"""Runner — read-only workspace'i /tmp'ye kopyalar, build aşamalarını subprocess çalıştırır.

Aşamalar: npm install → npx prisma db push → npm run build. İlk hatada durur.
Stateless: DB yok, sonuç dict döner (control-plane persist eder). /tmp bitince temizlenir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

from . import errors

WORKSPACES = os.environ.get("WORKSPACES_DIR", "/workspaces")
TMP_ROOT = os.environ.get("SANDBOX_TMP", "/tmp/run")
_EXCLUDE = {"node_modules", ".next", ".git", "dist", "build"}

# (key, aşama adı, komut, timeout sn)
_STAGES = [
    ("install", "npm_install", ["npm", "install", "--no-audit", "--no-fund"], 180),
    ("prisma", "prisma", ["npx", "prisma", "db", "push", "--skip-generate", "--accept-data-loss"], 60),
    ("build", "build", ["npm", "run", "build"], 300),
]
_LOG_TAIL_LINES = 80


def _copy_source(build_id: str, dest: str) -> None:
    src = os.path.join(WORKSPACES, build_id)
    if not os.path.isdir(src):
        raise FileNotFoundError(f"workspace yok: {src}")
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*_EXCLUDE))


def _tail(text: str, n: int = _LOG_TAIL_LINES) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n:])


def run_build(build_id: str) -> dict:
    """Bir build'i çalıştırır. {status, stage, *_ok, duration_s, errors[], log_tail} döner."""
    run_id = "run_" + uuid.uuid4().hex[:12]
    work = os.path.join(TMP_ROOT, run_id)
    os.makedirs(TMP_ROOT, exist_ok=True)
    started = time.monotonic()
    result = {
        "run_id": run_id, "status": "passed", "stage": "done",
        "install_ok": False, "prisma_ok": False, "build_ok": False,
        "duration_s": 0.0, "errors": [], "log_tail": "",
    }
    try:
        _copy_source(build_id, work)
        # .env yoksa DATABASE_URL ver (prisma db push için)
        env = {**os.environ, "DATABASE_URL": "file:./dev.db", "CI": "1",
               "NEXT_TELEMETRY_DISABLED": "1"}
        for key, phase, cmd, timeout in _STAGES:
            try:
                proc = subprocess.run(
                    cmd, cwd=work, env=env, capture_output=True, text=True, timeout=timeout,
                )
            except subprocess.TimeoutExpired as e:
                out = (e.stdout or "") + (e.stderr or "")
                result.update(status="failed", stage=key,
                              errors=[errors.timeout_error(phase, timeout)],
                              log_tail=_tail(out if isinstance(out, str) else ""))
                return _finish(result, started)
            log = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if proc.returncode != 0:
                result.update(status="failed", stage=key,
                              errors=errors.extract(phase, log), log_tail=_tail(log))
                return _finish(result, started)
            result[f"{key}_ok"] = True
        result["log_tail"] = "build başarılı"
        return _finish(result, started)
    except Exception as e:  # noqa: BLE001
        result.update(status="failed", stage="setup",
                      errors=[{"phase": "setup", "category": "sandbox_error",
                               "file": None, "message": str(e)[:300], "severity": "error"}])
        return _finish(result, started)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _finish(result: dict, started: float) -> dict:
    result["duration_s"] = round(time.monotonic() - started, 2)
    return result
