# CLAUDE.md — PR Summary & Risk Generator

## Project Overview

An automated pull request analysis system that triggers on code diffs, invokes Amazon Nova Pro via AWS Lambda + API Gateway, and stores structured AI-generated insights (summary, risk notes, one-line tag, test checklist) in DynamoDB.

---

## Technical Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Compute | AWS Lambda |
| API | AWS API Gateway (HTTP API, POST) |
| AI Model | Amazon Bedrock — `amazon.nova-pro-v1:0` |
| Storage | Amazon DynamoDB |
| Secrets | AWS Secrets Manager / SSM Parameter Store |
| CI/CD | GitHub Actions / GitLab CI |
| IaC | AWS SAM or CDK (TypeScript) |
| Observability | Amazon CloudWatch + EMF Metrics |

---

## Repository Structure

```
pr-risk-generator/
├── src/
│   ├── lambda_handler.py        # CLI entry point + Lambda handler
│   ├── diff_collector.py        # Diff Collector module
│   ├── prompt_builder.py        # Build Prompt module
│   ├── inference_wrapper.py     # Inference Wrapper (Bedrock client)
│   ├── response_parser.py       # Create Parser module
│   ├── dynamo_writer.py         # Platform Writer module
│   ├── system_prompt.py         # Prepare System Prompt
│   └── user_template.py         # Prepare User Template
├── tests/
│   ├── test_diff_collector.py
│   ├── test_prompt_builder.py
│   ├── test_inference_wrapper.py
│   ├── test_response_parser.py
│   └── test_dynamo_writer.py
├── .github/
│   └── workflows/
│       └── pr-analysis.yml      # GitHub Actions workflow
├── .gitlab-ci.yml               # GitLab CI job
├── template.yaml                # AWS SAM template
├── requirements.txt
├── .env.example
├── .gitignore
└── CLAUDE.md
```

---

## Module Descriptions & Implementation Guide

### 1. Create Repository
- Initialize with `.gitignore` (Python, `.env`, `__pycache__`, `.aws-sam/`)
- Branch strategy: `main` → protected, feature branches for all changes
- Enforce PR reviews before merge

### 2. Install Runtimes & SDKs
```bash
# Python 3.12
pyenv install 3.12.0
pyenv local 3.12.0

# AWS CLI + SAM CLI
pip install awscli aws-sam-cli
```

### 3. Install Dependencies
```
# requirements.txt
boto3>=1.34.0
aws-lambda-powertools>=2.40.0
pydantic>=2.7.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-mock>=3.14.0
moto[dynamodb,bedrock]>=5.0.0
```

### 4. Create `.env`
```bash
# .env.example  — never commit real values
AWS_REGION=us-east-1
DYNAMODB_TABLE_NAME=pr-analysis-results
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
MAX_TOKENS=2048
LOG_LEVEL=INFO
SECRET_NAME=pr-risk-generator/api-keys
```

---

## Flow

```
Git Diff (push/PR event)
        │
        ▼
API Gateway POST /analyze
        │
        ▼
Lambda Handler
  ├── Diff Collector      → normalise raw diff payload
  ├── Build Prompt        → inject diff into user template
  ├── System Prompt       → role + output format instructions
  ├── Inference Wrapper   → call Amazon Bedrock Nova Pro
  ├── Response Parser     → extract Summary, Risks, Tag, Checklist
  └── Platform Writer     → upsert to DynamoDB
        │
        ▼
DynamoDB  (PK: tag#timestamp)
  ├── modification_tag    (one-line diff descriptor — partition key)
  ├── timestamp           (ISO-8601 — sort key)
  ├── summary
  ├── risk_notes          (list)
  └── test_checklist      (list)
```

---

## Module Implementation Details

### `system_prompt.py` — Prepare System Prompt
```python
SYSTEM_PROMPT = """
You are a senior software engineer and security reviewer.
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
- Return ONLY the JSON object, no markdown fences, no extra text
"""
```

