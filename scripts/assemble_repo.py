#!/usr/bin/env python3
"""Project Assembler (v2.0-B) — artifact'ları çalıştırılabilir Next.js+Prisma repo'suna çevirir.

Deterministik (LLM yok). Dört katman:
  1. Workspace      — stack scaffold'ı yerleştir (render)
  2. File placement — ajan dosyalarını namespace kurallarıyla yaz
  3. Dep Synthesizer— 2-faz (import çıkar + rule-based resolve) → package.json deps
  4. Entry verify   — prisma şema birleştir (tek-kaynak), .env, README

Kullanım:
    python3 scripts/assemble_repo.py <task_id> [--cp http://localhost:8000]
                                     [--stack nextjs-prisma-sqlite] [--out generated]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STACKS = os.path.join(HERE, "config", "stacks")

# Scaffold'un sahibi olduğu, ajanların ezemeyeceği altyapı dosyaları
PROTECTED = {
    "package.json", "tsconfig.json", "next.config.mjs",
    "app/layout.tsx", "app/globals.css", "lib/prisma.ts",
    "prisma/schema.prisma", ".env", ".env.example",
}
# Ajan dosyalarının izinli kök namespace'leri
ALLOWED_PREFIXES = ("app/", "lib/", "prisma/", "components/")


def fetch_artifacts(cp: str, task_id: str) -> list[dict]:
    with urllib.request.urlopen(f"{cp}/tasks/{task_id}/artifacts", timeout=30) as r:
        return json.load(r).get("artifacts", [])


def _app_name(task_id: str) -> str:
    return f"app-{task_id[:8]}"


# ----------------------------------------------------------------- 1. workspace
def lay_scaffold(stack_dir: str, out: str, app_name: str) -> dict:
    meta = json.load(open(os.path.join(stack_dir, "_meta.json")))
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
            body = open(src).read().replace("__APP_NAME__", app_name)
            open(dest, "w").write(body)
    # .env (db push için gerekli) — .env.example'dan
    ex = os.path.join(out, ".env.example")
    if os.path.exists(ex) and not os.path.exists(os.path.join(out, ".env")):
        shutil.copy(ex, os.path.join(out, ".env"))
    return meta


# --------------------------------------------------------------- 2. placement
def place_files(artifacts: list[dict], out: str) -> tuple[list[str], list[str], list[str]]:
    written, skipped, prisma_models = [], [], []
    for a in artifacts:
        files = (a.get("content") or {}).get("files") or {}
        for path, body in files.items():
            safe = os.path.normpath(path).lstrip("/.").replace("\\", "/")
            # prisma model parçaları → schema birleştirmeye gider, ayrı dosya yazma
            if safe.startswith("prisma/") and safe.endswith(".prisma"):
                prisma_models.append(str(body))
                continue
            if not safe.startswith(ALLOWED_PREFIXES):
                skipped.append(f"{safe} (namespace dışı)")
                continue
            if safe in PROTECTED:
                skipped.append(f"{safe} (korumalı scaffold)")
                continue
            dest = os.path.join(out, safe)
            if os.path.exists(dest) and safe in written:
                skipped.append(f"{safe} (çakışma, ilk yazan korundu)")
                continue
            os.makedirs(os.path.dirname(dest) or out, exist_ok=True)
            open(dest, "w").write(str(body))
            written.append(safe)
    return written, skipped, prisma_models


# ------------------------------------------------------- 3. schema (tek-kaynak)
_MODEL_RE = re.compile(r"(model\s+\w+\s*\{.*?\})", re.DOTALL)


def merge_schema(out: str, prisma_models: list[str]) -> int:
    schema_path = os.path.join(out, "prisma", "schema.prisma")
    base = open(schema_path).read()
    blocks: list[str] = []
    for raw in prisma_models:
        # datasource/generator'ı at (scaffold'da var), sadece model bloklarını al
        blocks += _MODEL_RE.findall(raw)
    merged = "\n\n".join(b.strip() for b in blocks)
    base = base.replace("// __MODELS__", merged if merged else "// (model yok)")
    open(schema_path, "w").write(base)
    return len(blocks)


# ------------------------------------------------ 4. dependency synthesizer
_IMPORT_RES = [
    re.compile(r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)"""),
]


