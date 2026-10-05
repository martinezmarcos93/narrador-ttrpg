from pathlib import Path

from narrator.cerebro.indexador import IndiceCerebro


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, text):
        self.calls += 1
        return [1.0, 0.0]


def write_neuron(root: Path, text: str):
    (root / "n.md").write_text(
        "---\nid: n\ntitle: N\nsistema: universal\n---\n" + text,
        encoding="utf-8",
    )


def test_index_is_incremental_but_reindexes_changed_content(tmp_path):
    root = tmp_path / "cerebro"
    root.mkdir()
    write_neuron(root, "primero")
    embedder = FakeEmbedder()
    index = IndiceCerebro(root, embedder=embedder)

    assert index.build() == 1
    assert embedder.calls == 1
    assert index.build() == 0
    assert embedder.calls == 1

    write_neuron(root, "modificado")
    assert index.build() == 1
    assert embedder.calls == 2
