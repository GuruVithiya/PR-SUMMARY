import logging
import os
from datetime import datetime, timezone, timedelta

import boto3

from src.response_parser import ParsedAnalysis

logger = logging.getLogger(__name__)

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
        logger.info("Wrote analysis to DynamoDB: tag=%s", analysis.modification_tag)
    except Exception as exc:
        logger.error("DynamoDB write failed: %s", exc)
        raise
