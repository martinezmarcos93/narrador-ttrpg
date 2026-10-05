"""CLI offline para evaluar el retrieval real del Narrador.

Requiere el índice del cerebro y el modelo de embeddings configurados localmente.
No modifica estado de campaña ni llama al LLM.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from narrator.agents.orchestrator import Orchestrator
from narrator.core.retrieval_benchmark import benchmark_router, load_cases
from narrator.core.system_pack import SystemPack


def run(
    *,
    config_path: str = "config/config.yaml",
    ground_truth_path: str = "data/evaluation/retrieval_ground_truth.yaml",
    k: int = 5,
) -> dict:
    orchestrator = Orchestrator(config_path=config_path)
    brain = orchestrator.retriever.brain
    if not brain.available:
        raise RuntimeError(
            "El índice del cerebro no está disponible. Construí el índice antes del benchmark."
        )
    if not brain.index.embedder.is_available():
        raise RuntimeError(
            "El modelo de embeddings configurado no está disponible en Ollama."
        )
    cases = load_cases(ground_truth_path)
    systems_path = orchestrator.builder.systems_path
    evaluation = benchmark_router(
        orchestrator.knowledge_router,
        cases,
        systems_path,
        k=k,
    )
    return evaluation.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evalúa el retrieval real contra ground truth."
    )
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument(
        "--ground-truth",
        default="data/evaluation/retrieval_ground_truth.yaml",
    )
    parser.add_argument("-k", "--k", type=int, default=5)
    args = parser.parse_args()

    if args.k < 1:
        parser.error("--k debe ser >= 1")

    result = run(
        config_path=args.config,
        ground_truth_path=args.ground_truth,
        k=args.k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
