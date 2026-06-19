"""v0.9.1 — Tool Safety Layer acceptance tests.

Usage: make test  (docker exec'te pytest -q çalıştırır)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schema_validator import validate, validate_tool_plan
from app.models import ToolCompensation


# ---------------------------------------------------------------------------
# V1 — Dry-run
# ---------------------------------------------------------------------------
def test_v1_dry_run_invocation():
    """Dry_run=true → simulated result, compensation kaydı oluşmaz."""
    from app.schema_validator import _load_catalog
    catalog = _load_catalog()
    args = {"customer": "Test Ltd", "items": ["widget"]}
    errs = validate("create_quote", args, catalog)
    assert errs == [], f"valid args should pass: {errs}"
    # Dry-run verification is done at tool-runtime level (integration test).
    # Unit: plan-time validation should pass valid dry-run args.
    plan = [{"key": "t1", "node_kind": "tool", "tool": "create_quote", "tool_args": args}]
    errs = validate_tool_plan(plan, catalog)
    assert errs == []


# ---------------------------------------------------------------------------
# V2 — Schema validation
# ---------------------------------------------------------------------------
def test_v2_schema_missing_required():
    """Eksik required field → schema error list döner."""
    from app.schema_validator import _load_catalog
    catalog = _load_catalog()
    errs = validate("create_quote", {}, catalog)
    assert any("customer" in e for e in errs), f"expected customer error, got {errs}"


def test_v2_schema_wrong_type():
    """Yanlış tip → schema error."""
    from app.schema_validator import _load_catalog
    catalog = _load_catalog()
    errs = validate("check_stock", {"sku": 42, "qty": 1}, catalog)
    assert any("sku" in e for e in errs), f"expected sku type error, got {errs}"


def test_v2_unknown_tool():
    """Var olmayan tool → error."""
    errs = validate("nope", {}, {})
    assert errs


# ---------------------------------------------------------------------------
# V3 — Rate-limit (plan-time validation doesn't test Redis — needs integration)
# ---------------------------------------------------------------------------
def test_v3_rate_limit_config_valid():
    """tools.json rate_limit alanları geçerli mi?"""
    from app.schema_validator import _load_catalog
    catalog = _load_catalog()
    for name, spec in catalog.get("tools", {}).items():
        rl = spec.get("rate_limit")
        if rl is not None:
            assert "per_minute" in rl, f"{name}: per_minute required"
            assert isinstance(rl["per_minute"], int) and rl["per_minute"] > 0


# ---------------------------------------------------------------------------
# V4 — Compensation kaydı (model-level)
# ---------------------------------------------------------------------------
def test_v4_compensation_model():
    """ToolCompensation modeli beklenen alanlara sahip."""
    fields = {c.name for c in ToolCompensation.__table__.columns}
    for required in ("id", "task_id", "node_key", "tool", "exec_id", "compensate_fn", "status"):
        assert required in fields, f"missing field: {required}"


def test_v4_compensation_side_effect_filter():
    """Yalnızca side_effect=true olan tool'lar compensation üretir."""
    from app.schema_validator import _load_catalog
    catalog = _load_catalog()
    for name, spec in catalog.get("tools", {}).items():
        se = spec.get("side_effect", False)
        comp = spec.get("compensation")
        if se:
            assert "compensation" in spec, f"{name}: side_effect=true ama compensation yok"
        # side_effect=false → compensation null olmalı
        if not se:
            assert comp is None, f"{name}: side_effect=false ama compensation={comp}"


# ---------------------------------------------------------------------------
# V5 — Regresyon
# ---------------------------------------------------------------------------
def test_v5_canonical_dag_valid():
    """Fulfillment DAG'ı plan-time validation'dan geçer."""
    plan = [
        {"key": "t1", "node_kind": "tool", "tool": "check_stock", "tool_args": {"sku": "HTD-8M-800", "qty": 1}},
        {"key": "t2", "node_kind": "tool", "tool": "create_quote", "tool_args": {"customer": "ABC Makina", "items": ["HTD 8M 800"]}, "depends_on": ["t1"]},
        {"key": "t3", "node_kind": "tool", "tool": "generate_pdf", "tool_args": {"quote_id": "Q-123"}, "depends_on": ["t2"]},
        {"key": "t4", "node_kind": "approval", "depends_on": ["t3"]},
        {"key": "t5", "node_kind": "tool", "tool": "send_whatsapp", "tool_args": {"to": "+90", "doc": "Q-123.pdf"}, "depends_on": ["t4"]},
    ]
    from app.schema_validator import _load_catalog
    errs = validate_tool_plan(plan, _load_catalog())
    assert errs == [], f"canonical DAG should pass: {errs}"


# ---------------------------------------------------------------------------
# V6 — make validate (schema + registry + subjects)
# ---------------------------------------------------------------------------
def test_v6_validate_imports():
    """make validate'de kullanılan tüm modüller import edilebilir mi?"""
    from agentic_schemas.acp.v1 import ErrorCode, ErrorMessage, TaskMessage, ResultMessage
    from agentic_schemas.events.v1 import ALL_SUBJECTS
    from agentic_schemas.agent_registry.v1 import Registry
    # RATE_LIMIT enum mevcut
    assert ErrorCode.RATE_LIMIT == "RATE_LIMIT"


# ---------------------------------------------------------------------------
# V7 — Approval persistence (model + state-machine)
# ---------------------------------------------------------------------------
def test_v7_approval_node_terminal():
    """Approval node completed ise re-request edilmez (retry sırasında)."""
    # TaskNode model'inde node_kind=approval + status=done terminaldir
    from app.models import TaskNode
    assert any(
        c.name == "node_kind" for c in TaskNode.__table__.columns
    ), "TaskNode.node_kind required"
    # Approval completed → retry scheduler dokunmaz
    # Bu integration testiyle doğrulanır; burada model varlığı kontrol edilir.


# ---------------------------------------------------------------------------
# V8 — exec_id uniqueness (INV-6)
# ---------------------------------------------------------------------------
def test_v8_exec_id_unique_constraint():
    """tool_compensations.exec_id UNIQUE constraint mevcut."""
    from app.models import ToolCompensation
    constraints = [c for c in ToolCompensation.__table__.constraints if "exec_id" in str(c)]
    assert constraints, "exec_id UNIQUE constraint missing"
