import os
import time
import pytest
import boto3
from moto import mock_aws

from src.response_parser import ParsedAnalysis
from src.dynamo_writer import write_to_dynamo, _TTL_DAYS

TABLE_NAME = "pr-analysis-results"
REGION = "us-east-1"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def dynamo_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "modification_tag", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "modification_tag", "KeyType": "HASH"},
                {"AttributeName": "timestamp", "KeyType": "RANGE"},
            ],
        )
        yield boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


_ANALYSIS = ParsedAnalysis(
    modification_tag="Add caching layer",
    summary="Adds Redis cache. Reduces DB load.",
    risk_notes=["Cache invalidation risk"],
    test_checklist=["Test cache hit", "Test cache miss"],
)

_METADATA = {
    "repo": "org/repo",
    "pr_number": 7,
    "diff_size_chars": 1234,
}


def test_item_written(dynamo_table):
    with mock_aws():
        write_to_dynamo(_ANALYSIS, _METADATA)
        resp = dynamo_table.scan()
        assert resp["Count"] == 1
        item = resp["Items"][0]
        assert item["modification_tag"] == "Add caching layer"
        assert item["repo"] == "org/repo"
        assert item["pr_number"] == 7


def test_pk_and_sk_present(dynamo_table):
    with mock_aws():
        write_to_dynamo(_ANALYSIS, _METADATA)
        item = dynamo_table.scan()["Items"][0]
        assert "modification_tag" in item
        assert "timestamp" in item


def test_ttl_approximately_90_days(dynamo_table):
    with mock_aws():
        before = int(time.time())
        write_to_dynamo(_ANALYSIS, _METADATA)
        after = int(time.time())
        item = dynamo_table.scan()["Items"][0]
        ttl = int(item["ttl"])
        expected_low = before + _TTL_DAYS * 86400
        expected_high = after + _TTL_DAYS * 86400
        assert expected_low <= ttl <= expected_high


def test_risk_notes_stored_as_list(dynamo_table):
    with mock_aws():
        write_to_dynamo(_ANALYSIS, _METADATA)
        item = dynamo_table.scan()["Items"][0]
        assert isinstance(item["risk_notes"], list)
        assert "Cache invalidation risk" in item["risk_notes"]


def test_no_pr_number_omitted(dynamo_table):
    with mock_aws():
        meta = {**_METADATA, "pr_number": None}
        write_to_dynamo(_ANALYSIS, meta)
        item = dynamo_table.scan()["Items"][0]
        assert "pr_number" not in item
