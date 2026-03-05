import json

from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

from src.diff_collector import collect_diff
from src.prompt_builder import build_messages
from src.inference_wrapper import invoke_nova
from src.response_parser import parse_response
from src.dynamo_writer import write_to_dynamo

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
    import time
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
