#!/usr/bin/env python3
"""Audita el cerebro: esquema, IDs, enlaces, cobertura conceptual y ground truth."""
from __future__ import annotations

import argparse
import json
import sys

from narrator.cerebro.auditor import audit_brain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brain", default="cerebro/universal")
    parser.add_argument("--concepts", default="data/cerebro/conceptos_requeridos.yaml")
    parser.add_argument("--ground-truth", default="data/evaluation/retrieval_ground_truth.yaml")
    parser.add_argument(
        "--profile", choices=("universal", "sistema"), default="universal",
        help="universal: esquema canónico; sistema: neuronas del barredor",
    )
    args = parser.parse_args()

    report = audit_brain(
        args.brain,
        concepts_path=args.concepts if args.profile == "universal" else None,
        ground_truth_path=args.ground_truth if args.profile == "universal" else None,
        profile=args.profile,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
