"""Agent-runner LiteLLM istemcisi — gerçek ajan reasoning (v2.0-A).

control-plane/app/planner.py deseninin birebir yansıması: httpx → LiteLLM
/v1/chat/completions. Başarısızlıkta None döner → çağıran (consumer._collaborate)
deterministik stub'a düşer (graceful degradation; sistem asla çökmez).
"""
from __future__ import annotations

import asyncio
import os

import httpx

LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-local-master-dev")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet")
LLM_AVAILABLE = os.environ.get("LLM_AVAILABLE", "false").lower() == "true"

TIMEOUT_S = 60.0
MAX_RETRIES = 1
MAX_TOKENS = 4096


def llm_enabled() -> bool:
    return LLM_AVAILABLE


async def complete(messages: list[dict], *, json_mode: bool = True) -> str | None:
    """LiteLLM chat completion. İçerik string'i döner; her hata/timeout'ta None.

    None → çağıran stub'a düşer. LLM_AVAILABLE false ise hiç çağırmaz.
    """
    if not LLM_AVAILABLE:
        return None

    payload: dict = {
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}
    url = f"{LITELLM_URL}/v1/chat/completions"

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                r = await client.post(url, json=payload, headers=headers)
            if r.status_code >= 500 or r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                return None  # 4xx (ör. key yok) → retry'sız fallback
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.TimeoutException, httpx.TransportError):
            await asyncio.sleep(2 ** attempt)
        except Exception:
            return None
    return None
