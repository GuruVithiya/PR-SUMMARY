"""
Consolidated Lambda handler — all modules in one file.
Covers: system prompt, user template, diff collector, prompt builder,
        inference wrapper, response parser, dynamo writer, and handler.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, field_validator
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior software engineer and security reviewer.
Analyse the provided code diff and respond ONLY with valid JSON matching this exact schema:

{
  "modification_tag": "<one-line imperative tag, max 72 chars>",
  "summary": "<2-4 sentence plain-English summary of what changed and why>",
  "risk_notes": ["<risk 1>", "<risk 2>", ...],
  "test_checklist": ["<test case 1>", "<test case 2>", ...]
}

Rules:
- modification_tag must be concise and start with a verb (e.g. "Add rate-limiting to auth endpoint")
- risk_notes must include security, performance, and regression risks where relevant
- test_checklist must be actionable and specific to the diff
- Return ONLY the JSON object, no markdown fences, no extra text"""

# ---------------------------------------------------------------------------
# User Template
# ---------------------------------------------------------------------------

def build_user_message(diff: str, pr_title: str = "", pr_description: str = "") -> str:
    """Build the user message to send to Bedrock with the diff context."""
    return f"""PR Title: {pr_title or 'N/A'}
PR Description: {pr_description or 'N/A'}

Code Diff:
```diff
{diff}
```

Analyse the diff and return the JSON response."""

# ---------------------------------------------------------------------------
# Diff Collector
# ---------------------------------------------------------------------------

MAX_DIFF_SIZE = 50_000

_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|token|password|passwd|auth)[^\n]{0,10}[=:]\s*["\']?[A-Za-z0-9+/=_\-]{16,}["\']?'),
    re.compile(r'(?i)aws_secret_access_key\s*=\s*[A-Za-z0-9+/]{40}'),
    re.compile(r'(?i)aws_access_key_id\s*=\s*AKIA[A-Z0-9]{16}'),
    re.compile(r'ghp_[A-Za-z0-9]{36}'),
    re.compile(r'glpat-[A-Za-z0-9\-_]{20}'),
]

_logger = logging.getLogger(__name__)


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
        _logger.warning("Diff truncated from %d to %d chars", len(diff), MAX_DIFF_SIZE)
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

# ---------------------------------------------------------------------------
# Prompt Builder
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Inference Wrapper
# ---------------------------------------------------------------------------

_MAX_RETRIES = 3
_BASE_BACKOFF = 1.0


def invoke_nova(messages: list[dict]) -> str:
    """
    Call Amazon Bedrock Nova Pro via the converse API.

    Implements exponential backoff on ThrottlingException.
    Returns the raw response string from the model.
    """
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))
    model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    max_tokens = int(os.getenv("MAX_TOKENS", "2048"))

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.converse(
                modelId=model_id,
                system=[{"text": SYSTEM_PROMPT}],
                messages=messages,
                inferenceConfig={"maxTokens": max_tokens},
            )
            usage = response.get("usage", {})
            _logger.debug(
                "Bedrock usage — input: %s, output: %s",
                usage.get("inputTokens"),
                usage.get("outputTokens"),
            )
            return response["output"]["message"]["content"][0]["text"]

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ThrottlingException" and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF * (2 ** attempt)
                _logger.warning("ThrottlingException — retrying in %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
            else:
                raise

# ---------------------------------------------------------------------------
# Response Parser
# ---------------------------------------------------------------------------

class ParsedAnalysis(BaseModel):
    modification_tag: str
    summary: str
    risk_notes: list[str]
    test_checklist: list[str]

    @field_validator("modification_tag")
    @classmethod
    def tag_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("modification_tag must not be empty")
        return v.strip()

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v.strip()


def parse_response(raw: str) -> ParsedAnalysis:
    """
    Parse and validate JSON from Nova Pro response.

    Strips accidental markdown fences, validates required keys,
    and returns a typed ParsedAnalysis Pydantic model.
    Raises ValueError on malformed response.
    """
    cleaned = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid JSON: {exc}") from exc

    required_keys = {"modification_tag", "summary", "risk_notes", "test_checklist"}
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"Response missing required keys: {missing}")

    for list_key in ("risk_notes", "test_checklist"):
        if not isinstance(data[list_key], list):
            raise ValueError(f"'{list_key}' must be a list, got {type(data[list_key]).__name__}")

    return ParsedAnalysis(**data)

