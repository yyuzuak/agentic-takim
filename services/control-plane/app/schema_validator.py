"""Plan-time tool argument schema validation (v0.9.1, INV-3).

Runtime validation ile birlikte defense in depth.
"""
from __future__ import annotations

import json
import os

TYPE_MAP = {"string": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}

_CATALOG: dict | None = None
_CATALOG_PATH = os.environ.get("TOOLS_CONFIG", "/app/config/tools.json")


def _load_catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        raw.pop("$comment", None)
        _CATALOG = raw
    return _CATALOG


def validate(tool_name: str, args: dict, catalog: dict | None = None) -> list[str]:
    if catalog is None:
        catalog = _load_catalog()
    spec = (catalog.get("tools") or {}).get(tool_name)
    if not spec:
        return [f"tool '{tool_name}' not found in catalog"]

    raw = spec.get("args_schema")
    if not raw:
        return []

    errors: list[str] = []

    if isinstance(raw, dict) and "type" in raw and raw.get("type") == "object":
        props = raw.get("properties", {})
        required = raw.get("required", list(props.keys()))
        for field in required:
            if field not in args:
                errors.append(f"missing required field '{field}'")
        for field, val in args.items():
            prop = props.get(field)
            if prop and isinstance(prop, dict) and "type" in prop:
                expected = TYPE_MAP.get(prop["type"])
                if expected is not None and not isinstance(val, expected):
                    errors.append(f"'{field}': expected {prop['type']}, got {type(val).__name__}")
    elif isinstance(raw, dict):
        for field, raw_type in raw.items():
            if field not in args:
                errors.append(f"missing required field '{field}'")
            else:
                expected = TYPE_MAP.get(raw_type)
                if expected is not None and not isinstance(args[field], expected):
                    errors.append(f"'{field}': expected {raw_type}, got {type(args[field]).__name__}")

    return errors


def validate_tool_plan(plan: list[dict], catalog: dict | None = None) -> list[str]:
    """POST /tasks yolunda plan sonrası çağrılır. Hata varsa 422."""
    if catalog is None:
        catalog = _load_catalog()
    errors: list[str] = []
    for node in plan:
        if node.get("node_kind") == "tool":
            errs = validate(node.get("tool", ""), node.get("tool_args", {}) or {}, catalog)
            errors.extend(f"{node['key']}: {e}" for e in errs)
    return errors
