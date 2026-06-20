"""Structured error extraction — ham build log'unu yapılandırılmış hatalara çevirir.

v2.2'nin merkezi: ajan/UI ham npm logu yerine {phase, category, file, message, severity}
görür. v3.0 autonomous repair'in girdisi bu olacak. Otomatik repair YOK — sadece teşhis.
"""
from __future__ import annotations

import re

# (regex, category, file_grup_no | None) — aşama bazlı pattern eşleme
_PATTERNS = {
    "npm_install": [
        (re.compile(r"npm error code E404"), "missing_dependency", None),
        (re.compile(r"404 Not Found.*'([^']+)'"), "missing_dependency", 1),
        (re.compile(r"Cannot find module ['\"]([^'\"]+)['\"]"), "missing_dependency", 1),
        (re.compile(r"npm error code ERESOLVE"), "dependency_conflict", None),
        (re.compile(r"npm error (.*)"), "npm_error", 1),
    ],
    "prisma": [
        (re.compile(r"Error validating model ['\"]?(\w+)"), "prisma_schema_error", 1),
        (re.compile(r"Error validating field ['\"]?(\w+)"), "prisma_schema_error", 1),
        (re.compile(r"The relation field .* is missing"), "prisma_relation_error", None),
        (re.compile(r"Error: (P\d+):?\s*(.*)"), "prisma_error", 2),
        (re.compile(r"Environment variable not found: (\w+)"), "prisma_env_error", 1),
    ],
    "build": [
        (re.compile(r"Module not found: Can't resolve ['\"]([^'\"]+)['\"]"), "missing_dependency", 1),
        (re.compile(r"Type error: (.*)"), "type_error", 1),
        (re.compile(r"Syntax error: (.*)"), "syntax_error", 1),
        (re.compile(r"Error: (.*) is not exported from"), "import_error", 1),
        (re.compile(r"ReferenceError: (.*)"), "reference_error", 1),
        (re.compile(r"Failed to compile"), "build_error", None),
    ],
}

# Next.js hata satırlarında dosya yolu: "./app/page.tsx:12:5"
_FILE_RE = re.compile(r"\.?/?((?:app|lib|prisma|components)/[\w./\-\[\]]+\.\w+)")


def extract(phase: str, log: str) -> list[dict]:
    """Bir aşamanın log'undan yapılandırılmış hata listesi. Eşleşme yoksa generic unknown."""
    out: list[dict] = []
    seen: set = set()
    file_hint = None
    m = _FILE_RE.search(log)
    if m:
        file_hint = m.group(1)

    for rx, category, grp in _PATTERNS.get(phase, []):
        for match in rx.finditer(log):
            msg = match.group(grp).strip() if grp else match.group(0).strip()
            key = (category, msg[:120])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "phase": phase, "category": category,
                "file": file_hint, "message": msg[:300], "severity": "error",
            })
            if len(out) >= 5:  # log spam'ini sınırla
                break
        if out:
            break  # ilk eşleşen kategori grubu yeterli (en spesifik önce)

    if not out:
        # eşleşme yok: son anlamlı satırı generic hata olarak ver
        lines = [l for l in log.strip().splitlines() if l.strip()]
        tail = lines[-1][:300] if lines else "bilinmeyen hata"
        out.append({"phase": phase, "category": "unknown", "file": file_hint,
                    "message": tail, "severity": "error"})
    return out


def timeout_error(phase: str, seconds: int) -> dict:
    return {"phase": phase, "category": "timeout", "file": None,
            "message": f"{phase} {seconds}s içinde tamamlanmadı (timeout)", "severity": "error"}
