"""Redis sliding-window rate limiter — v0.9.1

Anahtarlar:
  rl:{tool}:min:{epoch_minute}  — dakikalık sayaç (INCR + EXPIRE 70sn)
  rl:{tool}:task:{task_id}      — task başına sayaç (INCR + EXPIRE 3600sn)

Redis bağlanamazsa → passthrough (True, 0) — graceful degradation.
"""
from __future__ import annotations

import time

RL_MIN_TTL = 70
RL_TASK_TTL = 3600


async def check(tool: str, task_id: str, spec: dict, redis) -> tuple[bool, int]:
    """Returns (allowed: bool, retry_after_seconds: int).

    spec: {"per_minute": N, "per_task": M} veya None/eksik → limitsiz.
    """
    limits = spec.get("rate_limit") if spec else None
    if not limits:
        return True, 0

    per_minute = limits.get("per_minute", 0)
    per_task = limits.get("per_task", 0)

    epoch_min = int(time.time() // 60)
    min_key = f"rl:{tool}:min:{epoch_min}"
    task_key = f"rl:{tool}:task:{task_id}"

    try:
        if per_minute:
            cur = await redis.incr(min_key)
            if cur == 1:
                await redis.expire(min_key, RL_MIN_TTL)
            if cur > per_minute:
                ttl = await redis.ttl(min_key)
                return False, max(ttl, 1)

        if per_task:
            cur = await redis.incr(task_key)
            if cur == 1:
                await redis.expire(task_key, RL_TASK_TTL)
            if cur > per_task:
                ttl = await redis.ttl(task_key)
                return False, max(ttl, 1)

        return True, 0
    except Exception:
        return True, 0
