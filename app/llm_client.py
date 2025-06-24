import asyncio
import logging
from typing import Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)


class LLMClient:
    """Handles communication with the LLM API"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_response(self, messages: List[Dict[str, str]],
                                max_tokens: int = 500,
                                temperature: float = 0.7) -> Optional[str]:
        """Generate a response using the LLM API"""
        if not self.session:
            raise RuntimeError("LLMClient not initialized. Use async context manager.")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }

        logger.debug(f"Sending request to LLM API: {self.base_url}/chat/completions")
        logger.debug(f"Payload: model={self.model}, messages={len(messages)}, max_tokens={max_tokens}, temp={temperature}")

        try:
            async with self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload
            ) as response:
                logger.debug(f"LLM API response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    response_content = data["choices"][0]["message"]["content"].strip()
                    logger.debug(f"LLM API response received, length: {len(response_content)}")
                    return response_content
                else:
                    error_text = await response.text()
                    logger.error(f"LLM API error {response.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            logger.error("LLM API request timed out")
            return None
        except Exception as e:
            logger.error(f"LLM API request failed: {e}")
            return None