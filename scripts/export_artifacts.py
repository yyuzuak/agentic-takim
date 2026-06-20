#!/usr/bin/env python3
"""Bir görevin üretilen kod artifact'larını diske yazar (v2.0-B köprüsü).

Kullanım:
    python3 scripts/export_artifacts.py <task_id> [--cp http://localhost:8000] [--out generated]

Her artifact'taki `content.files` (yol→içerik) gerçek dosyalara yazılır:
    generated/<task_id>/<dosya yolu>
Markdown tasarım çıktıları da _docs/<node_key>.md olarak kaydedilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def fetch(cp: str, task_id: str) -> dict:
    with urllib.request.urlopen(f"{cp}/tasks/{task_id}/artifacts", timeout=30) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    ap.add_argument("--cp", default="http://localhost:8000")
    ap.add_argument("--out", default="generated")
    args = ap.parse_args()

    data = fetch(args.cp, args.task_id)
    root = os.path.join(args.out, args.task_id)
    os.makedirs(root, exist_ok=True)

    n_files = n_docs = 0
    for a in data.get("artifacts", []):
        content = a.get("content") or {}
        node = a.get("node_key", "node")
        # kod dosyaları
        for path, body in (content.get("files") or {}).items():
            safe = os.path.normpath(path).lstrip("/.")          # path traversal koruması
            dest = os.path.join(root, safe)
            os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
            with open(dest, "w") as f:
                f.write(str(body))
            n_files += 1
        # tasarım dokümanları
        md = content.get("markdown")
        if md:
            ddir = os.path.join(root, "_docs")
            os.makedirs(ddir, exist_ok=True)
            with open(os.path.join(ddir, f"{node}-{a.get('agent','')}.md"), "w") as f:
                f.write(str(md))
            n_docs += 1

    print(f"✓ {n_files} kod dosyası + {n_docs} doküman yazıldı → {root}/")
    print(f"  İncele:  find {root} -type f")
    return 0


if __name__ == "__main__":
    sys.exit(main())
