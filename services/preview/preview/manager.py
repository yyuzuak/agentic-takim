"""Tek-slot preview yöneticisi — üretilen uygulamanın canlı dev server'ı.

In-memory tek aktif preview: workspace (ro) → /tmp kopya → npm install + prisma db push +
(seed) → `npm run dev` (background, ayakta kalır). DB yok. Yeni preview öncekini durdurur.
TTL auto-stop ile kaynak korunur.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time

WORKSPACES = os.environ.get("WORKSPACES_DIR", "/workspaces")
TMP = os.environ.get("PREVIEW_TMP", "/tmp/preview")
DEV_PORT = int(os.environ.get("PREVIEW_DEV_PORT", "3100"))
TTL_S = int(os.environ.get("PREVIEW_TTL_S", "1200"))  # 20 dk
_EXCLUDE = {"node_modules", ".next", ".git", "dist", "build"}
_INSTALL_TIMEOUT = 240

_lock = threading.Lock()
_state: dict = {
    "active": False, "build_id": None, "status": "stopped",  # starting|running|failed|stopped
    "url": None, "log": "", "started_at": None, "proc": None, "ttl_timer": None,
}


def _log(msg: str) -> None:
    _state["log"] = (_state["log"] + msg)[-6000:]


def status() -> dict:
    return {k: _state[k] for k in ("active", "build_id", "status", "url", "started_at")} | {
        "log_tail": "\n".join(_state["log"].splitlines()[-60:]),
    }


def stop() -> dict:
    with _lock:
        _kill_locked()
        _state.update(active=False, status="stopped", build_id=None, url=None)
    return status()


def _kill_locked() -> None:
    t = _state.get("ttl_timer")
    if t:
        t.cancel()
        _state["ttl_timer"] = None
    proc = _state.get("proc")
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
    _state["proc"] = None
    shutil.rmtree(TMP, ignore_errors=True)


def start(build_id: str, public_url: str) -> dict:
    with _lock:
        _kill_locked()
        _state.update(active=True, build_id=build_id, status="starting", url=public_url,
                      log="", started_at=time.time())
    threading.Thread(target=_run, args=(build_id,), daemon=True).start()
    return status()


def _run(build_id: str) -> None:
    src = os.path.join(WORKSPACES, build_id)
    try:
        if not os.path.isdir(src):
            raise FileNotFoundError(f"workspace yok: {src}")
        shutil.rmtree(TMP, ignore_errors=True)
        shutil.copytree(src, TMP, ignore=shutil.ignore_patterns(*_EXCLUDE))
        env = {**os.environ, "DATABASE_URL": "file:./dev.db", "CI": "1",
               "NEXT_TELEMETRY_DISABLED": "1"}

        for label, cmd in [
            ("npm install", ["npm", "install", "--no-audit", "--no-fund"]),
            ("prisma db push", ["npx", "prisma", "db", "push", "--skip-generate", "--accept-data-loss"]),
        ]:
            _log(f"\n$ {label}\n")
            p = subprocess.run(cmd, cwd=TMP, env=env, capture_output=True, text=True, timeout=_INSTALL_TIMEOUT)
            _log((p.stdout or "")[-2000:] + (p.stderr or "")[-2000:])
            if p.returncode != 0:
                _fail(f"{label} başarısız")
                return
        # seed best-effort (hata yutulur)
        try:
            subprocess.run(["npm", "run", "db:seed"], cwd=TMP, env=env,
                           capture_output=True, text=True, timeout=60)
        except Exception:
            pass

        _log("\n$ npm run dev\n")
        proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "-p", str(DEV_PORT), "-H", "0.0.0.0"],
            cwd=TMP, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, start_new_session=True,
        )
        with _lock:
            if not _state["active"] or _state["build_id"] != build_id:
                proc.kill(); return  # bu sırada başka preview başladı
            _state["proc"] = proc
            _state["ttl_timer"] = threading.Timer(TTL_S, stop)
            _state["ttl_timer"].daemon = True
            _state["ttl_timer"].start()
        # stdout izle: "Ready" görünce running
        for line in proc.stdout:  # type: ignore
            _log(line)
            if ("Ready in" in line or "Local:" in line) and _state["status"] == "starting":
                with _lock:
                    if _state["build_id"] == build_id:
                        _state["status"] = "running"
        # dev server çıktıysa
        with _lock:
            if _state["build_id"] == build_id and _state["status"] != "stopped":
                _state["status"] = "stopped"
                _state["active"] = False
    except subprocess.TimeoutExpired:
        _fail("kurulum timeout")
    except Exception as e:  # noqa: BLE001
        _fail(str(e))


def _fail(msg: str) -> None:
    _log(f"\n[HATA] {msg}\n")
    with _lock:
        _state.update(status="failed", active=False)
