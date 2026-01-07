"""
Anthropic Claude API client wrapper.

Handles HTTP calls to Anthropic Messages API.
"""

import os
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# Default config (can be overridden via env vars)
DEFAULT_MODEL = "claude-sonnet-4-20250514"  # Updated model name
DEFAULT_MAX_TOKENS = 800
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TIMEOUT = 30  # seconds

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"


def call_claude_messages(
    prompt_text: str,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:
    """
    Call Anthropic Claude Messages API.
    
    Args:
        prompt_text: The user message/prompt to send
        model: Model name (defaults to env ANTHROPIC_MODEL or DEFAULT_MODEL)
        max_tokens: Max tokens in response (defaults to env ANTHROPIC_MAX_TOKENS or DEFAULT_MAX_TOKENS)
        temperature: Temperature (defaults to DEFAULT_TEMPERATURE)
    
    Returns:
        The text content from Claude's response
    
    Raises:
        ValueError: If API key is missing
        requests.RequestException: If HTTP request fails
        RuntimeError: If response parsing fails
    """
    # Get API key from environment
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
    
    # Get config from env or defaults
    model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    max_tokens = max_tokens or int(os.getenv("ANTHROPIC_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE
    
    url = f"{ANTHROPIC_API_BASE}/messages"
    
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {
                "role": "user",
                "content": prompt_text
            }
        ]
    }
    
    logger.debug(f"Calling Claude API: model={model}, max_tokens={max_tokens}, temperature={temperature}")
    logger.debug(f"Prompt length: {len(prompt_text)} chars")
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=DEFAULT_TIMEOUT
        )
        
        if response.status_code != 200:
            error_body = response.text[:500] if response.text else "No response body"
            logger.error(f"Claude API error: status={response.status_code}, body={error_body}")
            raise RuntimeError(
                f"Anthropic API error: status {response.status_code}. "
                f"Body (truncated): {error_body}"
            )
        
        response_data = response.json()
        
        # Extract text from content blocks
        # Claude Messages API returns content as array of content blocks
        content = response_data.get("content", [])
        if not content:
            raise RuntimeError("Claude API returned empty content")
        
        # Get the first text block
        text_parts = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        
        if not text_parts:
            raise RuntimeError("Claude API response contains no text content blocks")
        
        result_text = "".join(text_parts)
        
        logger.debug(f"Claude API success: response length={len(result_text)} chars")
        
        return result_text
        
    except requests.Timeout:
        logger.error(f"Claude API timeout after {DEFAULT_TIMEOUT}s")
        raise RuntimeError(f"Anthropic API request timed out after {DEFAULT_TIMEOUT} seconds")
    except requests.RequestException as e:
        logger.error(f"Claude API request failed: {e}")
        raise RuntimeError(f"Anthropic API request failed: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude API JSON response: {e}")
        raise RuntimeError(f"Failed to parse Anthropic API response: {str(e)}")



