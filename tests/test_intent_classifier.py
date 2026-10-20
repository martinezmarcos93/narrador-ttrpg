import pytest

from narrator.core.intent_classifier import classify_intent
from narrator.core.system_pack import SystemPack

VTM = SystemPack.load("vtm_v20", "data/systems").resolution


@pytest.mark.parametrize("text, kind", [
    ("", "unknown"),
    ("(OOC) me tengo que ir en 10 minutos", "out_of_character"),
    ("¿Cómo funciona la tirada de frenesí?", "rules_question"),
    ("¿Quién es el Príncipe de la ciudad?", "lore_question"),
    ("¿Qué pasó en la sesión anterior?", "recall"),
    ("recordame en qué estábamos", "recall"),
    ("Ataco al guardia con mi cuchillo", "mechanical_action"),
    ("Me escondo detrás de los contenedores", "mechanical_action"),
    ("Examino el cuerpo buscando heridas", "investigation"),
    ("Intento convencer al ghoul de que nos deje pasar", "social"),
    ("Abro la puerta y entro al salón", "player_action"),
    ("\"Buenas noches, hermano\", digo con una sonrisa.", "dialogue_or_description"),
])
def test_classification(text, kind):
    assert classify_intent(text, VTM).kind == kind


def test_pack_action_is_attached_and_requires_roll():
    result = classify_intent("Disparo al lupino desde la azotea", VTM)
    assert result.needs_roll
    assert result.action["atributo"] == "destreza"


def test_investigation_with_pack_action_suggests_roll():
    result = classify_intent("Investigo los registros del hospital", VTM)
    assert result.kind == "investigation"
    assert result.needs_roll
    assert result.action["atributo"] == "inteligencia"


def test_accent_and_case_insensitive():
    assert classify_intent("ME ESCONDO", VTM).kind == "mechanical_action"
    assert classify_intent("¿QUÉ PASÓ ayer?", VTM).kind == "recall"
