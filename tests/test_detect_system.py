from narrator.app import detect_system


def test_detect_vampiro():
    text = "Este juego utiliza el sistema de Narrador de Vampiro la Mascarada. La Sangre, clanes y disciplinas."
    name, slug = detect_system(text)
    assert name == "Mundo de Tinieblas (Vampiro V20)"
    assert slug == "vtm_v20"

def test_detect_dnd():
    text = "Este manual contiene las reglas de D&D 5e con clases, razas y tiradas de d20."
    name, slug = detect_system(text)
    assert name == "Dungeons & Dragons 5e"
    assert slug == "dnd_5e"

def test_detect_cthulhu():
    text = "La llamada de Cthulhu utiliza un sistema de porcentaje (d100) para la cordura."
    name, slug = detect_system(text)
    assert name == "La Llamada de Cthulhu 7e"
    assert slug == "coc_7e"

def test_detect_generic():
    text = "Un juego de rol indie sobre gatos mágicos."
    name, slug = detect_system(text)
    assert name == "Sistema Genérico"
    assert slug == "generic"


def test_detect_werewolf_even_if_vampires_are_mentioned():
    text = (
        "Los Garou de la tribu Fianna defienden el túmulo del Wyrm. "
        "En forma Crinos, el Ahroun recuerda la Letanía. Los vampiros son enemigos menores."
    )
    name, slug = detect_system(text)
    assert slug == "wta_w20"
    assert "Hombre Lobo" in name


def test_detection_is_accent_insensitive_and_word_bounded():
    from narrator.core.system_detection import detect_system as detect

    assert detect("Las reglas de CORDURA y los Mitos de Cthulhu", "data/systems")[1] == "coc_7e"
    # 'clan' no debe contar dentro de 'clandestino'
    assert detect("Una reunión clandestina", "data/systems")[1] == "generic"


def test_every_pack_declares_detection_block():
    from narrator.core.system_detection import load_detection_profiles

    profiles = load_detection_profiles("data/systems")
    for slug, profile in profiles.items():
        if slug != "generic":
            assert profile["keywords"], slug


def test_identify_manual_edition_and_mismatch_warning():
    from narrator.core.system_detection import identify_manual

    v20 = identify_manual("Vampiro: La Mascarada 20º Aniversario. La Camarilla y el Sabbat.",
                          "data/systems")
    assert (v20.slug, v20.edition, v20.edition_mismatch) == ("vtm_v20", "V20", False)

    v5 = identify_manual("Vampiro La Mascarada quinta edición: el Ansia y la Camarilla.",
                         "data/systems")
    assert v5.slug == "vtm_v20"
    assert v5.edition == "V5" and v5.edition_mismatch
    assert "V5" in v5.warning

    nada = identify_manual("Un juego sobre gatos mágicos.", "data/systems")
    assert nada.slug == "generic" and nada.confidence == 0.0 and nada.warning == ""
