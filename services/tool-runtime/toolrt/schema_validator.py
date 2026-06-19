"""Tool argument schema validation — v0.9.1

Flat dict ({"field": "type"}) → tüm alanlar required.
JSON Schema altkümesi ({"type":"object","properties":...,"required":[...]}) da desteklenir.
"""
from __future__ import annotations

TYPE_MAP = {"string": str, "int": int, "float": float, "bool": bool, "list": list, "dict": dict}


def validate(tool_name: str, args: dict, catalog: dict) -> list[str]:
    """Returns list of error messages. Empty list = valid."""
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
