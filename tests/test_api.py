"""
Tests for the OpenRouterClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from harp.api import OpenRouterClient, BatchResponse


@pytest.fixture
def api_client() -> OpenRouterClient:
    """
    Provides a fresh OpenRouterClient instance.
    """
    return OpenRouterClient(api_key="test_key", base_url="https://test.ai/v1")


def test_api_initialization(api_client: OpenRouterClient) -> None:
    """
    Verifies the client is initialized with correct parameters.
    """
    assert api_client.client.api_key == "test_key"
    assert str(api_client.client.base_url) == "https://test.ai/v1/"


@pytest.mark.asyncio
async def test_transcribe_empty_data(api_client: OpenRouterClient) -> None:
    """
    Checks if transcribing empty data returns a default BatchResponse.
    """
    result = await api_client.transcribe(
        np.array([], dtype=np.float32), 16000, "test-model"
    )
    assert isinstance(result, BatchResponse)
    assert result.full_text == ""


@pytest.mark.asyncio
@patch("base64.b64encode")
@patch("wave.open")
async def test_transcribe_success(
    mock_wave_open: MagicMock, mock_b64encode: MagicMock, api_client: OpenRouterClient
) -> None:
    """
    Verifies a successful transcription call.
    """
    # Setup mocks
    mock_b64encode.return_value = b"dGVzdF9hdWRpbw=="
    api_client.client.beta = MagicMock()
    api_client.client.beta.chat = MagicMock()
    api_client.client.beta.chat.completions = MagicMock()
    api_client.client.beta.chat.completions.parse = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.parsed = BatchResponse(full_text="Success")
    api_client.client.beta.chat.completions.parse.return_value = mock_response

    audio_data = np.array([0.1, -0.1], dtype=np.float32)

    result = await api_client.transcribe(
        audio_data, 16000, "test-model", "test-instruction"
    )

    assert result.full_text == "Success"
    api_client.client.beta.chat.completions.parse.assert_called_once()

    # Check if the instruction and base64 audio were passed correctly
    call_args = api_client.client.beta.chat.completions.parse.call_args
    messages = call_args.kwargs["messages"]
    assert messages[0]["content"][0]["text"] == "test-instruction"
    assert messages[0]["content"][1]["input_audio"]["data"] == "dGVzdF9hdWRpbw=="


@pytest.mark.asyncio
async def test_transcribe_error(api_client: OpenRouterClient) -> None:
    """
    Checks if API errors are re-raised.
    """
    api_client.client.beta = MagicMock()
    api_client.client.beta.chat = MagicMock()
    api_client.client.beta.chat.completions = MagicMock()
    api_client.client.beta.chat.completions.parse = AsyncMock(
        side_effect=Exception("API Error")
    )

    audio_data = np.array([0.1], dtype=np.float32)
    with pytest.raises(Exception, match="API Error"):
        await api_client.transcribe(audio_data, 16000, "test-model")
