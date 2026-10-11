# SciCalc: a scientific calculator on AWS

A beginner-friendly full-stack app, built in two versions:

| Version | Where it runs |
|---|---|
| **1 · Static** | `frontend/` on **S3 + CloudFront**. All maths runs in the browser. |
| **2 · Full stack** | The same frontend, plus **API Gateway → Lambda → DynamoDB**. The maths runs in Lambda and history is saved in DynamoDB. |

Switching between them is one line in `frontend/config.js` (`API_URL`).

## What's in this folder

```
frontend/              the website (uploaded to S3)
  index.html           page layout
  style.css            the look
  calculator.js        safe maths engine for the browser (no eval)
  app.js               buttons, display, history; talks to the API in version 2
  config.js            API_URL: empty = version 1, your API URL = version 2
backend/
  lambda_function.py   the Lambda function (uploaded to AWS Lambda)
  test_lambda_function.py   tests, run by GitHub Actions before every deploy
iam/                   copy-paste IAM policies (replace YOUR-... placeholders)
events/                example requests for testing the Lambda
.github/workflows/test.yml     CI: runs the tests on every push
ci-cd/deploy.yml               CI/CD: test, then deploy (move it into .github/workflows/ in Part 11)
```

## Try it on your computer

```bash
python3 -m http.server 8000 --directory frontend
```

Open http://localhost:8000 (or just double-click `frontend/index.html`).

## Run the tests

```bash
pip install pytest
pytest -q backend
```

## Deploy

Follow the slides in `2_aws_full_stack.html`, step by step. When you're done,
delete everything (last part of the slides) so nothing keeps costing money.
