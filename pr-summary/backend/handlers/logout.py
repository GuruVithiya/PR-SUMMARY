from utils.response import success

# TODO: When auth is added, extract token from Authorization header
# and invalidate it (revoke Cognito token / delete session from DynamoDB / blacklist JWT)


def handle_logout(event, context):
    # TODO: token = event.get("headers", {}).get("Authorization", "")
    # TODO: invalidate_token(token)

    return success({"message": "Logged out successfully"})
