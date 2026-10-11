"""test_lambda_function.py - checks the backend before it is deployed.

Run on your computer:   pip install pytest   then   pytest -q backend
GitHub Actions runs exactly the same command before every deploy.
No AWS account is needed: a pretend DynamoDB table stands in for the real one.
"""
import json

import pytest

import lambda_function as app


# ------------------------------------------------------------------ a pretend DynamoDB table
class FakeTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)

    def query(self, ExpressionAttributeValues, ScanIndexForward=True, Limit=None, **kwargs):
        user = ExpressionAttributeValues[":u"]
        found = sorted((i for i in self.items if i["user_id"] == user), key=lambda i: i["created_at"],
                       reverse=not ScanIndexForward)
        return {"Items": found[:Limit] if Limit else found}

    def batch_writer(self):
        table = self

        class Batch:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def delete_item(self, Key):
                table.items = [i for i in table.items
                               if (i["user_id"], i["created_at"]) != (Key["user_id"], Key["created_at"])]
        return Batch()


@pytest.fixture
def table(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(app, "get_table", lambda: fake)
    return fake


def request(method, path, body=None, user_id=None):
    event = {"requestContext": {"http": {"method": method}}, "rawPath": path}
    if body is not None:
        event["body"] = json.dumps(body)
    if user_id:
        event["queryStringParameters"] = {"user_id": user_id}
    response = app.lambda_handler(event, None)
    return response["statusCode"], json.loads(response["body"])


# ------------------------------------------------------------------ the maths
@pytest.mark.parametrize("expression, mode, expected", [
    ("2+3*4", "deg", 14),
    ("(2+3)*4", "deg", 20),
    ("2^3^2", "deg", 512),
    ("-2^2", "deg", -4),
    ("sin(30)", "deg", 0.5),
    ("sin(pi/2)", "rad", 1),
    ("cos(60)", "deg", 0.5),
    ("tan(45)", "deg", 1),
    ("asin(1)", "deg", 90),
    ("sqrt(16)+abs(-3)", "deg", 7),
    ("ln(e)", "deg", 1),
    ("log(1000)", "deg", 3),
    ("sin(180)", "deg", 0),
    ("10/4", "deg", 2.5),
    ("2×3÷4", "deg", 1.5),
])
def test_evaluate(expression, mode, expected):
    assert app.evaluate(expression, mode) == pytest.approx(expected)


@pytest.mark.parametrize("bad", ["1/0", "sqrt(-1)", "2+", "foo(2)", "(1+2", "", "9^9^9",
                                 "__import__('os')", "open('x')", "[1,2]", "2 if 1 else 3"])
def test_bad_expressions_are_rejected(bad):
    with pytest.raises(app.CalcError):
        app.evaluate(bad)


# ------------------------------------------------------------------ the API
def test_calculate_saves_to_history(table):
    status, body = request("POST", "/calculate", {"expression": "2+2", "mode": "deg", "user_id": "u1"})
    assert status == 200
    assert body["result"] == 4
    assert table.items[0]["result"] == "4"


def test_calculate_reports_user_mistakes(table):
    status, body = request("POST", "/calculate", {"expression": "1/0", "user_id": "u1"})
    assert status == 400
    assert "divide by zero" in body["error"]
    assert table.items == []


def test_calculate_rejects_bad_requests(table):
    assert request("POST", "/calculate", {"expression": "1" * 500})[0] == 400
    assert request("POST", "/calculate", {"expression": "1+1", "mode": "grad"})[0] == 400
    event = {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/calculate", "body": "not json"}
    assert app.lambda_handler(event, None)["statusCode"] == 400


def test_history_newest_first_and_per_user(table):
    request("POST", "/calculate", {"expression": "1+1", "user_id": "u1"})
    request("POST", "/calculate", {"expression": "2+2", "user_id": "u1"})
    request("POST", "/calculate", {"expression": "3+3", "user_id": "someone-else"})
    status, body = request("GET", "/history", user_id="u1")
    assert status == 200
    assert [i["expression"] for i in body["items"]] == ["2+2", "1+1"]


def test_clear_history(table):
    request("POST", "/calculate", {"expression": "1+1", "user_id": "u1"})
    request("POST", "/calculate", {"expression": "5+5", "user_id": "u2"})
    status, body = request("DELETE", "/history", user_id="u1")
    assert (status, body["deleted"]) == (200, 1)
    assert [i["user_id"] for i in table.items] == ["u2"]


def test_unknown_route_and_cors(table):
    status, _ = request("GET", "/nope")
    assert status == 404
    response = app.lambda_handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/history"}, None)
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"
