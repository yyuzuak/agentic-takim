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

from . import context_reducer, memory, planner, schema_validator
from .config import settings
from .db import SessionLocal
from .models import (
    DeadLetterNode,
    ProcessedExecution,
    Task,
    TaskContextEvent,
    TaskContextSnapshot,
    TaskNode,
    TaskPlanVersion,
)
from .routing import route


def _same_dag(plan_a: list[dict], plan_b) -> bool:
    """İki planın yapısal (skill + bağımlılık) eşitliği — copy-risk telemetrisi."""
    if not plan_a or not plan_b:
        return False
    def sig(p):
        return sorted((n.get("skill"), tuple(sorted(n.get("depends_on", [])))) for n in p)
    return sig(plan_a) == sig(plan_b)

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

# v0.7.1 refinement
REFINE_TERMINAL = {"accept", "max_depth", "converged", "node_cap"}


def _fp(goal: str, content) -> str:
    return hashlib.sha256(f"{goal}|{json.dumps(content, sort_keys=True, ensure_ascii=False)}".encode()).hexdigest()[:16]


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
# v0.7 collab: producer → critic → synthesizer (acyclic)
_COLLAB = [
    ("t1", "prd-uretici", [], "producer"),
    ("t2", "sistem-mimarisi-uretici", ["t1"], "critic"),
    ("t3", "fullstack-kod-uretici", ["t1", "t2"], "synthesizer"),
]


# v0.9 fulfillment: tool node DAG (check_stock → create_quote → generate_pdf → approval → send_whatsapp)
_FULFILLMENT = [
    ("t1", "tool", "check_stock", {"sku": "HTD-8M-800", "qty": 1}, []),
    ("t2", "tool", "create_quote", {"customer": "ABC Makina", "items": ["HTD 8M 800"]}, ["t1"]),
    ("t3", "tool", "generate_pdf", {"quote_id": "from:t2"}, ["t2"]),
    ("t4", "approval", None, None, ["t3"]),
    ("t5", "tool", "send_whatsapp", {"to": "+90", "doc": "from:t3"}, ["t4"]),
]

# v2.0-B app-build: Next.js+Prisma repo üreten sabit (deterministik) DAG.
# Şekil sabit tutulur — assembler prisma→api bağımlılığına ve page/api ayrımına güvenir.
_APP_BUILD = [
    ("t1", "app-spec-uretici", []),               # pusula — entity/feature/sayfa speci
    ("t2", "sistem-mimarisi-uretici", ["t1"]),    # mimar — mimari (stack sabit)
    ("t3", "prisma-sema-uretici", ["t1", "t2"]),  # usta — prisma şema + seed
    ("t4", "nextjs-sayfa-uretici", ["t1", "t2"]), # usta — app/page + components
    ("t5", "nextjs-api-uretici", ["t3"]),         # usta — app/api route'ları (şemaya bağlı)
]


def infer_type(goal: str) -> str:
    g = goal.lower()
    if any(w in g for w in ["teklif", "quote", "stok", "stock", "whatsapp", "gönder", "gonder", "fatura", "sipariş", "siparis"]):
        return "fulfillment"
    if any(w in g for w in ["eleştir", "elestir", "değerlendir", "degerlendir", "gözden geçir", "critique", "review", "consensus", "uzlaş"]):
        return "collab"
    if any(w in g for w in ["uygulama", "app", "web sitesi", "website", "nextjs", "next.js", "dashboard", "gösterge paneli"]):
        return "app-build"
    if any(w in g for w in ["araştır", "arastir", "analiz", "rapor", "research", "incele"]):
        return "research"
    return "build"


