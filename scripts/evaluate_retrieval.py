#!/usr/bin/env python3
"""Benchmark del recuperador del cerebro contra el ground truth versionado.

Mide solo la capa cerebro (RecuperadorCerebro). Para medir el KnowledgeRouter
completo (manual + sistema + campaña + cerebro) usar tools/evaluate_retrieval.py.
Requiere el índice del cerebro construido (python scripts/ingest_brain.py).
"""
from __future__ import annotations

import argparse
import json

from narrator.cerebro.recuperador import RecuperadorCerebro
from narrator.core.retrieval_benchmark import load_cases
from narrator.core.retrieval_evaluator import evaluate_cases


def run(brain: str, ground_truth: str, k: int, model: str) -> dict:
    retriever = RecuperadorCerebro(brain, embedding_model=model)
    cases = load_cases(ground_truth)
    results: dict[str, list[str]] = {}
    layers: dict[str, list[str]] = {}
    for case in cases:
        found = retriever.search(case.query, max_results=max(k, 8), system=case.system or None)
        results[case.query_id] = [str(item["meta"].get("id", "")) for item in found]
        layers[case.query_id] = [str(item.get("layer", "")) for item in found]
    return evaluate_cases(cases, results, k=k, layers=layers).to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain", default="cerebro")
    parser.add_argument("--ground-truth", default="data/evaluation/retrieval_ground_truth.yaml")
    parser.add_argument("--model", default="nomic-embed-text")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k debe ser >= 1")

    payload = run(args.brain, args.ground_truth, args.k, args.model)
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
