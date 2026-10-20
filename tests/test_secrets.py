from pathlib import Path

import pytest

from narrator.core import secrets
from narrator.core.causality_engine import CausalityEngine
from narrator.core.proposal_executor import ProposalExecutor
from narrator.core.state_manager import StateManager

ROOT = Path(__file__).resolve().parent.parent
VERDAD = "El Príncipe Valerius es en realidad un Tremere infiltrado en la Camarilla"
PISTAS = [
    "Valerius lleva un anillo con un sello hermético",
    "Sus ghouls compran tiza y sal en el mercado negro",
    "Una carta firmada por la Capilla de Viena lo menciona",
]


@pytest.fixture
def state(tmp_path):
    st = StateManager(str(tmp_path / "estado.yaml"))
    st.data["escena_actual"]["npcs_presentes"] = ["Valerius"]
    secrets.add_secret(st, "principe", tema="La identidad del Príncipe", verdad=VERDAD,
                       pistas=PISTAS, sobre_tipo="npc", sobre_nombre="Valerius")
    return st


def test_add_secret_validates_shape(tmp_path):
    st = StateManager(str(tmp_path / "e.yaml"))
    with pytest.raises(secrets.SecretError):
        secrets.add_secret(st, "x", tema="t", verdad="v", pistas=[])
    with pytest.raises(secrets.SecretError):
        secrets.add_secret(st, "x", tema="t", verdad="v", pistas=["p"], sobre_tipo="dragon")


def test_gradual_discovery_per_perspective(state):
    entry = state.data["secretos"]["principe"]
    assert secrets.status(entry) == "oculto"
    secrets.reveal_clue(state, "principe")
    assert secrets.status(entry) == "parcial"
    assert secrets.status(entry, character="Alicia") == "oculto"
    secrets.reveal_clue(state, "principe")
    result = secrets.reveal_clue(state, "principe")
    assert result["status"] == "revelado"
    assert state.get_player_fact("secreto:principe") == VERDAD
    assert secrets.reveal_clue(state, "principe")["advanced"] is False


def test_narrator_section_only_exposes_next_clue(state):
    section = secrets.narrator_section(state, scene_entities=["Valerius"])
    assert "La identidad del Príncipe" in section
    assert PISTAS[0] in section
    assert PISTAS[1] not in section and VERDAD not in section
    secrets.reveal_clue(state, "principe")
    section = secrets.narrator_section(state, scene_entities=["Valerius"])
    assert PISTAS[1] in section and PISTAS[2] not in section
    assert secrets.narrator_section(state, scene_entities=["Otro NPC"]) == ""


def test_find_leaks_detects_hidden_material_only(state):
    assert secrets.find_leaks("La niebla cubre el Elíseo.", state) == []
    assert secrets.find_leaks(f"El narrador dice: {VERDAD.lower()}.", state) == ["principe"]
    # La próxima pista puede aparecer (es la que se va a descubrir).
    assert secrets.find_leaks(PISTAS[0], state) == []
    assert secrets.find_leaks(PISTAS[2], state) == ["principe"]


def test_discoveries_go_through_validated_proposals(state):
    executor = ProposalExecutor(state)
    bad = executor.execute({"discoveries": [{"secret": "inexistente"}]})
    assert not bad.applied
    assert any(i.code == "invalid_discovery" for i in bad.report.errors)
    ok = executor.execute({"discoveries": [{"secret": "principe"}]})
    assert ok.applied
    assert state.data["secretos"]["principe"]["descubiertas"]["jugador"] == 1
    assert any(c.startswith("discovery:principe") for c in ok.changes)


def test_causal_reveal_clue_effect(state):
    state.add_pending_consequence(
        "La carta cae en manos del grupo", trigger="registro del despacho",
        effects=[{"type": "reveal_clue", "secret": "principe"}],
    )
    CausalityEngine(state).evaluate("registro del despacho")
    assert state.data["secretos"]["principe"]["descubiertas"]["jugador"] == 1


def test_end_to_end_prompt_never_contains_hidden_truth(tmp_path, monkeypatch):
    from narrator.agents.orchestrator import Orchestrator

    monkeypatch.setattr("narrator.core.embedder.Embedder.is_available", lambda self: False)
    config = tmp_path / "config.yaml"
    config.write_text(
        f"systems_path: {ROOT / 'data' / 'systems'}\n"
        f"vault:\n  path: {tmp_path / 'vault'}\n"
        f"cerebro:\n  path: {tmp_path / 'cerebro'}\n"
        f"estado:\n  path: {tmp_path / 'estado.yaml'}\n",
        encoding="utf-8",
    )
    orch = Orchestrator(config_path=str(config))
    orch.state.data["escena_actual"]["npcs_presentes"] = ["Valerius"]
    secrets.add_secret(orch.state, "principe", tema="La identidad del Príncipe",
                       verdad=VERDAD, pistas=PISTAS, sobre_tipo="npc", sobre_nombre="Valerius")
    app_state = {"system_slug": "vtm_v20",
                 "messages": [{"role": "user", "content": "Observo el anillo de Valerius"}]}

    prompt = orch.build_narrator_context(app_state)
    assert secrets.find_leaks(prompt, orch.state) == []
    assert PISTAS[0] in prompt

    for _ in PISTAS:
        result = orch.validate_and_apply_proposal({"discoveries": [{"secret": "principe"}]},
                                                  app_state)
        assert result["applied"], result
    prompt = orch.build_narrator_context(app_state)
    assert VERDAD in prompt
