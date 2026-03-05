from src.prompt_builder import build_messages


def test_messages_format():
    diff_context = {
        "diff": "- old\n+ new",
        "pr_title": "My PR",
        "pr_description": "Some changes",
    }
    messages = build_messages(diff_context)
    assert isinstance(messages, list)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert isinstance(messages[0]["content"], str)


def test_diff_in_content():
    diff_context = {"diff": "- foo\n+ bar", "pr_title": "", "pr_description": ""}
    messages = build_messages(diff_context)
    assert "- foo\n+ bar" in messages[0]["content"]


def test_pr_title_in_content():
    diff_context = {"diff": "x", "pr_title": "Fix bug", "pr_description": ""}
    messages = build_messages(diff_context)
    assert "Fix bug" in messages[0]["content"]


def test_missing_optional_fields_use_defaults():
    diff_context = {"diff": "x"}
    messages = build_messages(diff_context)
    assert "N/A" in messages[0]["content"]


def test_single_user_message_only():
    """Bedrock converse requires alternating roles starting with user."""
    diff_context = {"diff": "x", "pr_title": "", "pr_description": ""}
    messages = build_messages(diff_context)
    roles = [m["role"] for m in messages]
    assert roles == ["user"]
