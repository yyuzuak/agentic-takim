"""Worker — NATS JetStream'den ACP.TASK.CREATED tüketen iskelet.

Şimdilik mesajı loglar ve ACK'ler. İleride: tool execution, embedding üretimi,
background job'lar. agent-runner'dan ayrı tutulur (ölçekleme/izolasyon).
"""
from __future__ import annotations

import asyncio
import os

import nats

from agentic_schemas.events.v1 import Subject

NATS_URL = os.environ.get("NATS_URL", "nats://nats:4222")
DURABLE = "worker-task-created"


async def main() -> None:
    nc = await nats.connect(NATS_URL, name="agentic-worker", reconnect_time_wait=2, max_reconnect_attempts=-1)
    js = nc.jetstream()
    print(f"✓ worker bağlandı: {NATS_URL}. Dinlenen: {Subject.TASK_CREATED.value}")

    async def handler(msg) -> None:
        print(f"[worker] mesaj: subject={msg.subject} bytes={len(msg.data)}")
        await msg.ack()

    # Stream init-nats.sh tarafından oluşturulur; burada sadece abone oluyoruz.
    await js.subscribe(Subject.TASK_CREATED.value, durable=DURABLE, cb=handler, manual_ack=True)

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
