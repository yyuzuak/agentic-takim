"""LLM tabanlı planlayıcı — Kaptan'ın `niyet-ayristirma` skill'i.

LLM YALNIZCA plan üreticisidir: hedefi alır, izinli skill listesinden bir DAG
üretir. Düğüm yürütmesi (agent-runner) LLM çağırmaz. Her hata graceful fallback
ile kural tabanlı decompose'a düşer; nedeni (planner_error) raporlanır.
"""
from __future__ import annotations

import asyncio
import json

import httpx
from pydantic import BaseModel, ValidationError

from .config import settings
from .routing import get_registry

MAX_NODES = 8
TIMEOUT_S = 30.0
MAX_RETRIES = 2  # ilk denemeye ek olarak en fazla 2 retry


class _PlanNode(BaseModel):
    key: str
    skill: str
    depends_on: list[str] = []


class _Plan(BaseModel):
    nodes: list[_PlanNode]


def _allowed_skills() -> set[str]:
    reg = get_registry()
    return {s for a in reg.agents.values() if a.type.value != "meta" for s in a.skills}


def _build_messages(goal: str) -> list[dict]:
    reg = get_registry()
    catalog = {aid: a.skills for aid, a in reg.agents.items() if a.type.value != "meta"}
    system = (
        "Sen Kaptan'sın: bir ürün ekibinin orkestratörü. Kullanıcı hedefini, ekibin "
        "yapabileceği alt görevlerden oluşan yönlü-asiklik bir görev grafiğine (DAG) böl.\n"
        "Yalnızca JSON döndür: {\"nodes\":[{\"key\":\"t1\",\"skill\":\"<skill>\",\"depends_on\":[\"t0\"]}]}\n"
        f"Ajan→skill kataloğu (SADECE bu skill'leri kullan): {json.dumps(catalog, ensure_ascii=False)}\n"
        "KURALLAR:\n"
        "- SADECE yukarıdaki listeden skill seç. Uygun skill yoksa nodes'u BOŞ döndür; asla skill UYDURMA.\n"
        f"- En fazla {MAX_NODES} düğüm.\n"
        "- key'ler benzersiz (t1, t2, ...). depends_on yalnızca var olan key'lere işaret etsin. Döngü olmasın.\n"
        "- Bağımsız işler paralel olabilir (depends_on boş)."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": goal}]


def _is_acyclic(nodes: list[_PlanNode]) -> bool:
    keys = {n.key for n in nodes}
    deps = {n.key: set(n.depends_on) for n in nodes}
    # tüm bağımlılıklar var olan key'ler ve self-dep yok
    for k, ds in deps.items():
        if k in ds or not ds <= keys:
            return False
    # Kahn topolojik sıralama
    indeg = {k: len(ds) for k, ds in deps.items()}
    ready = [k for k, d in indeg.items() if d == 0]
    seen = 0
    while ready:
        k = ready.pop()
        seen += 1
        for other, ds in deps.items():
            if k in ds:
                indeg[other] -= 1
                if indeg[other] == 0:
                    ready.append(other)
    return seen == len(nodes)


def _validate(raw: str) -> tuple[list[dict] | None, str | None]:
    try:
        plan = _Plan.model_validate_json(raw)
    except ValidationError:
        return None, "schema_invalid"
    if not plan.nodes:
        return None, "empty"
    if len(plan.nodes) > MAX_NODES:
        return None, "schema_invalid"
    allowed = _allowed_skills()
    if any(n.skill not in allowed for n in plan.nodes):
        return None, "schema_invalid"  # halüsine/uydurma skill
    if len({n.key for n in plan.nodes}) != len(plan.nodes):
        return None, "schema_invalid"
    if not _is_acyclic(plan.nodes):
        return None, "schema_invalid"
    return [{"key": n.key, "skill": n.skill, "depends_on": n.depends_on} for n in plan.nodes], None


async def llm_plan(goal: str) -> tuple[list[dict] | None, str | None]:
    """(nodes, error_reason) döner. Başarıda (nodes, None); aksi halde (None, reason)."""
    payload = {
        "model": settings.llm_model,
        "messages": _build_messages(goal),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {settings.litellm_master_key}"}
    url = f"{settings.litellm_url}/v1/chat/completions"

    last_err = "http_error"
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
                r = await client.post(url, json=payload, headers=headers)
            if r.status_code >= 500 or r.status_code == 429:
                last_err = "http_error"
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                return None, "http_error"  # 4xx (ör. key yok) → retry'sız fallback
            content = r.json()["choices"][0]["message"]["content"]
            return _validate(content)
        except (httpx.TimeoutException, httpx.TransportError):
            last_err = "timeout"
            await asyncio.sleep(2 ** attempt)
        except Exception:
            return None, "http_error"
    return None, last_err
