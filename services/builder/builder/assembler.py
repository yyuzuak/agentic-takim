"""Assembler — artifact'ları çalıştırılabilir repo'ya çevirir (v2.0-B logic, runtime portu).

Deterministik (LLM yok). scripts/assemble_repo.py ile aynı 4 katman; burada artifact'lar
parametre olarak alınır (builder API çeker), çıktı verilen workspace dizinine yazılır.
"""
from __future__ import annotations

import json
import os
import re
import shutil

# config/ container imajına COPY'lenir (Dockerfile)
STACKS = "/app/config/stacks"

PROTECTED = {
    "package.json", "tsconfig.json", "next.config.mjs",
    "app/layout.tsx", "app/globals.css", "lib/prisma.ts",
    "prisma/schema.prisma", ".env", ".env.example",
}
ALLOWED_PREFIXES = ("app/", "lib/", "prisma/", "components/")
_EXCLUDE_DIRS = ("node_modules", ".next", "dist", "build", ".git")


def _meta(stack: str) -> dict:
    with open(os.path.join(STACKS, stack, "_meta.json")) as f:
        return json.load(f)


def _lay_scaffold(stack: str, out: str, app_name: str) -> None:
    stack_dir = os.path.join(STACKS, stack)
    for dirpath, _, files in os.walk(stack_dir):
        for fn in files:
            if fn == "_meta.json":
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, stack_dir)
            if rel == "package.json.tmpl":
                rel = "package.json"
            elif rel == "prisma/schema.prisma.base":
                rel = "prisma/schema.prisma"
            dest = os.path.join(out, rel)
            os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
            with open(src) as sf, open(dest, "w") as df:
                df.write(sf.read().replace("__APP_NAME__", app_name))
    ex = os.path.join(out, ".env.example")
    if os.path.exists(ex) and not os.path.exists(os.path.join(out, ".env")):
        shutil.copy(ex, os.path.join(out, ".env"))


def _place_files(artifacts: list[dict], out: str):
    written, skipped, prisma_models = [], [], []
    for a in artifacts:
        files = (a.get("content") or {}).get("files") or {}
        for path, body in files.items():
            safe = os.path.normpath(path).lstrip("/.").replace("\\", "/")
            if safe.startswith("prisma/") and safe.endswith(".prisma"):
                prisma_models.append(str(body)); continue
            if not safe.startswith(ALLOWED_PREFIXES):
                skipped.append(f"{safe} (namespace dışı)"); continue
            if safe in PROTECTED:
                skipped.append(f"{safe} (korumalı)"); continue
            if safe in written:
                skipped.append(f"{safe} (çakışma)"); continue
            dest = os.path.join(out, safe)
            os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
            with open(dest, "w") as df:
                df.write(str(body))
            written.append(safe)
    return written, skipped, prisma_models


_MODEL_RE = re.compile(r"(model\s+\w+\s*\{.*?\})", re.DOTALL)


def _merge_schema(out: str, prisma_models: list[str]) -> int:
    schema_path = os.path.join(out, "prisma", "schema.prisma")
    with open(schema_path) as f:
        base = f.read()
    blocks = []
    for raw in prisma_models:
        blocks += _MODEL_RE.findall(raw)
    base = base.replace("// __MODELS__", "\n\n".join(b.strip() for b in blocks) or "// (model yok)")
    with open(schema_path, "w") as f:
        f.write(base)
    return len(blocks)


_IMPORT_RES = [
    re.compile(r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)"""),
]


def _extract_imports(out: str) -> set[str]:
    specs: set[str] = set()
    for dp, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        for fn in files:
            if fn.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
                with open(os.path.join(dp, fn), errors="ignore") as f:
                    txt = f.read()
                for rx in _IMPORT_RES:
                    specs.update(rx.findall(txt))
    return specs


def _resolve_pkg(spec: str, meta: dict) -> str | None:
    if spec.startswith(tuple(meta["internal_prefixes"])):
        return None
    root = spec.split("/")[0]
    if spec.startswith("@"):
        parts = spec.split("/")
        root = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
    if root in set(meta["node_builtins"]) or spec.startswith("node:"):
        return None
    if root == "next" or spec.startswith("next/"):
        return "next"
    return root


def _synth_deps(out: str, meta: dict) -> dict:
    pkg_path = os.path.join(out, "package.json")
    with open(pkg_path) as f:
        pkg = json.load(f)
    deps = dict(meta["base_deps"]); deps.update(pkg.get("dependencies", {}))
    vmap = meta.get("version_map", {})
    base_set = set(meta["base_deps"]) | set(meta["base_dev_deps"])
    added = {}
    for spec in _extract_imports(out):
        name = _resolve_pkg(spec, meta)
        if not name or name in base_set or name in deps:
            continue
        deps[name] = vmap.get(name, "latest"); added[name] = deps[name]
    pkg["dependencies"] = dict(sorted(deps.items()))
    with open(pkg_path, "w") as f:
        json.dump(pkg, f, indent=2)
    return added


def _finalize(out: str, app_name: str) -> bool:
    page = os.path.join(out, "app", "page.tsx")
    injected = False
    if not os.path.exists(page):
        os.makedirs(os.path.dirname(page), exist_ok=True)
        with open(page, "w") as f:
            f.write(f'export default function Home() {{\n  return <main><h1>{app_name}</h1>'
                    f'<p>Agentic Takım tarafından üretildi.</p></main>;\n}}\n')
        injected = True
    with open(os.path.join(out, "README.md"), "w") as f:
        f.write(f"# {app_name}\n\nAgentic Takım App Builder (Next.js + Prisma + SQLite).\n\n"
                "## Çalıştır\n```bash\nnpm install\nnpx prisma db push\nnpm run dev\n```\n")
    return injected


def assemble(artifacts: list[dict], out: str, stack: str, app_name: str) -> dict:
    """artifact'ları workspace dizinine deterministik repo olarak yaz. İstatistik döner."""
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    meta = _meta(stack)
    _lay_scaffold(stack, out, app_name)
    written, skipped, prisma_models = _place_files(artifacts, out)
    n_models = _merge_schema(out, prisma_models)
    added = _synth_deps(out, meta)
    injected = _finalize(out, app_name)
    return {
        "written": written, "skipped": skipped, "models": n_models,
        "added_deps": added, "entry_injected": injected,
        "file_count": sum(1 for dp, ds, fs in os.walk(out)
                          if not any(x in dp for x in _EXCLUDE_DIRS) for _ in fs),
    }