def _rule_plan(goal: str, wtype: str | None) -> list[dict]:
    t = wtype or infer_type(goal)
    if t == "fulfillment":
        return [{"key": k, "kind": kind, "tool": tool, "args": args, "depends_on": d}
                for k, kind, tool, args, d in _FULFILLMENT]
    if t == "collab":
        return [{"key": k, "skill": s, "depends_on": d, "role": r} for k, s, d, r in _COLLAB]
    if t == "app-build":
        return [{"key": k, "skill": s, "depends_on": d, "role": "producer"} for k, s, d in _APP_BUILD]
    template = _RESEARCH if t == "research" else _BUILD
    return [{"key": k, "skill": s, "depends_on": d, "role": "producer"} for k, s, d in template]


async def decompose(goal: str, skill: str | None, wtype: str | None) -> tuple[list[dict], str, str | None]:
    """(plan, source, error) döner. source ∈ {single, llm, rule}; error fallback nedeni.

    skill verildiyse tek düğüm (geriye uyumlu). Aksi halde LLM (varsa) → guardrail →
    geçerliyse llm; değilse kural tabanlı fallback (error nedeniyle).
    """
    inferred = wtype or infer_type(goal)
    # --- Memory recall (planner'dan ÖNCE; danışmanlık, DAG üretmez) ---
    mem = {"hits": [], "ids": [], "confidence": "low", "avg": 0.0}
    if settings.memory_available and not skill:
        async with SessionLocal() as ms:
            res = await memory.recall(ms, goal, inferred)
            await ms.commit()
        mem["hits"] = res["hits"]
        mem["ids"] = [h["task_id"] for h in res["hits"]]
        mem["confidence"] = res["confidence"]
        mem["avg"] = res["avg_score"]

    if skill:
        plan, source = [{"key": "t1", "skill": skill, "depends_on": []}], "single"
        error = None
    elif inferred == "app-build":
        # v2.0-B: app-build DAG'ı deterministik (LLM planner bypass) — şekil sabit,
        # assembler buna güvenir. Düğüm İÇERİĞİ yine gerçek LLM ile üretilir.
        plan, source, error = _rule_plan(goal, "app-build"), "rule", "app_build_deterministic"
    else:
        nodes, error = (None, "disabled")
        if settings.llm_available:
            nodes, error = await planner.llm_plan(goal, mem["hits"])  # LLM few-shot enrichment
        if nodes:
            plan, source = nodes, "llm"
        else:
            # rule yolu: yalnız confidence=high ise memory intent/template'i etkiler
            chosen = wtype
            if not wtype and mem["confidence"] == "high" and mem["hits"]:
                chosen = mem["hits"][0].get("workflow_type")
                inferred = chosen or inferred
            plan, source = _rule_plan(goal, chosen), "rule"
    for n in plan:
        kind = n.get("kind", "reasoning")
        if kind == "tool":
            n["agent"] = "tool-runtime"
        elif kind == "approval":
            n["agent"] = "kaptan"
        else:
            n["agent"] = route(n["skill"])
        n.setdefault("role", "producer")

    # copy-risk telemetrisi (ölç, bloklama yok)
    warning = "retrieval_copy_risk" if any(_same_dag(plan, h.get("plan")) for h in mem["hits"]) else None

    print(f'[memory] goal="{goal[:40]}" hits={len(mem["hits"])} avg={mem["avg"]} confidence={mem["confidence"]}', flush=True)
    print(f'[planner] source={source} error={error} nodes={len(plan)} warning={warning}', flush=True)
    meta = {"hits": len(mem["hits"]), "ids": mem["ids"], "confidence": mem["confidence"],
            "avg": mem["avg"], "warning": warning, "wf_type": inferred}
    return plan, source, error, meta


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


def _build_nodes(s, task_id: str, plan: list[dict], retry_policy: str, max_retries: int,
                 refine_enabled: bool = False) -> None:
    for n in plan:
        role = n.get("role", "producer")
        # refine açıksa critic node'ları bir refine_group başlatır (chain id = node_key)
        group = n["key"] if (refine_enabled and role == "critic") else None
        s.add(TaskNode(id=str(uuid4()), task_id=task_id, node_key=n["key"], agent=n["agent"],
                       skill=n.get("skill"), depends_on=n["depends_on"], status="pending",
                       node_role=role, refine_group=group, refine_depth=0,
                       node_kind=n.get("kind", "reasoning"), tool=n.get("tool"), tool_args=n.get("args"),
                       retry_policy=retry_policy, max_retries=max_retries, retry_history=[]))


