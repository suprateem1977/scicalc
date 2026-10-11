// config.js - the ONE setting you change between version 1 and version 2.
//
// Version 1 (static):     leave API_URL empty  -> all maths runs in the browser.
// Version 2 (full stack): paste your API Gateway URL -> maths runs in AWS Lambda
//                         and history is saved in DynamoDB.
//
// Example: API_URL: "https://abc123xyz.execute-api.ap-south-1.amazonaws.com"
window.APP_CONFIG = {
  API_URL: ""
};
