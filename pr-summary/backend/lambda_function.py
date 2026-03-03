from utils.response import preflight, error
from handlers.bedrock import handle_bedrock


ROUTES = {
    ("POST", "/chat"): handle_bedrock,
}


def handler(event, context):
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    # Handle CORS preflight for all routes
    if http_method == "OPTIONS":
        return preflight()

    route_handler = ROUTES.get((http_method, path))

    if route_handler is None:
        return error(f"Route not found: {http_method} {path}", status_code=404)

    return route_handler(event, context)
