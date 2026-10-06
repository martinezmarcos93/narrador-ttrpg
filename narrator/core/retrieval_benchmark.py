"""Benchmark del KnowledgeRouter contra ground truth.

No se ejecuta durante una partida. Es una herramienta offline para comparar
versiones del retrieval sobre el mismo conjunto de consultas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from narrator.core.knowledge_router import KnowledgeRouter
from narrator.core.retrieval_evaluator import (
    RetrievalCase,
    RetrievalEvaluation,
    evaluate_cases,
)
from narrator.core.system_pack import SystemPack


def load_cases(path: str | Path) -> tuple[RetrievalCase, ...]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    cases = []
    for raw in data.get("cases", []):
        cases.append(
            RetrievalCase(
                query_id=str(raw["id"]),
                query=str(raw["query"]),
                relevant_ids=tuple(str(item) for item in raw.get("relevant_ids", [])),
                graded_relevance={
                    str(key): float(value)
                    for key, value in (raw.get("graded_relevance") or {}).items()
                },
                system=str(raw.get("system", "")),
                expected_layers=tuple(
                    str(item) for item in raw.get("expected_layers", [])
                ),
            )
        )
    return tuple(cases)


def _fragment_id(fragment: Any) -> str:
    metadata = getattr(fragment, "metadata", {}) or {}
    return str(metadata.get("id") or metadata.get("slug") or "")


def benchmark_router(
    router: KnowledgeRouter,
    cases: tuple[RetrievalCase, ...],
    systems_path: str | Path,
    *,
    k: int = 5,
) -> RetrievalEvaluation:
    results: dict[str, list[str]] = {}
    layers: dict[str, list[str]] = {}

    for case in cases:
        slug = case.system or "generic"
        pack = SystemPack.load(slug, Path(systems_path))
        fragments, _ = router.retrieve_fragments(case.query, pack)
        results[case.query_id] = [
            fragment_id
            for fragment in fragments
            if (fragment_id := _fragment_id(fragment))
        ][:k]
        layers[case.query_id] = [
            fragment.layer for fragment in fragments
        ][:k]

    return evaluate_cases(cases, results, k=k, layers=layers)