### `user_template.py` — Prepare User Template
```python
def build_user_message(diff: str, pr_title: str = "", pr_description: str = "") -> str:
    return f"""
PR Title: {pr_title or 'N/A'}
PR Description: {pr_description or 'N/A'}

Code Diff:
```diff
{diff}
```

Analyse the diff and return the JSON response.
"""
```

### `diff_collector.py` — Diff Collector
```python
def collect_diff(event: dict) -> dict:
    """
    Accepts API Gateway event body.
    Expected payload:
    {
      "diff": "<raw unified diff string>",
      "pr_title": "optional",
      "pr_description": "optional",
      "repo": "owner/repo",
      "pr_number": 42
    }
    Returns validated and sanitised diff context.
    """
```
- Validate required `diff` field
- Strip secrets/tokens from diff content (basic regex scan)
- Enforce max diff size: 50,000 characters (truncate with warning)

### `prompt_builder.py` — Build Prompt
```python
def build_messages(diff_context: dict) -> list[dict]:
    """Combine system prompt + user template into Bedrock messages format."""
    return [
        {"role": "user", "content": build_user_message(
            diff_context["diff"],
            diff_context.get("pr_title", ""),
            diff_context.get("pr_description", "")
        )}
    ]
```

### `inference_wrapper.py` — Inference Wrapper
```python
def invoke_nova(messages: list[dict]) -> str:
    """
    Call Amazon Bedrock Nova Pro.
    - Model: amazon.nova-pro-v1:0
    - Uses converse API for consistency
    - Implements exponential backoff on ThrottlingException
    - Returns raw response string
    """
    client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION"))
    response = client.converse(
        modelId=os.getenv("BEDROCK_MODEL_ID"),
        system=[{"text": SYSTEM_PROMPT}],
        messages=messages,
        inferenceConfig={"maxTokens": int(os.getenv("MAX_TOKENS", 2048))}
    )
    return response["output"]["message"]["content"][0]["text"]
```

### `response_parser.py` — Create Parser
```python
def parse_response(raw: str) -> dict:
    """
    Parse and validate JSON from Nova Pro response.
    Required keys: modification_tag, summary, risk_notes, test_checklist
    Raises ValueError on malformed response.
    """
```
- Strip any accidental markdown fences
- Validate all four required keys exist
- Ensure `risk_notes` and `test_checklist` are lists
- Return typed `ParsedAnalysis` Pydantic model

### `dynamo_writer.py` — Platform Writer
```python
def write_to_dynamo(analysis: ParsedAnalysis, metadata: dict) -> None:
    """
    PK  = modification_tag  (string — partition key)
    SK  = timestamp         (ISO-8601 UTC — sort key)

    Additional attributes:
    - summary          (String)
    - risk_notes       (List)
    - test_checklist   (List)
    - repo             (String)
    - pr_number        (Number)
    - diff_size_chars  (Number)
    - model_id         (String)
    - ttl              (Number — epoch, 90 days for cost control)
    """
```

### `lambda_handler.py` — CLI Entry Point
```python
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

@logger.inject_lambda_context
@tracer.capture_lambda_handler
def handler(event: dict, context: LambdaContext) -> dict:
    # 1. Parse body
    # 2. collect_diff()
    # 3. build_messages()
    # 4. invoke_nova()
    # 5. parse_response()
    # 6. write_to_dynamo()
    # 7. Return 200 + analysis JSON
```

---

## DynamoDB Schema

**Table Name:** `pr-analysis-results`

| Attribute | Type | Role |
|---|---|---|
| `modification_tag` | String (S) | Partition Key |
| `timestamp` | String (S) | Sort Key (ISO-8601 UTC) |
| `summary` | String (S) | |
| `risk_notes` | List (L) | |
| `test_checklist` | List (L) | |
| `repo` | String (S) | |
| `pr_number` | Number (N) | |
| `diff_size_chars` | Number (N) | |
| `model_id` | String (S) | |
| `ttl` | Number (N) | TTL attribute (90 days) |

