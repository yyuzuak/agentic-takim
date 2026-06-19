"""Circuit Breaker — v1.1-c

State: CLOSED → (N fail) → OPEN → (60s) → HALF_OPEN → (success) → CLOSED
                                                        → (fail)   → OPEN

State Redis'te saklanır: servis restart sonrası korunur.
OPEN iken: CIRCUIT_OPEN exception (non-retryable).
"""
from __future__ import annotations

import time
from enum import Enum


class CBState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """OPEN state: adapter geçici olarak devre dışı."""
    code = "CIRCUIT_OPEN"


class CircuitBreaker:
    def __init__(self, name: str, redis, fail_threshold: int = 5, recovery_timeout: int = 60):
        self.name = name
        self._redis = redis
        self._fail_threshold = fail_threshold
        self._recovery_timeout = recovery_timeout
        self._state_key = f"cb:{name}:state"
        self._fail_key = f"cb:{name}:fails"
        self._open_since_key = f"cb:{name}:open_since"

    async def state(self) -> CBState:
        s = await self._redis.get(self._state_key)
        if s is None:
            return CBState.CLOSED
        val = s if isinstance(s, str) else s.decode()
        if val == CBState.OPEN:
            open_since = await self._redis.get(self._open_since_key)
            if open_since:
                elapsed = time.time() - float(open_since)
                if elapsed >= self._recovery_timeout:
                    await self._redis.set(self._state_key, CBState.HALF_OPEN)
                    return CBState.HALF_OPEN
        return CBState(val)

    async def call(self, fn, *args, **kwargs):
        """fn'i circuit breaker ile çağır."""
        current = await self.state()

        if current == CBState.OPEN:
            raise CircuitOpenError(f"Circuit {self.name} is OPEN")

        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception:
            await self._on_fail()
            raise

    async def _on_success(self) -> None:
        await self._redis.set(self._state_key, CBState.CLOSED)
        await self._redis.delete(self._fail_key)
        await self._redis.delete(self._open_since_key)

    async def _on_fail(self) -> None:
        fails = await self._redis.incr(self._fail_key)
        if int(fails) >= self._fail_threshold:
            await self._redis.set(self._state_key, CBState.OPEN)
            await self._redis.set(self._open_since_key, str(time.time()))
        else:
            current = await self._redis.get(self._state_key)
            if current and (current if isinstance(current, str) else current.decode()) == CBState.HALF_OPEN:
                # HALF_OPEN'da fail → tekrar OPEN
                await self._redis.set(self._state_key, CBState.OPEN)
                await self._redis.set(self._open_since_key, str(time.time()))

    async def reset(self) -> None:
        """Manuel reset (test amaçlı)."""
        await self._redis.delete(self._state_key, self._fail_key, self._open_since_key)
