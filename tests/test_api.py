"""
Tests for the LLMClient.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from harp.api import LLMClient


@pytest.fixture
def llm_client() -> LLMClient:
    """
    Provides a fresh LLMClient instance.
    """
    return LLMClient(api_key="test_key", base_url="https://test.ai/v1")


def test_llm_initialization(llm_client: LLMClient) -> None:
    """
    Verifies the client is initialized with correct parameters.
    """
    assert llm_client.client.api_key == "test_key"
    assert str(llm_client.client.base_url) == "https://test.ai/v1/"


@pytest.mark.asyncio
async def test_process_text_empty_input(llm_client: LLMClient) -> None:
    """
    Checks if processing empty text returns an empty string.
    """
    result = await llm_client.process_text("", "instruction", "model")
    assert result == ""


@pytest.mark.asyncio
async def test_process_text_success(llm_client: LLMClient) -> None:
    """
    Verifies a successful text processing call.
    """
    llm_client.client.chat = MagicMock()
    llm_client.client.chat.completions = MagicMock()
    llm_client.client.chat.completions.create = AsyncMock()

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Success"
    llm_client.client.chat.completions.create.return_value = mock_response

    result = await llm_client.process_text(
        "test input", "test instruction", "test-model"
    )

    assert result == "Success"
    llm_client.client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_process_text_error(llm_client: LLMClient) -> None:
    """
    Checks if API errors are re-raised.
    """
    llm_client.client.chat = MagicMock()
    llm_client.client.chat.completions = MagicMock()
    llm_client.client.chat.completions.create = AsyncMock(
        side_effect=Exception("API Error")
    )

    with pytest.raises(Exception, match="API Error"):
        await llm_client.process_text("test input", "test instruction", "test-model")
