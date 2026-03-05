import logging
import os
import time

import boto3
from botocore.exceptions import ClientError

from src.system_prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

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
            logger.debug(
                "Bedrock usage — input: %s, output: %s",
                usage.get("inputTokens"),
                usage.get("outputTokens"),
            )
            return response["output"]["message"]["content"][0]["text"]

        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ThrottlingException" and attempt < _MAX_RETRIES - 1:
                wait = _BASE_BACKOFF * (2 ** attempt)
                logger.warning("ThrottlingException — retrying in %.1fs (attempt %d)", wait, attempt + 1)
                time.sleep(wait)
            else:
                raise
