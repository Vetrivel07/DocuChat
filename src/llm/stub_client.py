from __future__ import annotations

from dataclasses import dataclass

from src.llm.client import LlmClient


@dataclass
class StubLlmClient(LlmClient):
    def generate(self, prompt: str) -> str:
        return "Stub LLM response (configure LLM_PROVIDER=openai to enable real generation)."