async def _append_event(s, task_id: str, etype: str, agent: str | None, node_key: str | None,
                        payload: dict, exec_id: str | None = None) -> None:
    seq = await context_reducer.next_seq(s, task_id)
    s.add(TaskContextEvent(id=str(uuid4()), task_id=task_id, seq=seq, type=etype,
                           agent=agent, node_key=node_key, payload=payload, exec_id=exec_id))


async def start_workflow(js, goal: str, skill: str | None, wtype: str | None,
                         require_approval: bool = False, actor: str = "anonymous",
                         inputs: dict | None = None, retry_policy: str | None = None,
                         max_retries: int | None = None) -> dict:
    task_id = str(uuid4())
    plan, source, error, meta = await decompose(goal, skill, wtype)

    # Plan-time tool schema validation (v0.9.1, INV-3) — erken hata yakalama
    plan_errors = schema_validator.validate_tool_plan(plan)
    if plan_errors:
        return {"error": "invalid_plan", "reason": f"tool schema errors: {'; '.join(plan_errors)}"}

    status = "awaiting_approval" if require_approval else "running"
    rp = retry_policy or "exponential"
    mr = max_retries if max_retries is not None else 3
    # memory metadata + planner kaynağını task.inputs'a göm (store/feedback için)
    task_inputs = {**(inputs or {}), "_workflow_type": meta["wf_type"],
                   "_planner_source": source, "_memory_ids": meta["ids"]}
    async with _lock:
        async with SessionLocal() as s:
            s.add(Task(id=task_id, trace_id=task_id, agent="kaptan", skill=skill, goal=goal,
                       status=status, plan=plan, require_approval=require_approval,
                       current_plan_version=1, last_modified_by=actor, inputs=task_inputs))
            s.add(TaskPlanVersion(id=str(uuid4()), task_id=task_id, version=1, plan_json=plan, created_by=actor))
            refine_enabled = int((inputs or {}).get("max_refinement_depth", 0)) > 0
            _build_nodes(s, task_id, plan, rp, mr, refine_enabled)
            await s.flush()
            # v0.7 — context init event + snapshot
            await _append_event(s, task_id, "task.init", "kaptan", None, {"goal": goal})
            await context_reducer.apply(s, task_id)
            if require_approval:
                await _emit_event(js, "approval.requested", task_id, actor, 1)
            else:
                await _dispatch_ready(s, js, task_id)
            await s.commit()
    return {"task_id": task_id, "status": status, "planner": source, "planner_error": error,
            "version": 1, "plan": plan, "memory_hits": meta["hits"], "memory_ids": meta["ids"],
            "memory_confidence": meta["confidence"], "memory_avg_score": meta["avg"],
            "planner_warning": meta["warning"]}


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
    # Plan-time tool schema validation (v0.9.1)
    tool_errs = schema_validator.validate_tool_plan(clean)
    if tool_errs:
        return {"error": "invalid_plan", "reason": f"tool schema errors: {'; '.join(tool_errs)}"}
    for n in clean:
        kind = n.get("kind", "reasoning")
        n["agent"] = "tool-runtime" if kind == "tool" else "kaptan" if kind == "approval" else route(n["skill"])
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
    """node_kind'e göre dağıtım: reasoning→TASK.CREATED, tool→TOOL.REQUEST, approval→awaiting."""
    # approval node: dispatch yok, insan onayı beklenir (node-seviye HITL)
    if node.node_kind == "approval":
        node.status = "awaiting_approval"
        await _emit_event(js, "node.awaiting_approval", task.id, "kaptan", 0)
        print(f"[approval] node={node.node_key} awaiting_approval", flush=True)
        return

    node.exec_id = _exec_id(task.id, node.node_key, node.retry_count)
    inputs = {"node": node.node_key, "attempt": node.retry_count, "exec_id": node.exec_id,
              "refine_depth": node.refine_depth, **(task.inputs or {})}
    snap_row = await s.get(TaskContextSnapshot, task.id)
    snapshot = snap_row.snapshot if snap_row else {}
    all_nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task.id))).scalars().all()
    by_key = {n.node_key: n for n in all_nodes}
    node_history = [{"node_key": dk, "agent": by_key[dk].agent} for dk in node.depends_on if dk in by_key]
    msg = TaskMessage(
        from_agent="kaptan", to_agent=node.agent, trace_id=UUID(task.id), skill=node.skill,
        timestamp=int(time.time()),
        payload=TaskPayload(goal=task.goal, inputs=inputs, node_role=node.node_role,
                            snapshot=snapshot, node_history=node_history,
                            node_kind=node.node_kind, tool=node.tool, tool_args=node.tool_args or {}),
    )
    node.msg_id = str(msg.message_id)
    node.status = "running"
    subject = Subject.TOOL_REQUEST.value if node.node_kind == "tool" else Subject.TASK_CREATED.value
    await js.publish(subject, msg.model_dump_json(by_alias=True).encode())


