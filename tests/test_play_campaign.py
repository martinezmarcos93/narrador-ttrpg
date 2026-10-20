import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("play_campaign", ROOT / "scripts" / "play_campaign.py")
play_campaign = importlib.util.module_from_spec(spec)
sys.modules["play_campaign"] = play_campaign
spec.loader.exec_module(play_campaign)


class _Player:
    def chat(self, messages, max_tokens=0):
        return "Le pregunto a la Hermana Clara por los desaparecidos."


class _Narrator:
    def __init__(self):
        self.n = 0

    def chat(self, messages, max_tokens=0):
        self.n += 1
        if self.n == 1:
            return ('Clara baja la voz: vio una camioneta sin patente con el logo de una fundación.\n'
                    '```json-proposal\n{"discoveries": [{"secret": "cacería-valerius"}], '
                    '"events": ["Clara habla de la camioneta"]}\n```')
        return "La noche sigue fría en Constitución."


def test_headless_campaign_loop_with_fake_llms(tmp_path, monkeypatch):
    monkeypatch.setattr("narrator.core.embedder.Embedder.is_available", lambda self: False)
    report = play_campaign.play(
        ROOT / "data" / "campaigns" / "noches_de_ceniza.yaml", turns=3,
        narrator_llm=_Narrator(), player_llm=_Player(), archetype="social", workdir=tmp_path,
    )
    assert report["turns"] == 3
    assert report["leak_rate"] == 0.0
    assert report["proposal_validity"] == 1.0
    assert report["discoveries"]["cacería-valerius"] == 1
    assert report["intents"][0] == "social"
