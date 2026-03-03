import json

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def success(body: dict, status_code: int = 200) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def error(message: str, status_code: int = 400) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": message}),
    }


def preflight() -> dict:
    """Handle CORS preflight OPTIONS request."""
    return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}