async def _on_critic_done(s, js, task: Task, critic: TaskNode, payload: dict) -> None:
    """Refinement controller — forward expansion (literal cycle YOK)."""
    inputs = task.inputs or {}
    threshold = float(inputs.get("accept_threshold", 0.9))
    min_delta = float(inputs.get("min_improvement_delta", 0.05))
    max_depth = int(inputs.get("max_refinement_depth", 0))
    max_nodes = int(inputs.get("max_dynamic_nodes", 20))
    group, depth = critic.refine_group, critic.refine_depth

    # critic'in critique event'inden score
    score = 0.0
    for ev in payload.get("events", []) or []:
        if ev.get("type") == "critique":
            score = float(ev.get("payload", {}).get("score", 0.0))
            break

    # producer fingerprint (orchestrator-side, agent'a güvenmeden)
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task.id))).scalars().all()
    by_key = {n.node_key: n for n in nodes}
    prod = next((by_key[d] for d in critic.depends_on if d in by_key and by_key[d].node_role != "critic"), None)
    snap = await s.get(TaskContextSnapshot, task.id)
    content = None
    if prod and snap:
        content = (snap.snapshot.get("agents", {}).get(prod.agent, {}).get("artifacts", {}).get(prod.node_key) or {}).get("content")
    producer_fp = _fp(task.goal, content)

    hist = await _refinement_history(s, task.id, group)
    prev_score = hist[-1]["score"] if hist else None
    seen_fps = {h.get("fingerprint") for h in hist}
    delta = (score - prev_score) if prev_score is not None else None
    node_count = len(nodes)

    if score >= threshold:
        decision = "accept"
    elif prev_score is not None and delta is not None and delta < min_delta:
        decision = "converged"   # stagnation
    elif producer_fp in seen_fps:
        decision = "converged"   # fingerprint repeat
    elif depth + 1 > max_depth:
        decision = "max_depth"
    elif node_count >= max_nodes:
        decision = "node_cap"
    else:
        decision = "refine"

    await _append_event(s, task.id, "refinement", critic.agent, critic.node_key, {
        "group": group, "iteration": depth, "score": score, "previous_score": prev_score,
        "delta": delta, "fingerprint": producer_fp, "decision": decision,
    })
    print(f"[refine] group={group} iter={depth} score={score} prev={prev_score} delta={delta} decision={decision}", flush=True)

    if decision == "refine":
        nd = depth + 1
        pkey, ckey = f"{group}#r{nd}p", f"{group}#r{nd}c"
        skill = prod.skill if prod else critic.skill
        s.add(TaskNode(id=str(uuid4()), task_id=task.id, node_key=pkey, agent=route(skill), skill=skill,
                       depends_on=[critic.node_key], status="pending", node_role="producer",
                       refine_group=None, refine_depth=nd, retry_policy=critic.retry_policy,
                       max_retries=critic.max_retries, retry_history=[]))
        s.add(TaskNode(id=str(uuid4()), task_id=task.id, node_key=ckey, agent=critic.agent, skill=critic.skill,
                       depends_on=[pkey], status="pending", node_role="critic",
                       refine_group=group, refine_depth=nd, retry_policy=critic.retry_policy,
                       max_retries=critic.max_retries, retry_history=[]))
        # critic'e bağlı pending downstream'leri yeni critic'e re-point
        for n in nodes:
            if n.status == "pending" and critic.node_key in (n.depends_on or []):
                n.depends_on = [ckey if d == critic.node_key else d for d in n.depends_on]
    await s.flush()
    await context_reducer.apply(s, task.id)


