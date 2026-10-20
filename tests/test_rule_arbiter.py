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
    r = _arbiter().resolve("me escondo tras el muro, CD 18", char, "dnd_5e", rolls=[15], sides=20)
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
        "me escondo tras el muro, CD 18",
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


# ── Primitivas mecánicas por System Pack (Fase C) ─────────────
V20_CHAR = {
    "destreza": 3, "armas_fuego": 2, "fuerza_voluntad_temp": 4,
    "especialidades": {"armas_fuego": "pistolas"}, "salud_danio": 0,
}


def test_v20_pool_includes_ability_and_reports_expected_size():
    r = _arbiter().resolve("disparo al guardia", dict(V20_CHAR), "vtm_v20",
                           rolls=[7, 3, 8, 2, 9], sides=10)
    assert r["habilidad"] == "armas_fuego"
    assert r["pool_esperado"] == 5
    assert "advertencias" not in r


def test_v20_wound_penalty_reduces_expected_pool():
    char = dict(V20_CHAR, salud_danio=4)  # Herido: -2
    r = _arbiter().resolve("disparo", char, "vtm_v20", rolls=[7, 8, 9], sides=10)
    assert r["pool_esperado"] == 3
    assert "heridas -2" in r["detalle"]


def test_v20_specialty_counts_tens_twice():
    r = _arbiter().resolve("disparo", dict(V20_CHAR), "vtm_v20",
                           rolls=[10, 10, 2, 3, 4], sides=10)
    assert "4 éxitos" in r["detalle"]


def test_v20_willpower_adds_success_and_returns_cost():
    r = _arbiter().resolve("disparo y gasto fuerza de voluntad", dict(V20_CHAR), "vtm_v20",
                           rolls=[1, 2, 3, 4, 5], sides=10)
    assert r["veredicto"].startswith("ÉXITO PARCIAL")
    assert r["costos"] == [{
        "field": "fuerza_voluntad_temp", "delta": -1,
        "reason": "gasto de Fuerza de Voluntad en una tirada",
    }]


def test_v20_willpower_without_points_still_botches():
    char = dict(V20_CHAR, fuerza_voluntad_temp=0)
    r = _arbiter().resolve("disparo y uso mi fuerza de voluntad", char, "vtm_v20",
                           rolls=[1, 2, 3, 4, 5], sides=10)
    assert r["veredicto"] == "FRACASO (botch)"
    assert "costos" not in r


def test_dnd_proficiency_bonus_applies_to_declared_skill():
    char = {"destreza": 14, "nivel": 5, "competencias": ["Sigilo"]}
    r = _arbiter().resolve("me escondo entre las sombras", char, "dnd_5e", rolls=[10], sides=20)
    assert "+3 (competencia sigilo)" in r["detalle"]  # +2 DES +3 competencia
    assert "= 15" in r["detalle"]


def test_dnd_advantage_and_disadvantage_use_two_dice():
    adv = _arbiter().resolve("ataco con ventaja", {"fuerza": 10}, "dnd_5e", rolls=[4, 17], sides=20)
    dis = _arbiter().resolve("ataco con desventaja", {"fuerza": 10}, "dnd_5e", rolls=[4, 17], sides=20)
    assert "con ventaja: 17" in adv["detalle"]
    assert "con desventaja: 4" in dis["detalle"]
    assert _arbiter().resolve("ataco", {}, "dnd_5e", rolls=[4, 17], sides=20) is None


def test_suggest_roll_per_mechanic():
    arb = _arbiter()
    assert arb.suggest_roll("disparo", dict(V20_CHAR), "vtm_v20") == {
        "dados": 5, "lados": 10, "accion": "Destreza + Armas de Fuego"}
    assert arb.suggest_roll("ataco con ventaja", {}, "dnd_5e")["dados"] == 2
    assert arb.suggest_roll("busco pistas", {}, "coc_7e")["lados"] == 100


def test_action_keywords_match_without_accents():
    r = _arbiter().resolve("engano al portero", {"manipulacion": 3, "subterfugio": 2},
                           "vtm_v20", rolls=[8, 8, 8, 8, 8], sides=10)
    assert r["habilidad"] == "subterfugio"
