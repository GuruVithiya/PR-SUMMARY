from src.user_template import build_user_message


def build_messages(diff_context: dict) -> list[dict]:
    """Combine diff context into Bedrock converse messages format."""
    return [
        {
            "role": "user",
            "content": build_user_message(
                diff_context["diff"],
                diff_context.get("pr_title", ""),
                diff_context.get("pr_description", ""),
            ),
        }
    ]
