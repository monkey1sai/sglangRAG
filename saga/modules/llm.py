from __future__ import annotations

from typing import Any, Callable, Dict

from saga.adapters.sglang_adapter import SGLangAdapter
from saga.llm.parser import parse_analyzer_output, parse_implementer_output, parse_planner_output
from saga.llm.prompts import analyzer_prompt, implementer_prompt, planner_prompt
from saga.modules.base import Module


def _call_and_parse(client: SGLangAdapter, prompt: str, parser: Callable[[str], Any], max_retries: int = 3) -> Any:
    last_exc = None
    current_prompt = prompt
    
    for i in range(max_retries):
        try:
            resp = client.call(current_prompt)
            raw = resp["choices"][0]["message"]["content"]
            return parser(raw)
        except Exception as e:
            last_exc = e
            # Append error hint for next try
            current_prompt += f"\n\nSYSTEM: The previous response was invalid JSON. Error: {str(e)}. Please output strict JSON only."
    
    if last_exc:
        raise last_exc
    raise RuntimeError("Max retries reached")


class LLMAnalyzer(Module):
    """Analyzer module backed by SGLang."""

    def __init__(self, client: SGLangAdapter):
        self.client = client

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = analyzer_prompt(state.get("text", ""), state.get("keywords", []))
        return _call_and_parse(self.client, prompt, parse_analyzer_output)


class LLMPlanner(Module):
    """Planner module backed by SGLang."""

    def __init__(self, client: SGLangAdapter):
        self.client = client

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = planner_prompt(state.get("analysis", {}))
        return _call_and_parse(self.client, prompt, parse_planner_output)


class LLMImplementer(Module):
    """Implementer module backed by SGLang."""

    def __init__(self, client: SGLangAdapter):
        self.client = client

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = implementer_prompt(state.get("plan", {}))
        return _call_and_parse(self.client, prompt, parse_implementer_output)
