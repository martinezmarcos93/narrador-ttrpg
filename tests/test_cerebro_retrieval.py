from pathlib import Path

from narrator.cerebro.indexador import IndiceCerebro
from narrator.cerebro.recuperador import RecuperadorCerebro


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        lowered = text.lower()
        return [1.0, 0.0] if "investigación" in lowered or "investigacion" in lowered else [0.0, 1.0]


def write_neuron(root: Path, name: str, neuron_id: str, title: str, body: str, also=None):
    also = also or []
    (root / name).write_text(
        "---\n"
        f"id: {neuron_id}\n"
        f"title: {title}\n"
        "system: universal\n"
        "kind: concept\n"
        f"tags: [test]\n"
        f"ver_tambien: {also}\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_index_builds_and_persists_metadata(tmp_path):
    root = tmp_path / "cerebro"
    root.mkdir()
    write_neuron(root, "investigacion.md", "inv", "Investigación", "pistas y misterio")
    embedder = FakeEmbedder()
    index = IndiceCerebro(root, embedder=embedder)

    assert index.build() == 1
    assert index.ready()
    assert (root / ".brain_embeddings.json").exists()
    assert (root / ".brain_index.yaml").exists()


def test_hybrid_retrieval_filters_system_and_expands_graph(tmp_path):
    root = tmp_path / "cerebro"
    root.mkdir()
    write_neuron(root, "investigacion.md", "inv", "Investigación", "pistas y misterio", ["npc"])
    write_neuron(root, "npc.md", "npc", "NPC", "testigo de la investigación")

    retriever = RecuperadorCerebro(root)
    retriever.index.embedder = FakeEmbedder()
    retriever.build_index()

    results = retriever.search("investigacion", max_results=2, system="universal")
    assert results
    assert results[0]["meta"]["id"] == "inv"
    assert any(item["meta"]["id"] == "npc" for item in results)
