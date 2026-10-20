#!/usr/bin/env python3
"""Evaluación del motor (Fase I): escenarios TTRPG -> tasas por métrica.

Ejecuta los tests mapeados en data/evaluation/engine_scenarios.yaml y reporta
scenario_pass_rate y la tasa de aprobación por métrica (state_correctness,
causal_correctness, knowledge_leakage, proposal_validity, rollback_correctness).
Sin LLM ni red: es determinista y apto para CI.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def summarize(spec: dict, outcomes: dict[str, bool]) -> dict:
    scenarios, metrics = {}, {}
    for name, item in spec["scenarios"].items():
        passed = all(outcomes.get(test, False) for test in item["tests"])
        scenarios[name] = passed
        bucket = metrics.setdefault(item["metric"], [0, 0])
        bucket[0] += int(passed)
        bucket[1] += 1
    total = len(scenarios) or 1
    return {
        "scenario_pass_rate": round(sum(scenarios.values()) / total, 3),
        "metrics": {m: round(ok / n, 3) for m, (ok, n) in sorted(metrics.items())},
        "failed": sorted(name for name, ok in scenarios.items() if not ok),
        "scenarios": scenarios,
    }


def run_tests(tests: list[str]) -> dict[str, bool]:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "junit.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             f"--junitxml={report}", *tests],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        outcomes = {}
        for case in ET.parse(report).iter("testcase"):
            module = case.get("classname", "").replace(".", "/") + ".py"
            node = f"{module}::{case.get('name')}"
            failed = any(child.tag in {"failure", "error", "skipped"} for child in case)
            outcomes[node] = not failed
        return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=str(ROOT / "data/evaluation/engine_scenarios.yaml"))
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    tests = sorted({t for item in spec["scenarios"].values() for t in item["tests"]})
    report = summarize(spec, run_tests(tests))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["scenario_pass_rate"] >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
