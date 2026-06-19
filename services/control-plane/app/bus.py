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


async def _subscribe_one(js, subject: str, durable: str, handler) -> None:
    """Tek subject'i bağımsız abone et (stream oluşana kadar retry). Diğerlerini etkilemez."""
    for _ in range(120):
        try:
            await js.subscribe(subject, durable=durable, cb=handler, manual_ack=True)
            print(f"✓ sonuç tüketicisi aktif: {subject}")
            return
        except Exception:
            await asyncio.sleep(2)
    print(f"! sonuç tüketicisi başlatılamadı: {subject}")


async def result_consumer(js) -> None:
    """Her subject bağımsız abone (biri eksikse diğerleri etkilenmez)."""
    handler = _make_handler(js)
    await asyncio.gather(
        _subscribe_one(js, Subject.TASK_COMPLETED.value, "cp-completed", handler),
        _subscribe_one(js, Subject.TASK_FAILED.value, "cp-failed", handler),
        _subscribe_one(js, Subject.TOOL_RESULT.value, "cp-tool-result", handler),
    )
