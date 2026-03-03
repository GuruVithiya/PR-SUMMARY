import json
import boto3
from botocore.exceptions import ClientError
from utils.response import success, error

MODEL_ID = "amazon.nova-pro-v1:0"
AWS_REGION = "us-east-1"  # Nova Pro is available in us-east-1

bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

SYSTEM_PROMPT = """You are an expert software engineer and code reviewer specializing in summarizing GitHub Pull Requests.

When given a PR diff or description, you will:
1. Provide a concise summary of what the PR does and why.
2. List the key changes made (files modified, features added, bugs fixed).
3. Highlight any potential risks, breaking changes, or areas that need closer review.
4. Suggest a short, clear PR title if one is not provided.

Keep your response structured, clear, and developer-friendly and return in JSON Format."""


def handle_bedrock(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return error("Invalid JSON body", status_code=400)

    diff = body.get("diff", "").strip()
    if not diff:
        return error("diff is required", status_code=400)

    prompt = f"Please review and summarize the following PR diff:\n\n{diff}"

    # Optional inference params with sensible defaults
    max_tokens = body.get("max_tokens", 1024)
    temperature = body.get("temperature", 0.7)
    top_p = body.get("top_p", 0.9)

    request_payload = {
        "system": [{"text": SYSTEM_PROMPT}],
        "messages": [
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        "inferenceConfig": {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
    }

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(request_payload),
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        message = e.response["Error"]["Message"]
        return error(f"Bedrock error [{code}]: {message}", status_code=502)

    response_body = json.loads(response["body"].read())

    # Extract text from Nova Pro response structure
    output_text = (
        response_body.get("output", {})
        .get("message", {})
        .get("content", [{}])[0]
        .get("text", "")
    )

    return success({
        "response": output_text,
        "model": MODEL_ID,
        "usage": response_body.get("usage", {}),
    })
