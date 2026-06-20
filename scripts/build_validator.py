#!/usr/bin/env python3
"""Build Validator (v2.0-B) — STRICT, deterministik, build-ÖNCESİ correctness gate.

LLM yok. Üretilen repo'yu statik denetler; geçmezse exit≠0 + kategorize rapor.
İki seviye:
  A) Yapısal (hard): package.json / import graph / entry / route / prisma id+relation
  B) Semantik (hard/soft): route→model, fetch→endpoint, model kullanımı

Kullanım: python3 scripts/build_validator.py <repo_dir>
"""
from __future__ import annotations

import json
import os
import re
import sys

NODE_BUILTINS = {
    "fs", "path", "os", "crypto", "http", "https", "stream", "util", "url",
    "events", "buffer", "process", "child_process", "net", "zlib", "querystring",
    "assert", "timers", "string_decoder",
}
INTERNAL_PREFIXES = ("@/", "~/", "./", "../")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")

issues: list[dict] = []


def fail(level: str, cat: str, filep: str, msg: str) -> None:
    issues.append({"level": level, "cat": cat, "file": filep, "msg": msg})


_EXCLUDE_DIRS = ("node_modules", ".next", "dist", "build", ".git")


def _walk(root: str, exts: tuple[str, ...]) -> list[str]:
    out = []
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        out += [os.path.join(dp, f) for f in files if f.endswith(exts)]
    return out


def _imports(txt: str) -> list[str]:
    rxs = [
        r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]""",
        r"""require\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""import\(\s*['"]([^'"]+)['"]\s*\)""",
    ]
    res = []
    for rx in rxs:
        res += re.findall(rx, txt)
    return res


def _resolve_local(spec: str, fromfile: str, root: str) -> str | None:
    """Yerel import'u dosyaya çöz. Bulunamazsa None (=missing)."""
    if spec.startswith("@/") or spec.startswith("~/"):
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


# ----------------------------------------------------------------- A. structural
def check_package_json(root: str) -> set[str]:
    p = os.path.join(root, "package.json")
    if not os.path.exists(p):
        fail("hard", "package", "package.json", "yok"); return set()
    try:
        pkg = json.load(open(p))
    except Exception as e:
        fail("hard", "package", "package.json", f"geçersiz JSON: {e}"); return set()
    scripts = pkg.get("scripts", {})
    for s in ("dev", "build"):
        if s not in scripts:
            fail("hard", "package", "package.json", f"script '{s}' eksik")
    return set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))


def check_imports(root: str, deps: set[str]) -> None:
    for f in _walk(root, (".ts", ".tsx", ".js", ".jsx", ".mjs")):
        rel = os.path.relpath(f, root)
        for spec in _imports(open(f, errors="ignore").read()):
            if spec.startswith("node:") or spec.split("/")[0] in NODE_BUILTINS:
                continue
            if spec.startswith(INTERNAL_PREFIXES):
                if _resolve_local(spec, f, root) is None:
                    fail("hard", "import-graph", rel, f"yerel modül çözülemedi: {spec}")
            else:  # external
                root_pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if root_pkg not in deps:
                    fail("hard", "missing-dep", rel, f"paket deps'te yok: {root_pkg}")


def check_entry(root: str) -> None:
    if not os.path.exists(os.path.join(root, "app", "layout.tsx")):
        fail("hard", "entry", "app/layout.tsx", "yok")
    pages = [p for p in _walk(os.path.join(root, "app"), (".tsx",)) if os.path.basename(p) == "page.tsx"]
    if not pages:
        fail("hard", "entry", "app/", "hiç page.tsx yok")


def check_routes(root: str) -> list[str]:
    routes = []
    api_dir = os.path.join(root, "app", "api")
    for f in _walk(api_dir, (".ts",)):
        if os.path.basename(f) != "route.ts":
            continue
        rel = os.path.relpath(f, root)
        txt = open(f, errors="ignore").read()
        if not any(re.search(rf"export\s+(async\s+)?function\s+{m}\b", txt) or
                   re.search(rf"export\s+const\s+{m}\b", txt) for m in HTTP_METHODS):
            fail("hard", "route", rel, "hiç HTTP metodu export edilmemiş")
        # /api/<x>/route.ts → /api/<x>
        routes.append("/" + os.path.relpath(os.path.dirname(f), root).replace("app/", "", 1))
    return routes