# ---------------------------------------------------------------------------
# DynamoDB Writer
# ---------------------------------------------------------------------------

_TTL_DAYS = 90


def write_to_dynamo(analysis: ParsedAnalysis, metadata: dict) -> None:
    """
    Upsert analysis result to DynamoDB.

    PK  = modification_tag  (string — partition key)
    SK  = timestamp         (ISO-8601 UTC — sort key)

    Additional attributes:
    - summary, risk_notes, test_checklist
    - repo, pr_number, diff_size_chars, model_id
    - ttl (epoch seconds, 90 days from now)
    """
    table_name = os.getenv("DYNAMODB_TABLE_NAME", "pr-analysis-results")
    region = os.getenv("AWS_REGION", "us-east-1")

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    now = datetime.now(timezone.utc)
    ttl_epoch = int((now + timedelta(days=_TTL_DAYS)).timestamp())

    item = {
        "modification_tag": analysis.modification_tag,
        "timestamp": now.isoformat(),
        "summary": analysis.summary,
        "risk_notes": analysis.risk_notes,
        "test_checklist": analysis.test_checklist,
        "repo": metadata.get("repo", ""),
        "model_id": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"),
        "diff_size_chars": metadata.get("diff_size_chars", 0),
        "ttl": ttl_epoch,
    }

    pr_number = metadata.get("pr_number")
    if pr_number is not None:
        item["pr_number"] = int(pr_number)

    try:
        table.put_item(Item=item)
        _logger.info("Wrote analysis to DynamoDB: tag=%s", analysis.modification_tag)
    except Exception as exc:
        _logger.error("DynamoDB write failed: %s", exc)
        raise

# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------

logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="PRRiskGenerator")


def _error_response(status_code: int, message: str) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


@logger.inject_lambda_context
@tracer.capture_lambda_handler
@metrics.log_metrics
def handler(event: dict, context: LambdaContext) -> dict:
    """Lambda entry point — orchestrates the PR analysis pipeline."""
    metrics.add_metric(name="InvocationCount", unit=MetricUnit.Count, value=1)

    # 1. Collect and validate diff
    try:
        diff_context = collect_diff(event)
    except (ValueError, KeyError) as exc:
        logger.warning("Invalid request payload: %s", exc)
        return _error_response(400, str(exc))

    metrics.add_metric(name="DiffSizeChars", unit=MetricUnit.Count, value=diff_context["diff_size_chars"])
    if diff_context.get("truncated"):
        metrics.add_metric(name="TruncatedDiffs", unit=MetricUnit.Count, value=1)

    # 2. Build prompt messages
    messages = build_messages(diff_context)

    # 3. Call Bedrock Nova Pro
    t0 = time.monotonic()
    try:
        raw_response = invoke_nova(messages)
    except Exception as exc:
        logger.error("Bedrock invocation failed: %s", exc)
        return _error_response(502, "Inference service unavailable")
    finally:
        latency_ms = int((time.monotonic() - t0) * 1000)
        metrics.add_metric(name="InferenceLatencyMs", unit=MetricUnit.Milliseconds, value=latency_ms)

    # 4. Parse response
    try:
        analysis = parse_response(raw_response)
    except ValueError as exc:
        logger.error("Response parse failure: %s", exc)
        metrics.add_metric(name="ParseFailures", unit=MetricUnit.Count, value=1)
        return _error_response(502, f"Failed to parse model response: {exc}")

    # 5. Write to DynamoDB
    try:
        write_to_dynamo(analysis, diff_context)
    except Exception as exc:
        logger.error("DynamoDB write error: %s", exc)
        metrics.add_metric(name="DynamoWriteErrors", unit=MetricUnit.Count, value=1)
        # Non-fatal — still return the analysis to the caller

    # 6. Return result
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(analysis.model_dump()),
    }
