"""Kaptan orkestratörü — intent parsing + task decomposition (DAG) + yürütme.

Bir hedefi alt görev DAG'ına böler, bağımlılığı biten düğümleri NATS üzerinden
ilgili ajanlara dağıtır, sonuçları toplayıp birleştirir.

NOT: intent parsing şu an KURAL TABANLI (deterministik) — gerçek LLM `niyet-ayristirma`
(LiteLLM üzerinden) sonraki roadmap maddesi. Burada amaç çok-adımlı DAG yürütmesini
uçtan uca çalıştırmak.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from agentic_schemas.acp.v1 import TaskMessage, TaskPayload
from agentic_schemas.events.v1 import Subject

from . import planner
from .config import settings
from .db import SessionLocal
from .models import DeadLetterNode, ProcessedExecution, Task, TaskNode, TaskPlanVersion
from .routing import route

_lock = asyncio.Lock()

# Observability sayaçları (hybrid event+DB orchestration debugging için). GET /metrics döner.
_metrics = {
    "retry_scheduler_lock_conflicts_total": 0,
    "retries_scheduled_total": 0,
    "dead_letters_total": 0,
    "replays_total": 0,
}

# Failure taxonomy (ACP ErrorCode). Bunlar retry edilmez:
NON_RETRYABLE = {"SCHEMA", "PERMISSION", "LOGICAL", "BUDGET"}
RETRY_BASE_S = 1.0
RETRY_CAP_S = 8.0
TERMINAL = {"done", "dead_letter"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _exec_id(task_id: str, node_key: str, attempt: int) -> str:
    return hashlib.sha256(f"{task_id}:{node_key}:{attempt}".encode()).hexdigest()[:32]


def _retry_delay(policy: str, retry_count: int) -> float:
    if policy == "immediate":
        return 0.0
    # exponential + jitter
    return min(RETRY_BASE_S * (2 ** max(0, retry_count - 1)), RETRY_CAP_S) + random.uniform(0, 0.2)

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


def _build_nodes(s, task_id: str, plan: list[dict], retry_policy: str, max_retries: int) -> None:
    for n in plan:
        s.add(TaskNode(id=str(uuid4()), task_id=task_id, node_key=n["key"], agent=n["agent"],
                       skill=n["skill"], depends_on=n["depends_on"], status="pending",
                       retry_policy=retry_policy, max_retries=max_retries, retry_history=[]))


async def start_workflow(js, goal: str, skill: str | None, wtype: str | None,
                         require_approval: bool = False, actor: str = "anonymous",
                         inputs: dict | None = None, retry_policy: str | None = None,
                         max_retries: int | None = None) -> dict:
    task_id = str(uuid4())
    plan, source, error = await decompose(goal, skill, wtype)
    status = "awaiting_approval" if require_approval else "running"
    rp = retry_policy or "exponential"
    mr = max_retries if max_retries is not None else 3
    async with _lock:
        async with SessionLocal() as s:
            s.add(Task(id=task_id, trace_id=task_id, agent="kaptan", skill=skill, goal=goal,
                       status=status, plan=plan, require_approval=require_approval,
                       current_plan_version=1, last_modified_by=actor, inputs=inputs or {}))
            s.add(TaskPlanVersion(id=str(uuid4()), task_id=task_id, version=1, plan_json=plan, created_by=actor))
            _build_nodes(s, task_id, plan, rp, mr)
            await s.flush()
            if require_approval:
                await _emit_event(js, "approval.requested", task_id, actor, 1)
            else:
                await _dispatch_ready(s, js, task_id)
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
            await _dispatch_ready(s, js, task_id)
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
            # mevcut node'ların retry ayarlarını koru (yoksa varsayılan)
            existing = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().first()
            rp = existing.retry_policy if existing else "exponential"
            mr = existing.max_retries if existing else 3
            await s.execute(delete(TaskNode).where(TaskNode.task_id == task_id))
            _build_nodes(s, task_id, clean, rp, mr)
            await _emit_event(js, "approval.edited", task_id, actor, new_version)
            await s.commit()
            return {"task_id": task_id, "status": "awaiting_approval", "version": new_version, "plan": clean}


async def _dispatch_node(s, js, task: Task, node: TaskNode) -> None:
    """Tek düğümü yayınlar: yeni exec_id + msg_id, status=running, payload.inputs merge."""
    node.exec_id = _exec_id(task.id, node.node_key, node.retry_count)
    inputs = {"node": node.node_key, "attempt": node.retry_count, "exec_id": node.exec_id, **(task.inputs or {})}
    msg = TaskMessage(
        from_agent="kaptan", to_agent=node.agent, trace_id=UUID(task.id), skill=node.skill,
        timestamp=int(time.time()), payload=TaskPayload(goal=task.goal, inputs=inputs),
    )
    node.msg_id = str(msg.message_id)
    node.status = "running"
    await js.publish(Subject.TASK_CREATED.value, msg.model_dump_json(by_alias=True).encode())


async def _dispatch_ready(s, js, task_id: str) -> None:
    """Invariant: bir node dispatch edilebilir ⇔ tüm bağımlılıkları 'done'.
    (running|scheduled|dead_letter bağımlılık → done değil → child beklemede kalır.)"""
    task = await s.get(Task, task_id)
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    done = {n.node_key for n in nodes if n.status == "done"}
    for n in nodes:
        if n.status == "pending" and set(n.depends_on) <= done:
            await _dispatch_node(s, js, task, n)


async def _schedule_retry(node: TaskNode, error_code: str, last_error: str) -> None:
    node.retry_count += 1
    node.status = "scheduled"
    node.error_code = error_code
    node.last_error = last_error
    node.failed_at = _now()
    delay = _retry_delay(node.retry_policy, node.retry_count)
    node.retry_at = _now() + timedelta(seconds=delay)
    hist = list(node.retry_history or [])
    hist.append({"attempt": node.retry_count, "error_code": error_code, "at": _now().isoformat(), "next_delay_s": round(delay, 2)})
    node.retry_history = hist
    _metrics["retries_scheduled_total"] += 1
    print(f"[retry] node={node.node_key} attempt={node.retry_count} policy={node.retry_policy} next_delay={delay:.2f}s", flush=True)


async def _dead_letter(s, js, task: Task, node: TaskNode, error_code: str, last_error: str) -> None:
    node.status = "dead_letter"
    node.error_code = error_code
    node.last_error = last_error
    node.failed_at = _now()
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task.id))).scalars().all()
    dep_snapshot = {x.node_key: x.status for x in nodes}
    dag_hash = hashlib.sha256(json.dumps(task.plan, sort_keys=True).encode()).hexdigest()[:16]
    s.add(DeadLetterNode(
        id=str(uuid4()), task_id=task.id, node_id=node.id, node_key=node.node_key,
        error_code=error_code, retry_count=node.retry_count, last_error=last_error,
        retry_history=node.retry_history or [], dag_context_hash=dag_hash, dependency_snapshot=dep_snapshot,
    ))
    payload = {
        "event": "task.dlq", "task_id": task.id, "node_key": node.node_key, "error_code": error_code,
        "retry_count": node.retry_count, "retry_history": node.retry_history or [],
        "dag_context_hash": dag_hash, "dependency_snapshot": dep_snapshot, "timestamp": _now().isoformat(),
    }
    try:
        await js.publish(Subject.TASK_DLQ.value, json.dumps(payload).encode())
    except Exception:  # noqa: BLE001
        pass
    _metrics["dead_letters_total"] += 1
    print(f"[dlq] node={node.node_key} error={error_code} exhausted={node.retry_count}>={node.max_retries}", flush=True)


async def _on_node_failed(s, js, task: Task, node: TaskNode, error_code: str, last_error: str) -> None:
    non_retryable = error_code in NON_RETRYABLE
    if node.retry_policy == "manual" or non_retryable or node.retry_count >= node.max_retries:
        await _dead_letter(s, js, task, node, error_code, last_error)
    else:
        await _schedule_retry(node, error_code, last_error)


async def _finalize(s, task_id: str) -> None:
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    task = await s.get(Task, task_id)
    if task is None:
        return
    statuses = {n.status for n in nodes}
    if statuses == {"done"}:
        task.status = "done"
        task.result = {n.node_key: (n.result or {}) for n in nodes}
    elif "dead_letter" in statuses and not ({"pending", "running", "scheduled"} & statuses):
        task.status = "failed"
        task.error = "bir veya daha fazla düğüm dead_letter"


async def on_result(js, env: dict, subject: str) -> None:
    """COMPLETED/FAILED → dedup → düğüm güncelle → dispatch/retry/dead_letter → finalize."""
    in_reply_to = env.get("in_reply_to")
    exec_id = (env.get("payload") or {}).get("exec_id") or (env.get("context") or {}).get("exec_id")
    if not in_reply_to:
        return
    async with _lock:
        async with SessionLocal() as s:
            node = (await s.execute(select(TaskNode).where(TaskNode.msg_id == in_reply_to))).scalars().first()
            # Stale (eski attempt) veya terminal → yok say
            if node is None or node.status in TERMINAL:
                return
            # Fingerprint dedup: exec_id bir kez işlenir (exactly-once final state)
            fp = exec_id or node.exec_id
            if fp:
                res = await s.execute(
                    pg_insert(ProcessedExecution).values(exec_id=fp).on_conflict_do_nothing(index_elements=["exec_id"])
                )
                if res.rowcount == 0:
                    print(f"[dedup] ignored exec_id={fp}", flush=True)
                    return
            task = await s.get(Task, node.task_id)
            if subject == Subject.TASK_COMPLETED.value:
                node.status = "done"
                node.result = env.get("payload", {})
            else:
                code = env.get("error_code") or "UNKNOWN"
                await _on_node_failed(s, js, task, node, code, env.get("message") or "hata")
            await s.flush()
            await _dispatch_ready(s, js, node.task_id)
            await _finalize(s, node.task_id)
            await s.commit()


async def retry_scheduler(js) -> None:
    """Postgres tabanlı retry scheduler (async-sleep DEĞİL). ~1s'de bir vadesi gelen
    scheduled node'ları FOR UPDATE SKIP LOCKED ile alır ve re-dispatch eder (distributed-safe)."""
    while True:
        try:
            async with _lock:
                async with SessionLocal() as s:
                    due = (await s.execute(
                        select(TaskNode).where(TaskNode.status == "scheduled", TaskNode.retry_at <= _now())
                        .with_for_update(skip_locked=True)
                    )).scalars().all()
                    for node in due:
                        # CAS: yalnızca hâlâ 'scheduled' ise sahiplen (no double-pick invariant).
                        # SKIP LOCKED + _lock ile tek-instance'ta conflict=0; çok-instance'ta CAS kaybedeni sayar.
                        cas = await s.execute(
                            update(TaskNode).where(TaskNode.id == node.id, TaskNode.status == "scheduled")
                            .values(status="running")
                        )
                        if cas.rowcount != 1:
                            _metrics["retry_scheduler_lock_conflicts_total"] += 1
                            continue
                        await s.refresh(node)
                        task = await s.get(Task, node.task_id)
                        await _dispatch_node(s, js, task, node)
                    if due:
                        await s.commit()
        except Exception as e:  # noqa: BLE001
            print(f"[scheduler] hata: {e}", flush=True)
        await asyncio.sleep(1.0)


