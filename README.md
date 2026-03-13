# PR Summary & Risk Generator

Automated pull request analysis using Amazon Nova Pro (via AWS Bedrock). Analyses code diffs and returns a structured AI-generated report with a summary, risk notes, and a test checklist — posted directly as a PR comment.

## How It Works

1. A PR is opened or updated on GitHub
2. GitHub Actions generates the diff and sends it to AWS Lambda via API Gateway
3. Lambda invokes Amazon Bedrock (Nova Pro) to analyse the diff
4. The structured response is stored in DynamoDB and posted as a PR comment

## Setup

### Prerequisites
- Python 3.12
- AWS account with Bedrock and DynamoDB access
- GitHub repository with Actions enabled

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Unit Tests
```bash
pytest tests/ -v
```

### Deploy to AWS (SAM)
```bash
sam build && sam deploy --guided
```

## Environment Variables

| Variable | Description |
|---|---|
| `AWS_REGION` | AWS region (e.g. `us-east-1`) |
| `DYNAMODB_TABLE_NAME` | DynamoDB table name |
| `BEDROCK_MODEL_ID` | Bedrock model ID (`amazon.nova-pro-v1:0`) |
| `MAX_TOKENS` | Max tokens for inference (default: `2048`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

## Triggering the Pipeline

Push a branch and open a PR against `main` — the GitHub Actions workflow runs automatically and posts the analysis as a PR comment.
