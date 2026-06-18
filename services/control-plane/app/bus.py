"""NATS JetStream köprüsü — Kaptan'ın yayını + sonuç tüketicisi.

Akış: control-plane TaskMessage'ı ACP.TASK.CREATED'a yayınlar; agent-runner işler
ve ACP.TASK.COMPLETED / ACP.TASK.FAILED'a yazar; buradaki tüketici sonucu DB'ye işler.
"""
from __future__ import annotations

import asyncio
import json

import nats

from agentic_schemas.events.v1 import Subject

from . import orchestrator
from .config import settings


async def connect():
    """NATS'a bağlan (sonsuz reconnect)."""
    return await nats.connect(
        settings.nats_url, name="control-plane", reconnect_time_wait=2, max_reconnect_attempts=-1
    )


def _make_handler(js):
    async def _handle_result(msg) -> None:
        try:
            env = json.loads(msg.data)
            await orchestrator.on_result(js, env, msg.subject)
        finally:
            await msg.ack()
    return _handle_result


async def result_consumer(js) -> None:
    """Stream'ler init-nats ile sonradan oluşabilir; oluşana kadar retry."""
    handler = _make_handler(js)
    for _ in range(60):
        try:
            await js.subscribe(Subject.TASK_COMPLETED.value, durable="cp-completed", cb=handler, manual_ack=True)
            await js.subscribe(Subject.TASK_FAILED.value, durable="cp-failed", cb=handler, manual_ack=True)
            print("✓ control-plane sonuç tüketicisi aktif (COMPLETED/FAILED).")
            return
        except Exception:
            await asyncio.sleep(2)
    print("! control-plane sonuç tüketicisi başlatılamadı (stream yok?).")
