"""Builder HTTP API — v2.1 Workspace Runtime (port 8003).

artifact → assemble → validate → persist (workspace + build kaydı + manifest).
Gerçek exec YOK (sandbox v2.2). Build = task'tan türeyen kaynak.
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select

from . import ASSEMBLER_VERSION
from . import assembler, snapshot
from .db import Build, SessionLocal
from .validator import VALIDATOR_VERSION, validate

CONTROL_PLANE_URL = os.environ.get("CONTROL_PLANE_URL", "http://control-plane:8000")
WORKSPACES = os.environ.get("WORKSPACES_DIR", "/workspaces")
_EXCLUDE = ("node_modules", ".next", "dist", "build", ".git")

app = FastAPI(title="Builder API", version=ASSEMBLER_VERSION)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "builder",
            "assembler": ASSEMBLER_VERSION, "validator": VALIDATOR_VERSION}


async def _fetch_task(task_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        t = (await c.get(f"{CONTROL_PLANE_URL}/tasks/{task_id}")).json()
        a = (await c.get(f"{CONTROL_PLANE_URL}/tasks/{task_id}/artifacts")).json()
    return {"task": t, "artifacts": a.get("artifacts", [])}


@app.post("/build/{task_id}")
async def build(task_id: str, stack: str = Query(default="nextjs-prisma-sqlite")) -> dict:
    data = await _fetch_task(task_id)
    artifacts = data["artifacts"]
    if not artifacts:
        raise HTTPException(400, "task'ta artifact yok (önce çalışması gerekir)")

    art_hashes = snapshot.artifact_hashes(artifacts)
    fp = snapshot.fingerprint(art_hashes)

    async with SessionLocal() as s:
        # Idempotency: aynı (task_id, fingerprint) → mevcut kaydı döndür
        existing = (await s.execute(
            select(Build).where(Build.task_id == task_id, Build.build_fingerprint == fp)
        )).scalar_one_or_none()
        if existing:
            return {**existing.as_dict(), "deduped": True}

        # build_number = task içi monotonik
        from sqlalchemy import func as sqlfunc
        count = (await s.execute(
            select(sqlfunc.count()).select_from(Build).where(Build.task_id == task_id)
        )).scalar() or 0
        build_number = count + 1

    build_id = snapshot.new_build_id()
    out = os.path.join(WORKSPACES, build_id)
    app_name = f"app-{task_id[:8]}"

    stats = assembler.assemble(artifacts, out, stack, app_name)
    vres = validate(out)
    snap = snapshot.dag_snapshot(data["task"], art_hashes)
    snapshot.write_manifest(out, build_id=build_id, build_fingerprint=fp,
                            build_number=build_number, task_id=task_id, validator_result=vres)

    status = "validated" if vres["status"] == "passed" else "failed"
    rec = Build(
        build_id=build_id, build_fingerprint=fp, task_id=task_id, build_number=build_number,
        stack=stack, status=status, dag_snapshot=snap,
        assembler_version=ASSEMBLER_VERSION, validator_version=VALIDATOR_VERSION,
        validator_result=vres, file_count=stats["file_count"], workspace_path=out,
    )
    async with SessionLocal() as s:
        s.add(rec)
        await s.commit()
    return {**rec.as_dict(), "deduped": False, "added_deps": stats["added_deps"]}


@app.get("/builds")
async def list_builds(task_id: str = Query(...)) -> dict:
    async with SessionLocal() as s:
        rows = (await s.execute(
            select(Build).where(Build.task_id == task_id).order_by(Build.build_number.desc())
        )).scalars().all()
    return {"count": len(rows), "builds": [r.as_dict() for r in rows]}


def _file_tree(build_id: str) -> list[dict]:
    """Dosya ağacını MANIFEST'ten üretir (DB değil)."""
    import json
    mpath = os.path.join(WORKSPACES, build_id, ".build_manifest.json")
    if not os.path.exists(mpath):
        return []
    with open(mpath) as f:
        return json.load(f).get("files", [])


@app.get("/builds/{build_id}")
async def get_build(build_id: str) -> dict:
    async with SessionLocal() as s:
        rec = await s.get(Build, build_id)
    if rec is None:
        raise HTTPException(404, "build bulunamadı")
    return {**rec.as_dict(), "files": _file_tree(build_id)}


@app.get("/builds/{build_id}/file")
async def get_file(build_id: str, path: str = Query(...)) -> dict:
    safe = os.path.normpath(path).lstrip("/.")
    full = os.path.join(WORKSPACES, build_id, safe)
    real_root = os.path.realpath(os.path.join(WORKSPACES, build_id))
    if not os.path.realpath(full).startswith(real_root) or not os.path.isfile(full):
        raise HTTPException(404, "dosya bulunamadı")
    with open(full, errors="ignore") as f:
        return {"path": safe, "content": f.read()}
