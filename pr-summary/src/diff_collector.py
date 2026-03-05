import json
import logging
import re

logger = logging.getLogger(__name__)

MAX_DIFF_SIZE = 50_000

_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password|passwd|auth)[^\n]{0,10}[=:]\s*["\']?[A-Za-z0-9+/=_\-]{16,}["\']?'),
    re.compile(r'(?i)aws_secret_access_key\s*=\s*[A-Za-z0-9+/]{40}'),
    re.compile(r'(?i)aws_access_key_id\s*=\s*AKIA[A-Z0-9]{16}'),
    re.compile(r'ghp_[A-Za-z0-9]{36}'),
    re.compile(r'glpat-[A-Za-z0-9\-_]{20}'),
]


def _scrub_secrets(diff: str) -> str:
    """Replace secret-looking values with [REDACTED]."""
    for pattern in _SECRET_PATTERNS:
        diff = pattern.sub('[REDACTED]', diff)
    return diff


def collect_diff(event: dict) -> dict:
    """
    Accepts API Gateway event body (already parsed dict).

    Expected payload:
    {
      "diff": "<raw unified diff string>",
      "pr_title": "optional",
      "pr_description": "optional",
      "repo": "owner/repo",
      "pr_number": 42
    }

    Returns validated and sanitised diff context.
    Raises ValueError on missing required fields.
    """
    body = event
    if isinstance(event.get("body"), str):
        body = json.loads(event["body"])
    elif isinstance(event.get("body"), dict):
        body = event["body"]

    if "diff" not in body or not body["diff"]:
        raise ValueError("Missing required field: 'diff'")

    diff = body["diff"]
    diff = _scrub_secrets(diff)

    truncated = False
    if len(diff) > MAX_DIFF_SIZE:
        logger.warning("Diff truncated from %d to %d chars", len(diff), MAX_DIFF_SIZE)
        diff = diff[:MAX_DIFF_SIZE]
        truncated = True

    return {
        "diff": diff,
        "pr_title": body.get("pr_title", ""),
        "pr_description": body.get("pr_description", ""),
        "repo": body.get("repo", ""),
        "pr_number": body.get("pr_number"),
        "diff_size_chars": len(diff),
        "truncated": truncated,
    }
