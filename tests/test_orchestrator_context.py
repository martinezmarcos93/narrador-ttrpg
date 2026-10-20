"""Integración del contexto del narrador con un Orchestrator real (sin LLM)."""

from pathlib import Path

import pytest

from narrator.agents.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def orchestrator(tmp_path, monkeypatch):
    # Sin Ollama: el embedder debe degradar a búsqueda léxica.
    monkeypatch.setattr(
        "narrator.core.embedder.Embedder.is_available", lambda self: False, raising=False
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        "sistema_activo: vtm_v20\n"
        f"systems_path: {ROOT / 'data' / 'systems'}\n"
        f"vault:\n  path: {tmp_path / 'vault'}\n"
        f"cerebro:\n  path: {tmp_path / 'cerebro'}\n"
        f"estado:\n  path: {tmp_path / 'estado.yaml'}\n",
        encoding="utf-8",
    )
    (tmp_path / "vault").mkdir()
    (tmp_path / "cerebro").mkdir()
    return Orchestrator(config_path=str(config))


def test_lorebook_keyword_reaches_narrator_prompt(orchestrator):
    prompt = orchestrator.build_narrator_context({
        "system_slug": "vtm_v20",
        "messages": [{"role": "user", "content": "Propongo hacer la vaulderie con la manada"}],
    })
    assert "[SYSTEM | lorebook]" in prompt
    assert "Vaulderie" in prompt


def test_lorebook_absent_without_keyword(orchestrator):
    prompt = orchestrator.build_narrator_context({
        "system_slug": "vtm_v20",
        "messages": [{"role": "user", "content": "Camino por la calle"}],
    })
    assert "[SYSTEM | lorebook]" not in prompt
