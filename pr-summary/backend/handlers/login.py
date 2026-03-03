import json
from utils.response import success, error

# TODO: Replace with real auth when Cognito / JWT is integrated
MOCK_USERS = {
    "admin@example.com": "password123",
}


def handle_login(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return error("Invalid JSON body", status_code=400)

    email = body.get("email", "").strip()
    password = body.get("password", "").strip()

    if not email or not password:
        return error("email and password are required", status_code=400)

    # TODO: Replace mock check with Cognito initiateAuth call
    if MOCK_USERS.get(email) != password:
        return error("Invalid credentials", status_code=401)

    # TODO: Return real Cognito tokens here
    return success({
        "message": "Login successful",
        "token": "mock-token-replace-with-cognito",
        "email": email,
    })
