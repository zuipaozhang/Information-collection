"""
LLM client wrapper.

OpenAI-compatible async client with exponential backoff retry.
Supports DeepSeek, Qwen, and any OpenAI-compatible API.
"""

import json
import logging
from typing import Any

import httpx
from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

# HTTP errors that are worth retrying
RETRYABLE_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
)


class LLMClient:
    """Async LLM client with retry logic for OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        if not api_key:
            raise ValueError("LLM_API_KEY is required")

        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            max_retries=0,  # We handle retries ourselves
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    )
    async def _call_api(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Internal API call with retry."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def chat_completion(
        self,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            system: System prompt
            user: User message
            temperature: Response randomness (lower = more deterministic)
            max_tokens: Maximum tokens in response

        Returns:
            LLM response text
        """
        try:
            return await self._call_api(
                system=system,
                user=user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.error(f"LLM API call failed after retries: {e}")
            raise

    async def chat_completion_with_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        Send a chat completion and parse the response as JSON.

        Handles common JSON formatting issues (markdown code blocks,
        trailing commas, etc.).
        """
        response = await self.chat_completion(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Try to extract JSON from response (may be wrapped in markdown)
        text = response.strip()

        # Remove markdown code block markers
        if text.startswith("```"):
            # Find the end of the first line (```json or ```)
            first_newline = text.find("\n")
            if first_newline > 0:
                text = text[first_newline + 1:]
            # Remove trailing ```
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Try parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array/object boundaries
            for start_char, end_char in [("[", "]"), ("{", "}")]:
                start = text.find(start_char)
                end = text.rfind(end_char)
                if start >= 0 and end > start:
                    try:
                        return json.loads(text[start:end + 1])
                    except json.JSONDecodeError:
                        continue

            logger.error(f"Failed to parse LLM response as JSON: {text[:200]}...")
            raise ValueError(f"LLM response is not valid JSON: {text[:200]}...")
