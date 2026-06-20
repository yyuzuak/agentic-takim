"""Build Validator — STRICT deterministik gate (v2.0-B logic portu) + sürümleme.

validate(root) → {"version", "status": "passed"|"failed", "hard", "soft", "issues"}.
VALIDATOR_VERSION değişince build_id de değişir (snapshot.py'de hesaba katılır).
"""
from __future__ import annotations

import json
import os
import re

VALIDATOR_VERSION = "1.0.0"

NODE_BUILTINS = {
    "fs", "path", "os", "crypto", "http", "https", "stream", "util", "url",
    "events", "buffer", "process", "child_process", "net", "zlib", "querystring",
    "assert", "timers", "string_decoder",
}
INTERNAL_PREFIXES = ("@/", "~/", "./", "../")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
_EXCLUDE = ("node_modules", ".next", "dist", "build", ".git")


def _walk(root, exts):
    out = []
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE]
        out += [os.path.join(dp, f) for f in files if f.endswith(exts)]
    return out


def _imports(txt):
    res = []
    for rx in (r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""",
               r"""require\(\s*['"]([^'"]+)['"]\s*\)""",
               r"""import\(\s*['"]([^'"]+)['"]\s*\)"""):
        res += re.findall(rx, txt)
    return res


def _resolve_local(spec, fromfile, root):
    if spec.startswith(("@/", "~/")):
        base = os.path.join(root, spec[2:])
    elif spec.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(fromfile), spec))
    else:
        return "EXTERNAL"
    for cand in (base, base + ".ts", base + ".tsx", base + ".js", base + ".jsx",
                 os.path.join(base, "index.ts"), os.path.join(base, "index.tsx"),
                 os.path.join(base, "route.ts")):
        if os.path.exists(cand):
            return cand
    return None


def validate(root: str) -> dict:
    issues: list[dict] = []

    def fail(level, cat, filep, msg):
        issues.append({"level": level, "cat": cat, "file": filep, "msg": msg})

    # package.json
    deps = set()
    p = os.path.join(root, "package.json")
    if not os.path.exists(p):
        fail("hard", "package", "package.json", "yok")
    else:
        try:
            pkg = json.load(open(p))
            deps = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
            for s in ("dev", "build"):
                if s not in pkg.get("scripts", {}):
                    fail("hard", "package", "package.json", f"script '{s}' eksik")
        except Exception as e:
            fail("hard", "package", "package.json", f"geçersiz JSON: {e}")

    # import graph
    for f in _walk(root, (".ts", ".tsx", ".js", ".jsx", ".mjs")):
        rel = os.path.relpath(f, root)
        for spec in _imports(open(f, errors="ignore").read()):
            if spec.startswith("node:") or spec.split("/")[0] in NODE_BUILTINS:
                continue
            if spec.startswith(INTERNAL_PREFIXES):
                if _resolve_local(spec, f, root) is None:
                    fail("hard", "import-graph", rel, f"yerel modül çözülemedi: {spec}")
            else:
                rp = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if rp not in deps:
                    fail("hard", "missing-dep", rel, f"paket deps'te yok: {rp}")

    # entry
    if not os.path.exists(os.path.join(root, "app", "layout.tsx")):
        fail("hard", "entry", "app/layout.tsx", "yok")
    if not [p for p in _walk(os.path.join(root, "app"), (".tsx",)) if os.path.basename(p) == "page.tsx"]:
        fail("hard", "entry", "app/", "hiç page.tsx yok")

    # routes
    routes = []
    for f in _walk(os.path.join(root, "app", "api"), (".ts",)):
        if os.path.basename(f) != "route.ts":
            continue
        rel = os.path.relpath(f, root)
        txt = open(f, errors="ignore").read()
        if not any(re.search(rf"export\s+(async\s+)?function\s+{m}\b", txt) or
                   re.search(rf"export\s+const\s+{m}\b", txt) for m in HTTP_METHODS):
            fail("hard", "route", rel, "hiç HTTP metodu export edilmemiş")
        routes.append("/" + os.path.relpath(os.path.dirname(f), root).replace("app/", "", 1))

    # prisma
    models: set[str] = set()
    sp = os.path.join(root, "prisma", "schema.prisma")
    if not os.path.exists(sp):
        fail("hard", "prisma", "prisma/schema.prisma", "yok")
    else:
        txt = open(sp).read()
        if "datasource" not in txt or "sqlite" not in txt:
            fail("hard", "prisma", "schema.prisma", "datasource sqlite eksik")
        if "generator" not in txt:
            fail("hard", "prisma", "schema.prisma", "generator client eksik")
        ms = re.findall(r"model\s+(\w+)\s*\{(.*?)\}", txt, re.DOTALL)
        if not ms:
            fail("hard", "prisma", "schema.prisma", "hiç model yok")
        seen = set()
        for name, body in ms:
            if name in seen:
                fail("hard", "prisma", "schema.prisma", f"model adı tekrarı: {name}")
            seen.add(name)
            if "@id" not in body:
                fail("hard", "prisma", "schema.prisma", f"model '{name}' @id içermiyor")
        models = set(seen)

    # semantik: route→model
    lower = {m.lower() for m in models}
    for f in _walk(os.path.join(root, "app", "api"), (".ts",)):
        if os.path.basename(f) != "route.ts":
            continue
        rel = os.path.relpath(f, root)
        for used in re.findall(r"prisma\.(\w+)\b", open(f, errors="ignore").read()):
            if used.lower() not in lower:
                fail("hard", "route→model", rel, f"prisma.{used} şemada yok")

    # semantik: fetch→endpoint
    routeset = set(routes)
    for f in _walk(os.path.join(root, "app"), (".tsx", ".ts")):
        rel = os.path.relpath(f, root)
        for url in re.findall(r"""fetch\(\s*[`'"](/api/[^`'"?]+)""", open(f, errors="ignore").read()):
            clean = "/" + "/".join(x for x in url.strip("/").split("/") if not x.startswith("$") and "{" not in x)
            if clean not in routeset and not any(clean.startswith(r) for r in routeset):
                fail("hard", "fetch→endpoint", rel, f"fetch hedefi yok: {url}")

    # semantik: model kullanımı (soft)
    api_txt = "".join(open(f, errors="ignore").read()
                      for f in _walk(os.path.join(root, "app", "api"), (".ts",)))
    used = {u.lower() for u in re.findall(r"prisma\.(\w+)\b", api_txt)}
    for m in models:
        if m.lower() not in used:
            fail("soft", "model-kullanımı", "schema.prisma", f"model '{m}' hiçbir route'ta kullanılmıyor")

    hard = [i for i in issues if i["level"] == "hard"]
    soft = [i for i in issues if i["level"] == "soft"]
    return {
        "version": VALIDATOR_VERSION,
        "status": "passed" if not hard else "failed",
        "hard": len(hard), "soft": len(soft), "issues": issues,
    }
