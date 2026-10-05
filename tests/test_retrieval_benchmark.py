from narrator.core.context_contract import ContextFragment
from narrator.core.retrieval_benchmark import benchmark_router, load_cases
from narrator.core.retrieval_evaluator import RetrievalCase


class FakeRouter:
    def retrieve_fragments(self, query, pack):
        return [
            ContextFragment(
                text="concepto",
                source="brain",
                layer="universal",
                title="Concepto",
                score=1.0,
                metadata={"id": "universal-investigacion"},
            ),
            ContextFragment(
                text="ruido",
                source="brain",
                layer="universal",
                title="Ruido",
                score=0.2,
                metadata={"id": "ruido"},
            ),
        ], 0


def _write_system(path):
    path.mkdir()
    (path / "generic.yaml").write_text(
        """
slug: generic
sistema: Generic
edition: test
vocabulario: {}
character_sheet_schema: {}
resolution: {}
lorebook: []
knowledge:
  brain_system: generic
  preferred_sources: [universal]
  universal_fallback: true
llm_system_prompt: ""
""",
        encoding="utf-8",
    )


def test_load_cases_reads_ground_truth(tmp_path):
    source = tmp_path / "ground.yaml"
    source.write_text(
        """
cases:
  - id: q1
    query: pistas
    relevant_ids: [universal-investigacion]
    system: generic
    expected_layers: [universal]
""",
        encoding="utf-8",
    )

    cases = load_cases(source)

    assert len(cases) == 1
    assert cases[0].relevant_ids == ("universal-investigacion",)


def test_benchmark_router_extracts_ids_and_layers(tmp_path):
    systems = tmp_path / "systems"
    _write_system(systems)

    cases = (
        RetrievalCase(
            "q1",
            "pistas",
            ("universal-investigacion",),
            expected_layers=("universal",),
            system="generic",
        ),
    )

    result = benchmark_router(FakeRouter(), cases, systems, k=2)

    assert result.recall_at_k == 1.0
    assert result.layer_coverage == 1.0
