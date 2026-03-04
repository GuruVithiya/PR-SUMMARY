import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from src.inference_wrapper import invoke_nova


MESSAGES = [{"role": "user", "content": "analyse this diff"}]

_BEDROCK_RESPONSE = {
    "output": {"message": {"content": [{"text": '{"modification_tag": "x", "summary": "y", "risk_notes": [], "test_checklist": []}'}]}},
    "usage": {"inputTokens": 10, "outputTokens": 20},
}


def _throttle_error():
    return ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "converse",
    )


@patch("src.inference_wrapper.boto3.client")
def test_successful_invocation(mock_client_cls):
    mock_client = MagicMock()
    mock_client.converse.return_value = _BEDROCK_RESPONSE
    mock_client_cls.return_value = mock_client

    result = invoke_nova(MESSAGES)
    assert "modification_tag" in result
    mock_client.converse.assert_called_once()


@patch("src.inference_wrapper.time.sleep")
@patch("src.inference_wrapper.boto3.client")
def test_retry_on_throttling(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.converse.side_effect = [
        _throttle_error(),
        _throttle_error(),
        _BEDROCK_RESPONSE,
    ]
    mock_client_cls.return_value = mock_client

    result = invoke_nova(MESSAGES)
    assert "modification_tag" in result
    assert mock_client.converse.call_count == 3
    assert mock_sleep.call_count == 2


@patch("src.inference_wrapper.time.sleep")
@patch("src.inference_wrapper.boto3.client")
def test_raises_after_max_retries(mock_client_cls, mock_sleep):
    mock_client = MagicMock()
    mock_client.converse.side_effect = _throttle_error()
    mock_client_cls.return_value = mock_client

    with pytest.raises(ClientError):
        invoke_nova(MESSAGES)

    assert mock_client.converse.call_count == 3


@patch("src.inference_wrapper.boto3.client")
def test_non_throttle_error_raises_immediately(mock_client_cls):
    mock_client = MagicMock()
    mock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "converse"
    )
    mock_client_cls.return_value = mock_client

    with pytest.raises(ClientError):
        invoke_nova(MESSAGES)

    assert mock_client.converse.call_count == 1
