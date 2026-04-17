from __future__ import annotations

from src.config import LlmConfig
from src.llm.client import LlmClient
from src.llm.openai_client import OpenAiChatCompletionsClient
from src.llm.stub_client import StubLlmClient

def build_llm_client(cfg: LlmConfig) -> LlmClient:
    provider = (cfg.provider or "").strip().lower()

    if provider == "openai":
        return OpenAiChatCompletionsClient(cfg=cfg)

    # fallback
    return StubLlmClient()