async def _refinement_history(s, task_id: str, group: str) -> list[dict]:
    rows = (await s.execute(
        select(TaskContextEvent).where(TaskContextEvent.task_id == task_id, TaskContextEvent.type == "refinement")
        .order_by(TaskContextEvent.seq)
    )).scalars().all()
    return [r.payload for r in rows if r.payload.get("group") == group]


async def _group_terminal(s, task_id: str, group: str) -> bool:
    hist = await _refinement_history(s, task_id, group)
    return any(h.get("decision") in REFINE_TERMINAL for h in hist)


async def _dispatch_ready(s, js, task_id: str) -> None:
    """Invariant: bir node dispatch edilebilir ⇔ tüm bağımlılıkları 'done' VE
    refine-critic bağımlılıklarının refine_group'u terminal (synthesizer gating)."""
    task = await s.get(Task, task_id)
    nodes = (await s.execute(select(TaskNode).where(TaskNode.task_id == task_id))).scalars().all()
    by_key = {n.node_key: n for n in nodes}
    done = {n.node_key for n in nodes if n.status == "done"}
    for n in nodes:
        if n.status != "pending" or not (set(n.depends_on) <= done):
            continue
        # synthesizer gating: non-terminal refine zincirine bağlı DIŞ node'lar bekler.
        # Zincir-içi node'lar (rev producer/critic) muaf — yoksa zincir ilerleyemez.
        blocked = False
        for dk in n.depends_on:
            dep = by_key.get(dk)
            if dep and dep.node_role == "critic" and dep.refine_group:
                g = dep.refine_group
                chain_internal = (n.refine_group == g) or n.node_key.startswith(f"{g}#")
                if not chain_internal and not await _group_terminal(s, task_id, g):
                    blocked = True
                    break
        if not blocked:
            await _dispatch_node(s, js, task, n)


async def _schedule_retry(node: TaskNode, error_code: str, last_error: str, *, retry_after: int | None = None) -> None:
    if error_code != "RATE_LIMIT":
        node.retry_count += 1  # RATE_LIMIT retry_count arttırmaz (GR-2, INV-5)
    node.status = "scheduled"
    node.error_code = error_code
    node.last_error = last_error
    node.failed_at = _now()
    if retry_after is not None:
        delay = float(retry_after)
    else:
        delay = _retry_delay(node.retry_policy, node.retry_count)
    node.retry_at = _now() + timedelta(seconds=delay)
    hist = list(node.retry_history or [])
    hist.append({"attempt": node.retry_count, "error_code": error_code, "at": _now().isoformat(), "next_delay_s": round(delay, 2)})
    node.retry_history = hist
    _metrics["retries_scheduled_total"] += 1
    print(f"[retry] node={node.node_key} attempt={node.retry_count} code={error_code} next_delay={delay:.2f}s", flush=True)


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


