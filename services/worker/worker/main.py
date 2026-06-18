"""Worker — arka plan/sistem olaylarını tüketen iskelet.

ACP.SYSTEM.EVENT dinler (task yürütme agent-runner'a aittir; çakışmamak için
worker ayrı subject kullanır). İleride: tool execution, embedding, background job.
"""
from __future__ import annotations

import asyncio
import os

import nats

from agentic_schemas.events.v1 import Subject

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
DURABLE = "worker-system-event"


async def main() -> None:
    nc = await nats.connect(NATS_URL, name="agentic-worker", reconnect_time_wait=2, max_reconnect_attempts=-1)
    js = nc.jetstream()
    print(f"✓ worker bağlandı: {NATS_URL}. Dinlenen: {Subject.SYSTEM_EVENT.value}")

    async def handler(msg) -> None:
        print(f"[worker] mesaj: subject={msg.subject} bytes={len(msg.data)}")
        await msg.ack()

    # Stream'ler init-nats ile sonradan oluşabilir; oluşana kadar retry.
    for _ in range(60):
        try:
            await js.subscribe(Subject.SYSTEM_EVENT.value, durable=DURABLE, cb=handler, manual_ack=True)
            break
        except Exception:
            await asyncio.sleep(2)

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