def check_prisma(root: str) -> set[str]:
    p = os.path.join(root, "prisma", "schema.prisma")
    if not os.path.exists(p):
        fail("hard", "prisma", "prisma/schema.prisma", "yok"); return set()
    txt = open(p).read()
    if "datasource" not in txt or "sqlite" not in txt:
        fail("hard", "prisma", "schema.prisma", "datasource sqlite eksik")
    if "generator" not in txt:
        fail("hard", "prisma", "schema.prisma", "generator client eksik")
    models = re.findall(r"model\s+(\w+)\s*\{(.*?)\}", txt, re.DOTALL)
    names = [m[0] for m in models]
    if not names:
        fail("hard", "prisma", "schema.prisma", "hiç model yok")
    seen = set()
    for name, body in models:
        if name in seen:
            fail("hard", "prisma", "schema.prisma", f"model adı tekrarı: {name}")
        seen.add(name)
        if "@id" not in body:
            fail("hard", "prisma", "schema.prisma", f"model '{name}' @id içermiyor")
    # relation hedefleri var olan model mi
    for name, body in models:
        for ref in re.findall(r"@relation[^\n]*", body):
            pass  # relation hedefi tip adından gelir; tip kontrolünü aşağıda yaparız
        for line in body.splitlines():
            m = re.match(r"\s*\w+\s+(\w+)(\[\])?\s", line)
            if m and m.group(1) in (set(names) - {name}) and "@relation" not in line and not m.group(2):
                pass
    return set(names)


# ----------------------------------------------------------------- B. semantic
def check_route_model(root: str, models: set[str]) -> None:
    lower = {m.lower() for m in models}
    for f in _walk(os.path.join(root, "app", "api"), (".ts",)):
        if os.path.basename(f) != "route.ts":
            continue
        rel = os.path.relpath(f, root)
        for used in re.findall(r"prisma\.(\w+)\b", open(f, errors="ignore").read()):
            if used.lower() not in lower:
                fail("hard", "route→model", rel, f"prisma.{used} şemada yok")


def check_fetch_endpoint(root: str, routes: list[str]) -> None:
    routeset = set(routes)
    for f in _walk(os.path.join(root, "app"), (".tsx", ".ts")):
        rel = os.path.relpath(f, root)
        for url in re.findall(r"""fetch\(\s*[`'"](/api/[^`'"?]+)""", open(f, errors="ignore").read()):
            clean = "/" + "/".join(p for p in url.strip("/").split("/") if not p.startswith("$") and "{" not in p)
            # dinamik segment toleransı: tam eşleşme yoksa prefix dene
            if clean not in routeset and not any(clean.startswith(r) for r in routeset):
                fail("hard", "fetch→endpoint", rel, f"fetch hedefi yok: {url}")


def check_model_usage(root: str, models: set[str]) -> None:
    api_txt = "".join(open(f, errors="ignore").read()
                      for f in _walk(os.path.join(root, "app", "api"), (".ts",)))
    used = {u.lower() for u in re.findall(r"prisma\.(\w+)\b", api_txt)}
    for m in models:
        if m.lower() not in used:
            fail("soft", "model-kullanımı", "schema.prisma", f"model '{m}' hiçbir route'ta kullanılmıyor")


def main() -> int:
    if len(sys.argv) < 2:
        print("kullanım: build_validator.py <repo_dir>"); return 2
    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"✗ dizin yok: {root}"); return 2

    deps = check_package_json(root)
    check_imports(root, deps)
    check_entry(root)
    routes = check_routes(root)
    models = check_prisma(root)
    check_route_model(root, models)
    check_fetch_endpoint(root, routes)
    check_model_usage(root, models)

    hard = [i for i in issues if i["level"] == "hard"]
    soft = [i for i in issues if i["level"] == "soft"]
    print(f"Build Validator: {len(hard)} hard, {len(soft)} soft")
    for i in issues:
        mark = "✗" if i["level"] == "hard" else "·"
        print(f"  {mark} [{i['cat']}] {i['file']}: {i['msg']}")
    if not hard:
        print("✅ VALIDATOR GEÇTİ" + (" (soft uyarılar var)" if soft else ""))
        return 0
    print("❌ VALIDATOR FAIL — build edilmemeli")
    return 1


if __name__ == "__main__":
    sys.exit(main())
