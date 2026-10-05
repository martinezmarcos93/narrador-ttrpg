"""Tests del Rule Arbiter — resolución mecánica determinística por sistema."""

from narrator import PROJECT_ROOT
from narrator.core.prompt_builder import PromptBuilder
from narrator.core.rule_arbiter import RuleArbiter, _buscar_valor

_SYSTEMS = str(PROJECT_ROOT / "data" / "systems")


def _arbiter() -> RuleArbiter:
    return RuleArbiter(builder=PromptBuilder(systems_path=_SYSTEMS))


# ── Búsqueda en planilla anidada ──────────────────────────────
def test_buscar_valor_anidado():
    char = {"nombre": "Kael", "atributos": {"fuerza": 16, "destreza": 12}}
    assert _buscar_valor(char, "fuerza") == 16
    assert _buscar_valor(char, "FUERZA") == 16
    assert _buscar_valor(char, "carisma") is None
    assert _buscar_valor({}, "fuerza") is None
    assert _buscar_valor(None, "fuerza") is None


# ── D&D 5e: d20 + modificador vs CD ───────────────────────────
def test_dnd_exito():
    char = {"atributos": {"fuerza": 16}}  # score 16 → +3
    r = _arbiter().resolve("ataco al orco", char, "dnd_5e", rolls=[14], sides=20)
    assert r["veredicto"] == "ÉXITO"           # 14+3=17 vs CD 15
    assert r["banda"] == "10+"
    assert "17" in r["detalle"] and "CD 15" in r["detalle"]


def test_dnd_fallo():
    char = {"atributos": {"fuerza": 10}}  # +0
    r = _arbiter().resolve("ataco al orco", char, "dnd_5e", rolls=[5], sides=20)
    assert r["veredicto"] == "FALLO"
    assert r["banda"] == "6-"


def test_dnd_fallo_por_poco_es_parcial():
    char = {"atributos": {"fuerza": 16}}  # +3 → 11+3=14 vs 15
    r = _arbiter().resolve("ataco", char, "dnd_5e", rolls=[11], sides=20)
    assert r["veredicto"] == "FALLO POR POCO"
    assert r["banda"] == "7-9"


def test_dnd_critico_natural():
    r = _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[20], sides=20)
    assert "CRÍTICO" in r["veredicto"]
    assert r["banda"] == "10+"


def test_dnd_pifia_natural():
    r = _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[1], sides=20)
    assert "FALLO CRÍTICO" in r["veredicto"]


def test_dnd_dificultad_explicita():
    char = {"atributos": {"destreza": 14}}  # +2
    r = _arbiter().resolve("trepo el muro, CD 18", char, "dnd_5e", rolls=[15], sides=20)
    assert "CD 18" in r["detalle"]           # 15+2=17 vs 18 → fallo por poco
    assert r["veredicto"] == "FALLO POR POCO"


def test_dnd_dificultad_por_keyword():
    r = _arbiter().resolve("es una tarea trivial, salto la valla", {}, "dnd_5e",
                           rolls=[12], sides=20)
    assert "CD 10" in r["detalle"]
    assert r["veredicto"] == "ÉXITO"


def test_dnd_modificador_directo():
    # Valores -5..5 se interpretan como modificador, no como score
    char = {"atributos": {"fuerza": 3}}
    r = _arbiter().resolve("ataco", char, "dnd_5e", rolls=[13], sides=20)
    assert "= 16" in r["detalle"]            # 13+3


# ── VtM V20: pool de d10, éxitos netos ────────────────────────
def test_vtm_exito():
    r = _arbiter().resolve("sigilo entre las sombras", {}, "vtm_v20",
                           rolls=[8, 9, 6, 7], sides=10)
    assert "ÉXITO" in r["veredicto"]         # 4 éxitos vs dif 6
    assert r["banda"] == "10+"