async def _on_node_failed(s, js, task: Task, node: TaskNode, error_code: str, last_error: str,
                           retry_after: int | None = None) -> None:
    non_retryable = error_code in NON_RETRYABLE
    if error_code == "RATE_LIMIT":
        # RATE_LIMIT: retry_count artmaz, retry_after kullanılır (GR-2, INV-5)
        rate_limit_count = sum(1 for h in (node.retry_history or []) if h.get("error_code") == "RATE_LIMIT")
        if rate_limit_count >= node.max_retries:
            await _dead_letter(s, js, task, node, error_code, last_error)
        else:
            await _schedule_retry(node, error_code, last_error, retry_after=retry_after)
    elif node.retry_policy == "manual" or non_retryable or node.retry_count >= node.max_retries:
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
        if task.status != "done":  # transition (bir kez)
            task.status = "done"
            task.result = {n.node_key: (n.result or {}) for n in nodes}
            # v0.8 — memory store + retrieval feedback (best-effort)
            try:
                snap = await s.get(TaskContextSnapshot, task_id)
                snapshot = snap.snapshot if snap else {}
                mids = (task.inputs or {}).get("_memory_ids", []) or []
                await memory.store(s, task, snapshot, parent_memory_ids=mids)
                if mids and (task.inputs or {}).get("_planner_source") == "llm":
                    await memory.mark_reuse_success(s, mids)
            except Exception as e:  # noqa: BLE001
                print(f"[memory] finalize store hata: {e}", flush=True)
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
            if env.get("type") == "result":   # success (task/tool sonucu)
                node.status = "done"
                payload = env.get("payload", {})
                node.result = payload
                # v0.9 — tool sonucu context'e artifact olarak
                if node.node_kind == "tool":
                    await _append_event(s, node.task_id, "artifact.created", node.agent, node.node_key,
                                        {"kind": "tool_result", "tool": node.tool, "content": payload.get("result", {})},
                                        exec_id=node.exec_id)
                # v0.7 — ajanın ürettiği context event'leri
                for ev in payload.get("events", []) or []:
                    await _append_event(s, node.task_id, ev.get("type", "artifact.created"),
                                        ev.get("agent") or node.agent, node.node_key,
                                        ev.get("payload", {}), exec_id=node.exec_id)
                await s.flush()
                await context_reducer.apply(s, node.task_id)
                await _emit_event(js, "context.updated", node.task_id, node.agent or "?", 0)
                # v0.7.1 — refine-enabled reasoning critic
                if (node.node_kind == "reasoning" and node.node_role == "critic" and node.refine_group
                        and int((task.inputs or {}).get("max_refinement_depth", 0)) > 0):
                    await _on_critic_done(s, js, task, node, payload)
            else:
                code = env.get("error_code") or "UNKNOWN"
                retry_after = None
                if code == "RATE_LIMIT":
                    payload = env.get("payload") or {}
                    retry_after = payload.get("retry_after")
                await _on_node_failed(s, js, task, node, code, env.get("message") or "hata",
                                     retry_after=retry_after)
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


async def approve_node(js, task_id: str, node_key: str, actor: str = "anonymous") -> dict:
    """Approval node'u (node-seviye HITL) onaylar → done → downstream serbest."""
    async with _lock:
        async with SessionLocal() as s:
            node = (await s.execute(
                select(TaskNode).where(TaskNode.task_id == task_id, TaskNode.node_key == node_key)
            )).scalars().first()
            if node is None:
                return {"error": "not_found"}
            if node.node_kind != "approval" or node.status != "awaiting_approval":
                return {"error": "invalid_state", "status": node.status}
            node.status = "done"
            node.approved_by = actor
            node.approved_at = _now()
            node.result = {"approved": True, "by": actor}
            await s.flush()
            await _dispatch_ready(s, js, task_id)
            await _finalize(s, task_id)
            await _emit_event(js, "node.approved", task_id, actor, 0)
            await s.commit()
            return {"task_id": task_id, "node": node_key, "status": "approved"}


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