def _extract_imports(out: str) -> set[str]:
    specs: set[str] = set()
    for dp, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", "dist", "build", ".git")]
        for fn in files:
            if not fn.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs")):
                continue
            txt = open(os.path.join(dp, fn), errors="ignore").read()
            for rx in _IMPORT_RES:
                specs.update(rx.findall(txt))
    return specs


def _resolve_pkg(spec: str, meta: dict) -> str | None:
    """RULE-BASED resolver. Dış paket adını döner; internal/builtin ise None."""
    if spec.startswith(tuple(meta["internal_prefixes"])):
        return None
    root = spec.split("/")[0]
    if spec.startswith("@"):                      # scoped: @a/b
        parts = spec.split("/")
        root = "/".join(parts[:2]) if len(parts) >= 2 else parts[0]
    if root in set(meta["node_builtins"]) or spec.startswith("node:"):
        return None
    if root == "next" or spec.startswith("next/"):
        return "next"
    return root


def synth_deps(out: str, meta: dict) -> dict:
    pkg_path = os.path.join(out, "package.json")
    pkg = json.load(open(pkg_path))
    deps = dict(meta["base_deps"]); deps.update(pkg.get("dependencies", {}))
    vmap = meta.get("version_map", {})
    base_set = set(meta["base_deps"]) | set(meta["base_dev_deps"])
    added = {}
    for spec in _extract_imports(out):
        pkg_name = _resolve_pkg(spec, meta)
        if not pkg_name or pkg_name in base_set or pkg_name in deps:
            continue
        deps[pkg_name] = vmap.get(pkg_name, "latest")
        added[pkg_name] = deps[pkg_name]
    pkg["dependencies"] = dict(sorted(deps.items()))
    json.dump(pkg, open(pkg_path, "w"), indent=2)
    return added


# --------------------------------------------------------------- 4b. entry/readme
def finalize(out: str, app_name: str, stats: dict) -> None:
    # eksik app/page.tsx → minimal index
    page = os.path.join(out, "app", "page.tsx")
    if not os.path.exists(page):
        os.makedirs(os.path.dirname(page), exist_ok=True)
        open(page, "w").write(
            'export default function Home() {\n'
            f'  return <main><h1>{app_name}</h1><p>Agentic Takım tarafından üretildi.</p></main>;\n'
            '}\n'
        )
        stats["entry_injected"] = True
    readme = (
        f"# {app_name}\n\n"
        "Agentic Takım v2.0-B App Builder tarafından üretildi (Next.js + Prisma + SQLite).\n\n"
        "## Çalıştır\n```bash\nnpm install\nnpx prisma db push\nnpm run dev\n```\n"
        "→ http://localhost:3000\n"
    )
    open(os.path.join(out, "README.md"), "w").write(readme)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--cp", default="http://localhost:8000")
    ap.add_argument("--stack", default="nextjs-prisma-sqlite")
    ap.add_argument("--out", default="generated")
    args = ap.parse_args()

    stack_dir = os.path.join(STACKS, args.stack)
    if not os.path.isdir(stack_dir):
        print(f"✗ stack bulunamadı: {stack_dir}"); return 2
    out = os.path.join(args.out, args.task_id)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out, exist_ok=True)
    app_name = _app_name(args.task_id)

    meta = lay_scaffold(stack_dir, out, app_name)
    artifacts = fetch_artifacts(args.cp, args.task_id)
    written, skipped, prisma_models = place_files(artifacts, out)
    n_models = merge_schema(out, prisma_models)
    added = synth_deps(out, meta)
    stats = {}
    finalize(out, app_name, stats)

    print(f"✓ Repo üretildi → {out}/")
    print(f"  yazılan dosya: {len(written)} | atlanan: {len(skipped)} | prisma model: {n_models}")
    print(f"  eklenen bağımlılık: {added or '(yok)'}")
    if stats.get("entry_injected"):
        print("  · app/page.tsx yoktu → minimal index eklendi")
    if skipped:
        for s in skipped:
            print(f"    - atlandı: {s}")
    print(f"\n  Çalıştır:\n    cd {out} && npm install && npx prisma db push && npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