def test_vtm_parcial():
    r = _arbiter().resolve("ataco", {}, "vtm_v20", rolls=[7, 3, 2], sides=10)
    assert "PARCIAL" in r["veredicto"]       # 1 éxito neto
    assert r["banda"] == "7-9"


def test_vtm_botch():
    r = _arbiter().resolve("ataco", {}, "vtm_v20", rolls=[1, 3, 2], sides=10)
    assert "FRACASO" in r["veredicto"]       # 0 éxitos y un 1
    assert r["banda"] == "6-"


def test_vtm_unos_restan():
    r = _arbiter().resolve("ataco", {}, "vtm_v20", rolls=[8, 1, 3], sides=10)
    assert r["veredicto"] == "FALLO"         # 1 éxito - 1 uno = 0 netos


# ── CoC 7e: percentil ─────────────────────────────────────────
def test_coc_exito():
    char = {"habilidades": {"descubrir": 60}}
    r = _arbiter().resolve("observo la habitación en busca de pistas", char,
                           "coc_7e", rolls=[45], sides=100)
    assert r["veredicto"] == "ÉXITO"


def test_coc_exito_extremo():
    char = {"habilidades": {"descubrir": 60}}
    r = _arbiter().resolve("observo la habitación", char, "coc_7e",
                           rolls=[10], sides=100)
    assert r["veredicto"] == "ÉXITO EXTREMO"


def test_coc_fallo():
    char = {"habilidades": {"descubrir": 40}}
    r = _arbiter().resolve("busco pistas", char, "coc_7e", rolls=[80], sides=100)
    assert r["veredicto"] == "FALLO"


def test_coc_dificultad_dura():
    char = {"habilidades": {"sigilo": 60}}
    # difícil → umbral 30; tirada 45 falla
    r = _arbiter().resolve("es difícil: sigilo bajo la luz", char, "coc_7e",
                           rolls=[45], sides=100)
    assert r["veredicto"] == "FALLO"


def test_coc_sin_habilidad_no_resuelve():
    # Sin valor en la planilla el percentil no puede resolverse → None (fallback)
    assert _arbiter().resolve("busco pistas", {}, "coc_7e", rolls=[30], sides=100) is None


# ── Genérico: bandas por ratio ────────────────────────────────
def test_generic_bandas():
    a = _arbiter()
    assert a.resolve("acción", {}, "generic", rolls=[19], sides=20)["banda"] == "10+"
    assert a.resolve("acción", {}, "generic", rolls=[12], sides=20)["banda"] == "7-9"
    assert a.resolve("acción", {}, "generic", rolls=[4], sides=20)["banda"] == "6-"


# ── Robustez ──────────────────────────────────────────────────
def test_sin_rolls_devuelve_none():
    assert _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[], sides=20) is None


def test_slug_desconocido_cae_a_generic():
    r = _arbiter().resolve("acción", {}, "sistema_inexistente", rolls=[18], sides=20)
    assert r is not None and r["banda"] == "10+"


def test_resultado_arbiter_incluye_trazabilidad_estructurada():
    r = _arbiter().resolve(
        "trepo el muro, CD 18",
        {"atributos": {"destreza": 14}},
        "dnd_5e",
        rolls=[15],
        sides=20,
    )
    assert r["system_slug"] == "dnd_5e"
    assert r["mecanica"] == "d20_vs_dc"
    assert r["atributo"] == "destreza"
    assert r["rolls"] == [15]
    assert r["sides"] == 20
    assert r["dificultad"] == 18
    assert r["dificultad_label"] == "declarada"
    assert r["rule_source"].endswith("dnd_5e.yaml:resolution")


def test_dnd_rechaza_dado_incompatible():
    assert _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[5], sides=10) is None


def test_arbiter_rechaza_resultado_fuera_de_rango():
    assert _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[21], sides=20) is None


def test_arbiter_expone_validacion_de_tirada():
    r = _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[12], sides=20)
    assert r["roll_validation"] == {
        "valid": True,
        "sides_compatible": True,
        "count": 1,
    }
