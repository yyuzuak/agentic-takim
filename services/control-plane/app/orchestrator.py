"""Kaptan orkestratörü — intent parsing + task decomposition (DAG) + yürütme.

Bir hedefi alt görev DAG'ına böler, bağımlılığı biten düğümleri NATS üzerinden
ilgili ajanlara dağıtır, sonuçları toplayıp birleştirir.

NOT: intent parsing şu an KURAL TABANLI (deterministik) — gerçek LLM `niyet-ayristirma`
(LiteLLM üzerinden) sonraki roadmap maddesi. Burada amaç çok-adımlı DAG yürütmesini
uçtan uca çalıştırmak.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select

from agentic_schemas.acp.v1 import TaskMessage, TaskPayload
from agentic_schemas.events.v1 import Subject

from . import planner
from .config import settings
from .db import SessionLocal
from .models import Task, TaskNode, TaskPlanVersion
from .routing import route

_lock = asyncio.Lock()

# Kural tabanlı şablonlar: (node_key, skill, depends_on)
_BUILD = [
    ("t1", "pazar-zekasi-motoru", []),          # dedektif — pazar araştırması
    ("t2", "eda-motoru", []),                    # veda — veri analizi (t1 ile paralel)
    ("t3", "prd-uretici", ["t1", "t2"]),         # pusula — PRD (join)
    ("t4", "sistem-mimarisi-uretici", ["t3"]),   # mimar — mimari
    ("t5", "fullstack-kod-uretici", ["t4"]),     # usta — kod
]
_RESEARCH = [
    ("t1", "derin-web-arastirma", []),
    ("t2", "rakip-tersine-muhendislik", ["t1"]),
    ("t3", "onceliklendirme-motoru", ["t2"]),    # pusula — önceliklendirme
]


def infer_type(goal: str) -> str:
    g = goal.lower()
    if any(w in g for w in ["araştır", "arastir", "analiz", "rapor", "research", "incele"]):
        return "research"
    return "build"


def _rule_plan(goal: str, wtype: str | None) -> list[dict]:
    template = _RESEARCH if (wtype or infer_type(goal)) == "research" else _BUILD
    return [{"key": k, "skill": s, "depends_on": d} for k, s, d in template]


async def decompose(goal: str, skill: str | None, wtype: str | None) -> tuple[list[dict], str, str | None]:
    """(plan, source, error) döner. source ∈ {single, llm, rule}; error fallback nedeni.

    skill verildiyse tek düğüm (geriye uyumlu). Aksi halde LLM (varsa) → guardrail →
    geçerliyse llm; değilse kural tabanlı fallback (error nedeniyle).
    """
    if skill:
        plan = [{"key": "t1", "skill": skill, "depends_on": []}]
        source, error = "single", None
    else:
        nodes, error = (None, "disabled")
        if settings.llm_available:
            nodes, error = await planner.llm_plan(goal)
        if nodes:
            plan, source = nodes, "llm"
        else:
            plan, source = _rule_plan(goal, wtype), "rule"
    # her düğüme agent'ı route ile ekle
    for n in plan:
        n["agent"] = route(n["skill"])
    print(f'[planner] source={source} error={error} nodes={len(plan)} goal="{goal[:60]}"', flush=True)
    return plan, source, error


async def _emit_event(js, event: str, task_id: str, actor: str, version: int) -> None:
    """Onay yaşam döngüsü olayı — ACP.SYSTEM.EVENT (best-effort, audit zemini)."""
    try:
        payload = {
            "event": event, "task_id": task_id, "actor": actor, "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await js.publish(Subject.SYSTEM_EVENT.value, json.dumps(payload).encode())
    except Exception:  # noqa: BLE001
        pass


def _build_nodes(s, task_id: str, plan: list[dict]) -> None:
    for n in plan:
        s.add(TaskNode(id=str(uuid4()), task_id=task_id, node_key=n["key"], agent=n["agent"],
                       skill=n["skill"], depends_on=n["depends_on"], status="pending"))


async def start_workflow(js, goal: str, skill: str | None, wtype: str | None,
                         require_approval: bool = False, actor: str = "anonymous") -> dict:
    task_id = str(uuid4())
    plan, source, error = await decompose(goal, skill, wtype)
    status = "awaiting_approval" if require_approval else "running"
    async with _lock:
        async with SessionLocal() as s:
            s.add(Task(id=task_id, trace_id=task_id, agent="kaptan", skill=skill, goal=goal,
                       status=status, plan=plan, require_approval=require_approval,
                       current_plan_version=1, last_modified_by=actor))
            s.add(TaskPlanVersion(id=str(uuid4()), task_id=task_id, version=1, plan_json=plan, created_by=actor))
            _build_nodes(s, task_id, plan)
            await s.flush()
            if require_approval:
                await _emit_event(js, "approval.requested", task_id, actor, 1)
            else:
                await _dispatch_ready(s, js, task_id, goal)
            await s.commit()
    return {"task_id": task_id, "status": status, "planner": source, "planner_error": error,
            "version": 1, "plan": plan}


async def approve(js, task_id: str, actor: str = "anonymous") -> dict:
    async with _lock:
        async with SessionLocal() as s:
            task = await s.get(Task, task_id)
            if task is None:
                return {"error": "not_found"}
            if task.status != "awaiting_approval":
                return {"error": "invalid_state", "status": task.status}
            task.status = "running"
            task.last_modified_by = actor
            await s.flush()
            await _dispatch_ready(s, js, task_id, task.goal)
            await _emit_event(js, "approval.approved", task_id, actor, task.current_plan_version)
            await s.commit()
            return {"task_id": task_id, "status": "running"}


async def reject(js, task_id: str, actor: str = "anonymous", reason: str | None = None) -> dict:
    async with _lock:
        async with SessionLocal() as s:
            task = await s.get(Task, task_id)
            if task is None:
                return {"error": "not_found"}
            if task.status != "awaiting_approval":
                return {"error": "invalid_state", "status": task.status}
            task.status = "cancelled"
            task.error = reason
            task.last_modified_by = actor
            await _emit_event(js, "approval.rejected", task_id, actor, task.current_plan_version)
            await s.commit()
            return {"task_id": task_id, "status": "cancelled"}


async def edit(js, task_id: str, actor: str, nodes: list[dict]) -> dict:
    clean, err = planner.validate_plan_nodes(nodes)
    if clean is None:
        return {"error": "invalid_plan", "reason": err}
    for n in clean:
        n["agent"] = route(n["skill"])
    async with _lock:
        async with SessionLocal() as s:
            task = await s.get(Task, task_id)
            if task is None:
                return {"error": "not_found"}
            if task.status != "awaiting_approval":
                return {"error": "invalid_state", "status": task.status}
            new_version = task.current_plan_version + 1
            task.plan = clean
            task.current_plan_version = new_version
            task.last_modified_by = actor
            s.add(TaskPlanVersion(id=str(uuid4()), task_id=task_id, version=new_version, plan_json=clean, created_by=actor))
            await s.execute(delete(TaskNode).where(TaskNode.task_id == task_id))
            _build_nodes(s, task_id, clean)
            await _emit_event(js, "approval.edited", task_id, actor, new_version)
            await s.commit()
            return {"task_id": task_id, "status": "awaiting_approval", "version": new_version, "plan": clean}


async def _dispatch_ready(s, js, task_id: str, goal: str) -> None:
    """Bağımlılığı biten pending düğümleri yayınlar (aynı session içinde)."""
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    done = {n.node_key for n in nodes if n.status == "done"}
    for n in nodes:
        if n.status == "pending" and set(n.depends_on) <= done:
            msg = TaskMessage(
                from_agent="kaptan", to_agent=n.agent, trace_id=UUID(task_id), skill=n.skill,
                timestamp=int(time.time()), payload=TaskPayload(goal=goal, inputs={"node": n.node_key}),
            )
            n.msg_id = str(msg.message_id)
            n.status = "running"
            await js.publish(Subject.TASK_CREATED.value, msg.model_dump_json(by_alias=True).encode())


async def _finalize(s, task_id: str) -> None:
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    task = await s.get(Task, task_id)
    if task is None:
        return
    statuses = {n.status for n in nodes}
    if statuses == {"done"}:
        task.status = "done"
        task.result = {n.node_key: (n.result or {}) for n in nodes}
    elif "failed" in statuses and not ({"pending", "running"} & statuses):
        task.status = "failed"
        task.error = "bir veya daha fazla düğüm başarısız"


async def on_result(js, env: dict, subject: str) -> None:
    """agent-runner sonucu (COMPLETED/FAILED) → düğümü güncelle, yeni hazırları dağıt, gerekiyorsa bitir."""
    in_reply_to = env.get("in_reply_to")
    if not in_reply_to:
        return
    async with _lock:
        async with SessionLocal() as s:
            node = (await s.execute(select(TaskNode).where(TaskNode.msg_id == in_reply_to))).scalars().first()
            if node is None:
                return  # eşleşmeyen/orphan sonuç
            task_id = node.task_id
            if subject == Subject.TASK_COMPLETED.value:
                node.status = "done"
                node.result = env.get("payload", {})
            else:
                node.status = "failed"
                node.error = env.get("message") or "hata"
            await s.flush()
            task = await s.get(Task, task_id)
            await _dispatch_ready(s, js, task_id, task.goal if task else "")
            await _finalize(s, task_id)
            await s.commit()
