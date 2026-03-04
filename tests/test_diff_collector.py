import pytest
from src.diff_collector import collect_diff, MAX_DIFF_SIZE


def _event(body: dict) -> dict:
    return body


def test_valid_payload():
    event = _event({"diff": "- old\n+ new", "repo": "owner/repo", "pr_number": 1})
    result = collect_diff(event)
    assert result["diff"] == "- old\n+ new"
    assert result["repo"] == "owner/repo"
    assert result["pr_number"] == 1
    assert result["truncated"] is False


def test_missing_diff_raises():
    with pytest.raises(ValueError, match="Missing required field"):
        collect_diff({"repo": "owner/repo"})


def test_empty_diff_raises():
    with pytest.raises(ValueError, match="Missing required field"):
        collect_diff({"diff": ""})


def test_diff_truncated_at_limit():
    big_diff = "a" * (MAX_DIFF_SIZE + 100)
    result = collect_diff({"diff": big_diff})
    assert len(result["diff"]) == MAX_DIFF_SIZE
    assert result["truncated"] is True


def test_diff_at_limit_not_truncated():
    exact_diff = "a" * MAX_DIFF_SIZE
    result = collect_diff({"diff": exact_diff})
    assert result["truncated"] is False


def test_secrets_scrubbed_aws_key():
    diff = "+ aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
    result = collect_diff({"diff": diff})
    assert "AKIAIOSFODNN7EXAMPLE" not in result["diff"]
    assert "[REDACTED]" in result["diff"]


def test_secrets_scrubbed_token():
    diff = "+ api_key = supersecretvalue1234567890abcdef"
    result = collect_diff({"diff": diff})
    assert "supersecretvalue1234567890abcdef" not in result["diff"]


def test_nested_body_string():
    import json
    body = json.dumps({"diff": "- a\n+ b"})
    result = collect_diff({"body": body})
    assert result["diff"] == "- a\n+ b"


def test_optional_fields_default():
    result = collect_diff({"diff": "- x\n+ y"})
    assert result["pr_title"] == ""
    assert result["pr_description"] == ""
    assert result["pr_number"] is None
