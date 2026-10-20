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
