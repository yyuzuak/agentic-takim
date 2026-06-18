"""NATS JetStream köprüsü — Kaptan'ın yayını + sonuç tüketicisi.

Akış: control-plane TaskMessage'ı ACP.TASK.CREATED'a yayınlar; agent-runner işler
ve ACP.TASK.COMPLETED / ACP.TASK.FAILED'a yazar; buradaki tüketici sonucu DB'ye işler.
"""
from __future__ import annotations

import asyncio
import json

import nats

from agentic_schemas.events.v1 import Subject

from .config import settings
from .db import SessionLocal
from .models import Task


async def connect():
    """NATS'a bağlan (sonsuz reconnect)."""
    return await nats.connect(
        settings.nats_url, name="control-plane", reconnect_time_wait=2, max_reconnect_attempts=-1
    )


async def _handle_result(msg) -> None:
    try:
        env = json.loads(msg.data)
        trace_id = env.get("trace_id")
        async with SessionLocal() as s:
            task = await s.get(Task, trace_id)
            if task is not None:
                if msg.subject == Subject.TASK_COMPLETED.value:
                    task.status = "done"
                    task.result = env.get("payload", {})
                else:
                    task.status = "failed"
                    task.error = env.get("message") or json.dumps(env.get("payload", {}))
                await s.commit()
    finally:
        await msg.ack()


async def result_consumer(js) -> None:
    """Stream'ler init-nats ile sonradan oluşabilir; oluşana kadar retry."""
    for _ in range(60):
        try:
            await js.subscribe(Subject.TASK_COMPLETED.value, durable="cp-completed", cb=_handle_result, manual_ack=True)
            await js.subscribe(Subject.TASK_FAILED.value, durable="cp-failed", cb=_handle_result, manual_ack=True)
            print("✓ control-plane sonuç tüketicisi aktif (COMPLETED/FAILED).")
            return
        except Exception:
            await asyncio.sleep(2)
    print("! control-plane sonuç tüketicisi başlatılamadı (stream yok?).")