**Billing mode:** PAY_PER_REQUEST  
**TTL:** Enabled on `ttl` attribute (auto-expire after 90 days)

---

## GitHub Actions Workflow

```yaml
# .github/workflows/pr-analysis.yml
name: PR Analysis

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  analyze:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate diff
        id: diff
        run: |
          git diff origin/${{ github.base_ref }}...HEAD > pr.diff
          echo "diff_b64=$(base64 -w0 pr.diff)" >> $GITHUB_OUTPUT

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Invoke PR Risk Generator API
        id: analysis
        run: |
          RESPONSE=$(curl -sf -X POST \
            "${{ secrets.API_GATEWAY_URL }}/analyze" \
            -H "Content-Type: application/json" \
            -d "{
              \"diff\": \"$(cat pr.diff | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'  | tr -d '\"')\",
              \"pr_title\": \"${{ github.event.pull_request.title }}\",
              \"repo\": \"${{ github.repository }}\",
              \"pr_number\": ${{ github.event.pull_request.number }}
            }")
          echo "response=$RESPONSE" >> $GITHUB_OUTPUT

      - name: Post analysis as PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const analysis = JSON.parse(`${{ steps.analysis.outputs.response }}`);
            const body = [
              `## 🤖 PR Analysis`,
              `**Tag:** \`${analysis.modification_tag}\``,
              `### Summary`,
              analysis.summary,
              `### ⚠️ Risk Notes`,
              analysis.risk_notes.map(r => `- ${r}`).join('\n'),
              `### ✅ Test Checklist`,
              analysis.test_checklist.map(t => `- [ ] ${t}`).join('\n'),
            ].join('\n\n');
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body
            });
```

---

## GitLab CI Job

```yaml
# .gitlab-ci.yml
pr-analysis:
  stage: test
  image: python:3.12-slim
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  before_script:
    - pip install awscli --quiet
    - apt-get install -y curl jq --quiet
  script:
    - git diff origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME...HEAD > pr.diff
    - |
      RESPONSE=$(curl -sf -X POST "$API_GATEWAY_URL/analyze" \
        -H "Content-Type: application/json" \
        -d "{\"diff\": $(python3 -c 'import sys,json; print(json.dumps(open("pr.diff").read()))'),
             \"pr_title\": \"$CI_MERGE_REQUEST_TITLE\",
             \"repo\": \"$CI_PROJECT_PATH\",
             \"pr_number\": $CI_MERGE_REQUEST_IID}")
    - echo "$RESPONSE" | jq .
    - |
      NOTE=$(echo "$RESPONSE" | jq -r '"**Tag:** `\(.modification_tag)`\n\n**Summary:** \(.summary)\n\n**Risks:**\n" + (.risk_notes | map("- " + .) | join("\n"))')
      curl -sf --request POST "$CI_API_V4_URL/projects/$CI_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID/notes" \
        --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
        --data-urlencode "body=$NOTE"
  variables:
    API_GATEWAY_URL: $API_GATEWAY_URL
```

---

## Unit Tests

```
tests/
├── test_diff_collector.py     — validate payload parsing, size limits, secret scrubbing
├── test_prompt_builder.py     — verify message structure matches Bedrock converse format
├── test_inference_wrapper.py  — mock Bedrock client, test retry logic, ThrottlingException
├── test_response_parser.py    — valid JSON, missing keys, malformed responses, fenced JSON
└── test_dynamo_writer.py      — mock DynamoDB via moto, verify PK/SK, TTL calculation
```

Run tests:
```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## Secret Management

| Secret | Store | Key |
|---|---|---|
| Bedrock model access | IAM Role (no secret needed) | — |
| API Gateway URL | GitHub/GitLab CI variable | `API_GATEWAY_URL` |
| GitLab token | GitLab CI variable (masked) | `GITLAB_TOKEN` |
| AWS Role ARN | GitHub secret | `AWS_ROLE_ARN` |

- Lambda uses **IAM execution role** — no hardcoded credentials
- All CI secrets stored as **masked, protected variables**
- Never log diff content at INFO level — use DEBUG only, disabled in production
- Rotate secrets via AWS Secrets Manager with automatic Lambda env injection

