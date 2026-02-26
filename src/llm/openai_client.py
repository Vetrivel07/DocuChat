from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from src.config import LlmConfig
from src.llm.client import LLMClient


@dataclass
class OpenAIClient(LLMClient):
    """
    Minimal OpenAI client using HTTP.
    - No extra deps
    - Uses Chat Completions endpoint
    """

    cfg: LlmConfig

    @staticmethod
    def from_env() -> "OpenAIClient":
        """
        Build from environment without depending on get_settings().
        Env:
          OPENAI_API_KEY (required)
          LLM_MODEL (default: gpt-4o-mini)
          TEMPERATURE (default: 0)
        """
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")

        model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        temp_raw = os.getenv("TEMPERATURE", "0").strip()

        try:
            temperature = float(temp_raw)
        except Exception:
            temperature = 0.0

        cfg = LlmConfig(
            openai_api_key=api_key,
            model=model,
            temperature=temperature,
        )
        return OpenAIClient(cfg=cfg)

    def generate(self, prompt: str) -> str:
        if not self.cfg.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing")

        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": self.cfg.model,
            "temperature": float(self.cfg.temperature),
            "messages": [
                # keep system minimal; your prompt already enforces grounding
                {"role": "system", "content": "You are a document-grounded assistant."},
                {"role": "user", "content": prompt},
            ],
        }

        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.cfg.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"OpenAI request failed: {e}") from e

        try:
            obj = json.loads(body)
            return obj["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenAI response parse failed: {e}. body={body[:400]}") from e