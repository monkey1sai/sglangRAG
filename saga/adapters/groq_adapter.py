from __future__ import annotations

import logging
from typing import Any, Dict

try:
    from groq import Groq
except ImportError:
    Groq = None

logger = logging.getLogger(__name__)


class GroqAdapter:
    """Adapter for Groq chat completions."""

    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b"):
        if not Groq:
            raise ImportError(
                "Groq package not installed. Please install it with 'pip install groq'."
            )
        self.client = Groq(api_key=api_key)
        self.model = model
        logger.info(f"[GroqAdapter] Initialized with model={model}")

    def call(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Call Groq API and return parsed JSON in OpenAI-compatible format."""
        try:
            # Prepare arguments
            # Note: Groq might have specific parameters like reasoning_effort for some models
            params = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": kwargs.get("temperature", 0.7),
                "max_completion_tokens": kwargs.get("max_tokens", 8192),
                "stream": False,
            }
            
            # Add reasoning_effort if using a model that supports/requires it?
            # The user example showed "reasoning_effort": "medium" for openai/gpt-oss-120b
            # We can tentatively add it if it doesn't break other models, or strictly for this model.
            # For now, let's keep it simple or allow kwargs to override.
            if "reasoning_effort" in kwargs:
                params["reasoning_effort"] = kwargs["reasoning_effort"]
            elif self.model == "openai/gpt-oss-120b":
                 params["reasoning_effort"] = "medium"

            completion = self.client.chat.completions.create(**params)
            
            # Convert ChatCompletion object to dict compatible with SGLang/OpenAI response structure
            # The object has .choices[0].message.content
            
            return {
                "choices": [
                    {
                        "message": {
                            "content": completion.choices[0].message.content,
                            "role": completion.choices[0].message.role
                        }
                    }
                ],
                "usage": {
                    "completion_tokens": completion.usage.completion_tokens,
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "total_tokens": completion.usage.total_tokens
                } if completion.usage else {}
            }
            
        except Exception as e:
            logger.error(f"[GroqAdapter] API call failed: {e}")
            raise e