---

## Cost Optimisation

| Strategy | Detail |
|---|---|
| **DynamoDB TTL** | Auto-expire records after 90 days |
| **Diff size cap** | Truncate diffs > 50,000 chars before inference |
| **Max tokens** | Set `maxTokens=2048`; increase only if checklists truncate |
| **Lambda memory** | Start at 256 MB; profile with Lambda Power Tuning tool |
| **On-demand DynamoDB** | PAY_PER_REQUEST — no provisioned capacity waste |
| **Bedrock pricing** | Nova Pro charged per input/output token — monitor via CloudWatch |
| **Lambda timeout** | Set to 30s; Bedrock calls typically < 10s |
| **Caching** | Cache identical diff hashes in DynamoDB — skip re-inference |

---

## Metrics & KPIs

Emit via AWS Lambda Powertools EMF:

| Metric | Unit | Description |
|---|---|---|
| `InvocationCount` | Count | Total Lambda invocations |
| `InferenceLatencyMs` | Milliseconds | Bedrock response time |
| `InputTokens` | Count | Nova Pro input tokens consumed |
| `OutputTokens` | Count | Nova Pro output tokens consumed |
| `ParseFailures` | Count | Malformed JSON responses |
| `DynamoWriteErrors` | Count | Failed DynamoDB writes |
| `DiffSizeChars` | Count | Size of incoming diff |
| `TruncatedDiffs` | Count | Diffs exceeding size cap |

CloudWatch Alarm: `ParseFailures > 3 in 5 minutes` → SNS alert.

---

## SAM Template (key resources)

```yaml
# template.yaml (abbreviated)
Resources:
  AnalysisFunction:
    Type: AWS::Serverless::Function
    Properties:
      Handler: src/lambda_handler.handler
      Runtime: python3.12
      Timeout: 30
      MemorySize: 256
      Environment:
        Variables:
          DYNAMODB_TABLE_NAME: !Ref AnalysisTable
          BEDROCK_MODEL_ID: amazon.nova-pro-v1:0
          AWS_REGION: !Ref AWS::Region
      Policies:
        - DynamoDBCrudPolicy:
            TableName: !Ref AnalysisTable
        - Statement:
            Effect: Allow
            Action: bedrock:InvokeModel
            Resource: !Sub arn:aws:bedrock:${AWS::Region}::foundation-model/amazon.nova-pro-v1:0
      Events:
        AnalyzeAPI:
          Type: HttpApi
          Properties:
            Method: POST
            Path: /analyze

  AnalysisTable:
    Type: AWS::DynamoDB::Table
    Properties:
      TableName: pr-analysis-results
      BillingMode: PAY_PER_REQUEST
      AttributeDefinitions:
        - AttributeName: modification_tag
          AttributeType: S
        - AttributeName: timestamp
          AttributeType: S
      KeySchema:
        - AttributeName: modification_tag
          KeyType: HASH
        - AttributeName: timestamp
          KeyType: RANGE
      TimeToLiveSpecification:
        AttributeName: ttl
        Enabled: true
```

---

## Documentation Checklist

- [ ] `README.md` — setup, deploy, environment variables, local testing
- [ ] `ARCHITECTURE.md` — flow diagram, component responsibilities
- [ ] `CONTRIBUTING.md` — branch strategy, PR template, linting rules
- [ ] Inline docstrings on all public functions
- [ ] API contract documented (request/response schema with examples)
- [ ] Runbook — how to triage `ParseFailures` alarm
- [ ] Cost estimation table (monthly projected at N PRs/day)

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Invoke locally via SAM
sam build && sam local invoke AnalysisFunction \
  --event events/sample_pr.json \
  --env-vars .env.json

# Deploy
sam deploy --guided
```

---

*Last updated: 2026-03-04 | Model: amazon.nova-pro-v1:0 | Stack: AWS Lambda + API Gateway + Bedrock + DynamoDB*
