#!/usr/bin/env python3
"""Run the retrieval benchmark locally against the real brain index."""
from __future__ import annotations

import argparse
import json

from narrator.cerebro.recuperador import RecuperadorCerebro
from narrator.core.retrieval_evaluator import RetrievalCase, evaluate_cases


CASES = (
    RetrievalCase(
        "investigacion",
        "investigación pistas evidencia incertidumbre",
        ("universal-investigacion",),
        system="generic",
        expected_layers=("universal",),
    ),
    RetrievalCase(
        "combate",
        "resolución combate ataque defensa",
        ("universal-combate",),
        system="generic",
        expected_layers=("universal",),
    ),
    RetrievalCase(
        "continuidad",
        "continuidad temporal consecuencias estado persistente",
        ("universal-continuidad-temporal", "universal-estado-persistente"),
        system="generic",
        expected_layers=("universal",),
    ),
    RetrievalCase(
        "vtm",
        "resolución mecánica vampiro",
        ("system_vtm_knowledge",),
        system="vtm_v20",
        expected_layers=("system",),
    ),
    RetrievalCase(
        "dnd",
        "resolución mecánica dungeons dragons",
        ("system_dnd_resolution",),
        system="dnd_5e",
        expected_layers=("system",),
    ),
    RetrievalCase(
        "coc",
        "resolución mecánica call of cthulhu",
        ("system_coc_resolution",),
        system="coc_7e",
        expected_layers=("system",),
    ),
    RetrievalCase(
        "pathfinder",
        "resolución mecánica pathfinder",
        ("system_pathfinder_resolution",),
        system="pathfinder_2e",
        expected_layers=("system",),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brain", default="cerebro")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()

    retriever = RecuperadorCerebro(args.brain)
    results: dict[str, list[str]] = {}
    layers: dict[str, list[str]] = {}
    for case in CASES:
        found = retriever.search(
            case.query,
            max_results=max(args.k, 8),
            system=case.system or None,
        )
        results[case.query_id] = [
            str(item["meta"].get("id", "")) for item in found
        ]
        layers[case.query_id] = [str(item.get("layer", "")) for item in found]

    evaluation = evaluate_cases(CASES, results, k=args.k, layers=layers)
    payload = evaluation.to_dict()
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