async def manual_retry(js, task_id: str, node_key: str, actor: str = "anonymous") -> dict:
    async with _lock:
        async with SessionLocal() as s:
            task = await s.get(Task, task_id)
            if task is None:
                return {"error": "not_found"}
            node = (await s.execute(
                select(TaskNode).where(TaskNode.task_id == task_id, TaskNode.node_key == node_key)
            )).scalars().first()
            if node is None:
                return {"error": "not_found"}
            if node.status not in {"dead_letter", "scheduled"}:
                return {"error": "invalid_state", "status": node.status}
            await s.execute(delete(DeadLetterNode).where(DeadLetterNode.node_id == node.id))
            node.retry_count += 1  # sonraki deneme olarak yeniden çalıştır
            await _dispatch_node(s, js, task, node)
            if task.status == "failed":
                task.status = "running"
            await _emit_event(js, "node.manual_retry", task_id, actor, task.current_plan_version)
            await s.commit()
            return {"task_id": task_id, "node": node_key, "status": "running"}


async def dlq_replay(js, node_id: str, actor: str = "anonymous", reset_retries: bool = True) -> dict:
    async with _lock:
        async with SessionLocal() as s:
            node = await s.get(TaskNode, node_id)
            if node is None:
                return {"error": "not_found"}
            # Idempotency: dead_letter satırını CAS-delete. rowcount==0 → zaten replay edilmiş → no-op.
            deleted = await s.execute(delete(DeadLetterNode).where(DeadLetterNode.node_id == node.id))
            if deleted.rowcount == 0:
                await s.commit()
                return {"task_id": node.task_id, "node": node.node_key, "status": "already_replayed"}
            task = await s.get(Task, node.task_id)
            if reset_retries:
                node.retry_count = 0
            else:
                node.retry_count += 1  # sonraki deneme olarak devam et
            await _dispatch_node(s, js, task, node)
            if task.status == "failed":
                task.status = "running"
            _metrics["replays_total"] += 1
            await _emit_event(js, "dlq.replayed", node.task_id, actor, task.current_plan_version)
            await s.commit()
            return {"task_id": node.task_id, "node": node.node_key, "status": "running", "reset_retries": reset_retries}
