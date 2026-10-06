"""Evaluación reproducible del retrieval del Narrador.

Recibe IDs recuperados y ground truth, permitiendo medir precision@k,
recall@k, MRR y nDCG sin depender de un modelo de embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log2
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RetrievalCase:
    query_id: str
    query: str
    relevant_ids: tuple[str, ...]
    graded_relevance: Mapping[str, float] = field(default_factory=dict)
    system: str = ""
    expected_layers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalScore:
    query_id: str
    k: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    relevant_retrieved: int
    retrieved_count: int
    layer_coverage: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "k": self.k,
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            "reciprocal_rank": self.reciprocal_rank,
            "ndcg_at_k": self.ndcg_at_k,
            "relevant_retrieved": self.relevant_retrieved,
            "retrieved_count": self.retrieved_count,
            "layer_coverage": self.layer_coverage,
        }


@dataclass(frozen=True)
class RetrievalEvaluation:
    cases: tuple[RetrievalScore, ...]
    k: int

    @property
    def precision_at_k(self) -> float:
        return _mean(item.precision_at_k for item in self.cases)

    @property
    def recall_at_k(self) -> float:
        return _mean(item.recall_at_k for item in self.cases)

    @property
    def mrr(self) -> float:
        return _mean(item.reciprocal_rank for item in self.cases)

    @property
    def ndcg_at_k(self) -> float:
        return _mean(item.ndcg_at_k for item in self.cases)

    @property
    def layer_coverage(self) -> float:
        return _mean(item.layer_coverage for item in self.cases)

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "case_count": len(self.cases),
            "precision_at_k": round(self.precision_at_k, 6),
            "recall_at_k": round(self.recall_at_k, 6),
            "mrr": round(self.mrr, 6),
            "ndcg_at_k": round(self.ndcg_at_k, 6),
            "layer_coverage": round(self.layer_coverage, 6),
            "cases": [item.to_dict() for item in self.cases],
        }


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _dcg(relevances: Sequence[float]) -> float:
    return sum(
        relevance / log2(index + 2)
        for index, relevance in enumerate(relevances)
    )


def _ideal_relevances(case: RetrievalCase) -> list[float]:
    if case.graded_relevance:
        return sorted(
            (float(value) for value in case.graded_relevance.values()),
            reverse=True,
        )
    return [1.0] * len(case.relevant_ids)


def score_case(
    case: RetrievalCase,
    retrieved_ids: Sequence[str],
    *,
    k: int = 5,
    retrieved_layers: Sequence[str] | None = None,
) -> RetrievalScore:
    if k < 1:
        raise ValueError("k debe ser >= 1")

    unique_ids: list[str] = []
    seen: set[str] = set()
    for item in retrieved_ids:
        item = str(item)
        if item not in seen:
            unique_ids.append(item)
            seen.add(item)

    top = unique_ids[:k]
    relevant = set(case.relevant_ids)
    hits = [item for item in top if item in relevant]
    precision = len(hits) / k
    recall = len(hits) / len(relevant) if relevant else 0.0

    reciprocal_rank = 0.0
    for index, item in enumerate(top, start=1):
        if item in relevant:
            reciprocal_rank = 1.0 / index
            break

    grades = case.graded_relevance or {item: 1.0 for item in case.relevant_ids}
    observed = [float(grades.get(item, 0.0)) for item in top]
    ideal = _ideal_relevances(case)[:k]
    ideal_dcg = _dcg(ideal)
    ndcg = _dcg(observed) / ideal_dcg if ideal_dcg else 0.0

    layer_coverage = 0.0
    if case.expected_layers and retrieved_layers is not None:
        expected = set(case.expected_layers)
        observed_layers = set(str(layer) for layer in retrieved_layers[:k])
        layer_coverage = len(expected & observed_layers) / len(expected)

    return RetrievalScore(
        query_id=case.query_id,
        k=k,
        precision_at_k=round(precision, 6),
        recall_at_k=round(recall, 6),
        reciprocal_rank=round(reciprocal_rank, 6),
        ndcg_at_k=round(ndcg, 6),
        relevant_retrieved=len(hits),
        retrieved_count=len(top),
        layer_coverage=round(layer_coverage, 6),
    )


def evaluate_cases(
    cases: Sequence[RetrievalCase],
    results: Mapping[str, Sequence[str]],
    *,
    k: int = 5,
    layers: Mapping[str, Sequence[str]] | None = None,
) -> RetrievalEvaluation:
    scores = []
    for case in cases:
        scores.append(
            score_case(
                case,
                results.get(case.query_id, ()),
                k=k,
                retrieved_layers=(layers or {}).get(case.query_id),
            )
        )
    return RetrievalEvaluation(tuple(scores), k=k)
