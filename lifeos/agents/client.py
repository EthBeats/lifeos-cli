"""Client for interacting with local Ollama LLM instance with streaming support."""

import json
from typing import Generator, Optional
import httpx
from lifeos.config import settings


class OllamaClient:
    """Wrapper around Ollama local HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    def is_available(self) -> bool:
        """Check if the local Ollama daemon is running and accessible."""
        try:
            res = httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
            return res.status_code == 200
        except Exception:
            return False

    def generate_chat_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Generator[str, None, None]:
        """Stream chat tokens from Ollama REST API, capturing both thinking and answer fields."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
        }

        in_thinking = False

        with httpx.stream("POST", url, json=payload, timeout=120.0) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line)
                msg = chunk.get("message", {})

                # Extract both separate thinking fields and standard content
                thinking_chunk = (
                    msg.get("thinking") or msg.get("reasoning_content") or ""
                )
                content_chunk = msg.get("content") or ""

                # 1. Handle API returning thinking in separate field
                if thinking_chunk:
                    if not in_thinking:
                        in_thinking = True
                        yield "<think>" + thinking_chunk
                    else:
                        yield thinking_chunk

                # 2. Handle transition from thinking to main content
                elif content_chunk:
                    if in_thinking:
                        in_thinking = False
                        yield "</think>" + content_chunk
                    else:
                        yield content_chunk

            # Close think tag if stream finishes while thinking
            if in_thinking:
                yield "</think>"
