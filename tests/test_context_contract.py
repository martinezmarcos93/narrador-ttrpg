import pytest

from narrator.core.context_contract import ContextFragment, render_context


def test_context_fragment_rejects_unknown_layer():
    with pytest.raises(ValueError):
        ContextFragment(text="x", source="test", layer="inventada")


def test_context_render_prioritizes_state_over_universal():
    universal = ContextFragment(
        text="concepto general", source="brain", layer="universal", score=1
    )
    state = ContextFragment(
        text="hecho de campaña", source="state", layer="state", score=0.1
    )
    rendered = render_context([universal, state], max_words=30)
    assert rendered.index("[STATE") < rendered.index("[UNIVERSAL")
    assert "hecho de campaña" in rendered


def test_context_render_preserves_source_labels():
    manual = ContextFragment(
        text="regla específica", source="manual-v20", layer="manual", title="Disciplina"
    )
    rendered = render_context([manual], max_words=30)
    assert "[MANUAL | Disciplina | fuente: manual-v20]" in rendered
