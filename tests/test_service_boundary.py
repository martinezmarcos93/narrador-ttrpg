"""Contrato ejecutable de la frontera UI -> NarratorService -> Core."""

import ast
from pathlib import Path

from narrator.core.narrator_service import NarratorService

ROOT = Path(__file__).resolve().parent.parent
UI_FILES = [ROOT / "narrator" / "app.py", *sorted((ROOT / "narrator" / "web").glob("*.py"))]
FORBIDDEN_ATTRS = {"orchestrator", "_orchestrator"}
FORBIDDEN_CORE_ATTRS = {"retriever", "builder", "scenes", "pacing_agent", "causality"}


def _attribute_chains(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            yield node


def test_ui_layers_do_not_reach_into_orchestrator():
    offenders = []
    for path in UI_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _attribute_chains(tree):
            if node.attr in FORBIDDEN_ATTRS:
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
            if isinstance(node.value, ast.Name) and node.value.id in FORBIDDEN_ATTRS:
                offenders.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "_orchestrator":
                offenders.append(f"{path.name}:{node.lineno} _orchestrator")
    assert offenders == [], offenders


def test_ui_does_not_touch_core_collaborators_of_service():
    offenders = []
    for path in UI_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _attribute_chains(tree):
            if (
                node.attr in FORBIDDEN_CORE_ATTRS
                and isinstance(node.value, ast.Attribute)
                and node.value.attr in FORBIDDEN_ATTRS
            ):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], offenders


def test_service_exposes_ui_queries():
    for name in (
        "vault_path", "vault_template_path", "live_vault_updates", "sessions_dir",
        "system_data", "character_sheet_schema", "clocks_summary", "fronts_with_clocks",
        "scenes_status", "reset_session_pacing", "invalidate_retrieval_cache",
        "create_world_agent", "create_extractor",
    ):
        assert hasattr(NarratorService, name), name
