"""lambda_function.py - the SciCalc backend, running in AWS Lambda.

API Gateway sends every request here. We look at the method and path and answer:

    POST   /calculate   {"expression": "sin(30)+2^3", "mode": "deg", "user_id": "user-abc"}
    GET    /history?user_id=user-abc
    DELETE /history?user_id=user-abc

Results are saved in the DynamoDB table named in the TABLE_NAME environment variable.
"""
import ast
import base64
import json
import math
import os
from datetime import datetime, timezone

TABLE_NAME = os.environ.get("TABLE_NAME", "calc-history")
MAX_LENGTH = 200          # longest expression we accept
MAX_EXPONENT = 1000       # stops things like 9^9^9 from freezing the server

FUNCTIONS = ["sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "ln", "log", "abs"]
CONSTANTS = {"pi": math.pi, "e": math.e}


class CalcError(Exception):
    """A mistake in the user's expression (shown to the user, not a server crash)."""


# --------------------------------------------------------------------- the maths engine
def evaluate(expression, mode="deg"):
    """Safely calculate a maths expression. Never uses eval()."""
    text = (expression.replace("×", "*").replace("÷", "/").replace("π", "pi")
            .replace("−", "-").replace("^", "**"))
    if not text.strip():
        raise CalcError("Nothing to calculate")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise CalcError("That doesn't look like a valid expression")
    try:
        result = _eval(tree.body, mode)
    except ZeroDivisionError:
        raise CalcError("Cannot divide by zero")
    except OverflowError:
        raise CalcError("Result is too big")
    if isinstance(result, complex) or math.isnan(result) or math.isinf(result):
        raise CalcError("Result is too big or undefined")
    result = float(f"{result:.12g}")  # tidy: sin(180) gives 0, not 1.2e-16
    return 0.0 if result == 0 else result


def _eval(node, mode):
    """Walk the expression tree. Only numbers, + - * / **, names and our functions are allowed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval(node.operand, mode)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left, mode), _eval(node.right, mode)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            if abs(right) > MAX_EXPONENT:
                raise CalcError("Exponent is too large")
            return left ** right
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise CalcError(f"Unknown name: {node.id}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
        if node.func.id not in FUNCTIONS:
            raise CalcError(f"Unknown name: {node.func.id}")
        return _apply(node.func.id, _eval(node.args[0], mode), mode)
    raise CalcError("That expression uses something this calculator doesn't support")


def _apply(name, x, mode):
    to_rad = math.radians if mode == "deg" else (lambda v: v)
    from_rad = math.degrees if mode == "deg" else (lambda v: v)
    if name in ("sin", "cos", "tan"):
        return getattr(math, name)(to_rad(x))
    if name in ("asin", "acos"):
        if not -1 <= x <= 1:
            raise CalcError(f"{name} needs a number between -1 and 1")
        return from_rad(getattr(math, name)(x))
    if name == "atan":
        return from_rad(math.atan(x))
    if name == "sqrt":
        if x < 0:
            raise CalcError("Square root of a negative number")
        return math.sqrt(x)
    if name in ("ln", "log"):
        if x <= 0:
            raise CalcError(f"{name} needs a positive number")
        return math.log(x) if name == "ln" else math.log10(x)
    return abs(x)


def format_number(value):
    """14.0 -> '14', 0.5 -> '0.5' (how results are stored in DynamoDB)."""
    return f"{value:.12g}"


# --------------------------------------------------------------------- DynamoDB
_table = None


def get_table():
    """Connect to DynamoDB the first time we need it (boto3 is built into Lambda)."""
    global _table
    if _table is None:
        import boto3
        _table = boto3.resource("dynamodb").Table(TABLE_NAME)
    return _table


# --------------------------------------------------------------------- the API
def reply(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": json.dumps(body),
    }


def read_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def user_id_from(event, body=None):
    user_id = ((body or {}).get("user_id")
               or (event.get("queryStringParameters") or {}).get("user_id")
               or "anonymous")
    return str(user_id)[:64]


def calculate(event):
    try:
        body = read_body(event)
    except (ValueError, UnicodeDecodeError):
        return reply(400, {"error": "Request body must be JSON"})
    expression = body.get("expression")
    mode = body.get("mode", "deg")
    if not isinstance(expression, str) or len(expression) > MAX_LENGTH:
        return reply(400, {"error": f"Send an expression of up to {MAX_LENGTH} characters"})
    if mode not in ("deg", "rad"):
        return reply(400, {"error": "mode must be 'deg' or 'rad'"})
    try:
        result = evaluate(expression, mode)
    except CalcError as err:
        return reply(400, {"error": str(err)})

    item = {
        "user_id": user_id_from(event, body),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expression": expression,
        "result": format_number(result),
        "mode": mode,
    }
    get_table().put_item(Item=item)
    return reply(200, {"result": result, "saved": item})


def get_history(event):
    response = get_table().query(
        KeyConditionExpression="user_id = :u",
        ExpressionAttributeValues={":u": user_id_from(event)},
        ScanIndexForward=False,   # newest first
        Limit=20,
    )
    return reply(200, {"items": response.get("Items", [])})


def clear_history(event):
    table = get_table()
    user_id = user_id_from(event)
    deleted = 0
    kwargs = {"KeyConditionExpression": "user_id = :u", "ExpressionAttributeValues": {":u": user_id}}
    while True:
        response = table.query(**kwargs)
        with table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"user_id": item["user_id"], "created_at": item["created_at"]})
                deleted += 1
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return reply(200, {"deleted": deleted})


def lambda_handler(event, context):
    """The function AWS Lambda calls. Handler setting: lambda_function.lambda_handler"""
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    print(f"{method} {path}")   # shows up in CloudWatch Logs
    try:
        if method == "OPTIONS":
            return reply(200, {})
        if method == "POST" and path.endswith("/calculate"):
            return calculate(event)
        if method == "GET" and path.endswith("/history"):
            return get_history(event)
        if method == "DELETE" and path.endswith("/history"):
            return clear_history(event)
        return reply(404, {"error": f"No route for {method} {path}"})
    except Exception as err:  # anything unexpected: log it, don't leak details
        print("ERROR:", repr(err))
        return reply(500, {"error": "Something went wrong on the server"})
