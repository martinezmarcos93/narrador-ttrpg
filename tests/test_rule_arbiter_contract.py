from narrator.core.rule_arbiter import RuleArbiter


class Builder:
    def load_system(self, slug):
        return {
            "resolution": {
                "mecanica": "d20_vs_dc",
                "acciones": [{"etiqueta": "Investigar", "atributo": "inteligencia", "keywords": ["investigar"]}],
                "dificultades": {"normal": 15},
            }
        }


def test_single_roll_mechanic_rejects_multiple_rolls():
    arbiter = RuleArbiter(Builder())
    assert arbiter.resolve("investigar", {"inteligencia": 14}, "generic", [13, 7], 20) is None
