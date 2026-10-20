from pathlib import Path

from narrator.cerebro.auditor import audit_brain
from narrator.cerebro.barredor import titulo_legible

ROOT = Path(__file__).resolve().parent.parent


def _neuron(path: Path, front: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}---\n{body}\n", encoding="utf-8")


def test_universal_brain_in_repo_passes_audit():
    report = audit_brain(
        ROOT / "cerebro" / "universal",
        concepts_path=ROOT / "data" / "cerebro" / "conceptos_requeridos.yaml",
        ground_truth_path=ROOT / "data" / "evaluation" / "retrieval_ground_truth.yaml",
    )
    assert report.ok, report.to_dict()


def test_audit_detects_schema_ids_links_gaps_and_ground_truth(tmp_path):
    _neuron(tmp_path / "a.md", "id: universal-a\ntitulo: A\nsystem: universal\nkind: x\ntags: [a]\n",
            "[[universal-b]] [[universal-inexistente]]")
    _neuron(tmp_path / "b.md", "id: Universal B\ntitle: B\nsystem: universal\nkind: x\ntags: [b]\n")
    _neuron(tmp_path / "c.md", "id: universal-a\ntitle: C\nsystem: universal\nkind: x\ntags: c\n")
    concepts = tmp_path / "conceptos.yaml"
    concepts.write_text("conceptos:\n  magia: {keywords: [magia]}\n", encoding="utf-8")
    gt = tmp_path / "gt.yaml"
    gt.write_text("cases:\n  - id: q\n    relevant_ids: [universal-zeta]\n", encoding="utf-8")

    report = audit_brain(tmp_path, concepts_path=concepts, ground_truth_path=gt)

    assert not report.ok
    assert any("falta 'title'" in e for e in report.schema_errors)
    assert any("legacy 'titulo'" in e for e in report.schema_errors)
    assert any("'tags' debe ser lista" in e for e in report.schema_errors)
    assert any("no cumple" in e for e in report.id_errors)
    assert any("duplicado" in e for e in report.id_errors)
    assert any("universal-inexistente" in e for e in report.broken_links)
    assert report.concept_gaps == ["magia"]
    assert report.ground_truth_missing == ["q: universal-zeta"]


def test_system_profile_accepts_barredor_schema(tmp_path):
    root = tmp_path / "sistemas"
    _neuron(root / "vtm_v20" / "v20" / "Disciplinas.md",
            "id: sistemas/vtm_v20/v20/Disciplinas\ntitulo: Disciplinas\ntipo: seccion\n"
            "capa: sistema\nsistema: vtm_v20\nfuente: v20\n")
    assert audit_brain(root, profile="sistema").ok


def test_titulo_legible_filters_ocr_noise():
    assert titulo_legible("Capítulo Cinco: Sistema de juego")
    assert not titulo_legible("lt-----1-MA -+-----~-")
    assert not titulo_legible("L~---... 111 4~ ;'5;·~,...,-~51i!!!p")
    assert not titulo_legible("12")
