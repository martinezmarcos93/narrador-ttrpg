from narrator.core.retrieval_evaluator import (
    RetrievalCase,
    evaluate_cases,
    score_case,
)


def test_score_case_binary_relevance():
    case = RetrievalCase(
        query_id="q1",
        query="investigación y pistas",
        relevant_ids=("universal-investigacion", "universal-incertidumbre"),
    )

    score = score_case(
        case,
        ["universal-investigacion", "ruido", "universal-incertidumbre"],
        k=3,
    )

    assert score.precision_at_k == 2 / 3
    assert score.recall_at_k == 1.0
    assert score.reciprocal_rank == 1.0
    assert score.ndcg_at_k > 0.9


def test_score_case_respects_rank_and_deduplicates():
    case = RetrievalCase(
        query_id="q2",
        query="continuidad",
        relevant_ids=("universal-continuidad-temporal",),
    )

    score = score_case(
        case,
        ["ruido", "ruido", "universal-continuidad-temporal"],
        k=3,
    )

    assert score.retrieved_count == 2
    assert score.reciprocal_rank == 0.5
    assert score.recall_at_k == 1.0


def test_graded_ndcg_penalizes_bad_ordering():
    case = RetrievalCase(
        query_id="q3",
        query="estado",
        relevant_ids=("state", "universal-estado-ficcion"),
        graded_relevance={
            "state": 3.0,
            "universal-estado-ficcion": 1.0,
        },
    )

    good = score_case(case, ["state", "universal-estado-ficcion"], k=2)
    bad = score_case(case, ["universal-estado-ficcion", "state"], k=2)

    assert good.ndcg_at_k > bad.ndcg_at_k
    assert good.recall_at_k == bad.recall_at_k == 1.0


def test_layer_coverage_is_explicit():
    case = RetrievalCase(
        query_id="q4",
        query="frentes",
        relevant_ids=("universal-frentes-relojes",),
        expected_layers=("universal", "system"),
    )

    score = score_case(
        case,
        ["universal-frentes-relojes"],
        k=3,
        retrieved_layers=["universal", "campaign"],
    )

    assert score.layer_coverage == 0.5


def test_evaluate_cases_aggregates_metrics():
    cases = [
        RetrievalCase("q1", "pistas", ("a",)),
        RetrievalCase("q2", "frentes", ("b",)),
    ]
    result = evaluate_cases(
        cases,
        {"q1": ["a"], "q2": ["noise", "b"]},
        k=2,
    )

    assert result.to_dict()["case_count"] == 2
    assert result.recall_at_k == 1.0
    assert result.mrr == 0.75
    assert 0.0 < result.ndcg_at_k <= 1.0
