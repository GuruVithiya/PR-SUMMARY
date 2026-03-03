import json

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    # TODO: When auth is added, invalidate token/session here
    # e.g. revoke Cognito token, delete DynamoDB session, blacklist JWT, etc.

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({"message": "Logged out successfully"}),
    }
