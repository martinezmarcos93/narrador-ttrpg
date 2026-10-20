import pytest

from narrator.core.character_sheet import (
    compute_derived,
    field_specs,
    track_status,
    validate_schema,
    wound_penalty,
)
from narrator.core.system_pack import SystemPack


@pytest.fixture(scope="module")
def vtm_schema():
    return SystemPack.load("vtm_v20", "data/systems").character_sheet_schema


def test_vtm_schema_has_full_v20_structure(vtm_schema):
    specs = field_specs(vtm_schema)
    for key in ("alerta", "pelea_armas", "ocultismo", "conciencia", "coraje",
                "fuerza_voluntad_temp", "salud_danio", "trasfondos", "especialidades"):
        assert key in specs, key
    assert specs["trasfondos"]["type"] == "map"
    assert specs["meritos"]["type"] == "list"


def test_vtm_clan_disciplines_match_v20(vtm_schema):
    def disciplines(clan):
        return {f["key"] for s in vtm_schema["conditional_sections"][clan] for f in s["fields"]}

    assert disciplines("brujah") == {"celeridad", "potencia", "presencia"}
    assert disciplines("malkavian") == {"auspex", "dementacion", "ofuscacion"}
    assert disciplines("lasombra") == {"dominacion", "obtenebracion", "potencia"}


@pytest.mark.parametrize("generation, blood_max, per_turn", [(13, 10, 1), (9, 14, 2), (6, 30, 6)])
def test_vtm_blood_is_derived_from_generation(vtm_schema, generation, blood_max, per_turn):
    derived = compute_derived(vtm_schema, {"generacion": generation})
    assert derived == {"sangre_max": blood_max, "sangre_por_turno": per_turn}


def test_derived_skips_missing_fields(vtm_schema):
    assert compute_derived(vtm_schema, {}) == {}


def test_health_track_penalties(vtm_schema):
    health = next(s for s in vtm_schema["base_sections"] if s.get("display") == "track")
    assert track_status(health, {})["label"] == "Ileso"
    assert track_status(health, {"salud_danio": 4})["penalty"] == -2
    assert track_status(health, {"salud_danio": 7})["maxed"] is True
    assert wound_penalty(vtm_schema, {"salud_danio": 6}) == -5


@pytest.mark.parametrize("schema, message", [
    ({"base_sections": [{"name": "X", "fields": [{"key": "a", "type": "float"}]}]}, "tipo desconocido"),
    ({"base_sections": [{"name": "X", "display": "rueda", "fields": []}]}, "display desconocido"),
    ({"base_sections": [{"name": "X", "fields": [{"key": "a", "type": "int", "min": 5, "max": 1}]}]}, "min > max"),
    ({"base_sections": [{"name": "X", "display": "track", "fields": [{"key": "a", "type": "int"}]}]}, "levels"),
    ({"base_sections": [], "derived": {"b": {"copy_of": "zzz"}}}, "inexistente"),
    ({"base_sections": [], "derived": {"b": {"computer": "nope"}}}, "computer desconocido"),
])
def test_validate_schema_reports_errors(schema, message):
    errors = validate_schema(schema)
    assert any(message in e for e in errors), errors
