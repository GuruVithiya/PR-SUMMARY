import pytest
from src.response_parser import parse_response, ParsedAnalysis

_VALID_JSON = '''{
  "modification_tag": "Add rate-limiting to auth endpoint",
  "summary": "This PR adds rate-limiting. It prevents brute force. Uses token bucket.",
  "risk_notes": ["Could break existing high-volume clients"],
  "test_checklist": ["Test normal login flow", "Test rate limit exceeded response"]
}'''


def test_valid_response():
    result = parse_response(_VALID_JSON)
    assert isinstance(result, ParsedAnalysis)
    assert result.modification_tag == "Add rate-limiting to auth endpoint"
    assert len(result.risk_notes) == 1
    assert len(result.test_checklist) == 2


def test_strips_markdown_fences():
    fenced = f"```json\n{_VALID_JSON}\n```"
    result = parse_response(fenced)
    assert result.modification_tag == "Add rate-limiting to auth endpoint"


def test_strips_plain_fences():
    fenced = f"```\n{_VALID_JSON}\n```"
    result = parse_response(fenced)
    assert isinstance(result, ParsedAnalysis)


def test_missing_key_raises():
    import json
    data = json.loads(_VALID_JSON)
    del data["risk_notes"]
    with pytest.raises(ValueError, match="missing required keys"):
        parse_response(json.dumps(data))


def test_invalid_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_response("not json at all")


def test_risk_notes_not_list_raises():
    import json
    data = json.loads(_VALID_JSON)
    data["risk_notes"] = "should be a list"
    with pytest.raises(ValueError, match="must be a list"):
        parse_response(json.dumps(data))


def test_test_checklist_not_list_raises():
    import json
    data = json.loads(_VALID_JSON)
    data["test_checklist"] = {"key": "value"}
    with pytest.raises(ValueError, match="must be a list"):
        parse_response(json.dumps(data))


def test_empty_modification_tag_raises():
    import json
    data = json.loads(_VALID_JSON)
    data["modification_tag"] = "   "
    with pytest.raises(Exception):
        parse_response(json.dumps(data))
