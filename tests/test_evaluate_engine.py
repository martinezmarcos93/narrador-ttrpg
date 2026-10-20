import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("evaluate_engine", ROOT / "scripts" / "evaluate_engine.py")
evaluate_engine = importlib.util.module_from_spec(spec)
sys.modules["evaluate_engine"] = evaluate_engine
spec.loader.exec_module(evaluate_engine)


def test_every_mapped_test_exists():
    data = yaml.safe_load((ROOT / "data/evaluation/engine_scenarios.yaml").read_text(encoding="utf-8"))
    assert len(data["scenarios"]) == 16
    for item in data["scenarios"].values():
        for node in item["tests"]:
            path, name = node.split("::")
            assert f"def {name}(" in (ROOT / path).read_text(encoding="utf-8"), node


def test_summarize_rates():
    spec = {"scenarios": {"a": {"metric": "m1", "tests": ["t1"]},
                          "b": {"metric": "m1", "tests": ["t2", "t3"]}}}
    report = evaluate_engine.summarize(spec, {"t1": True, "t2": True, "t3": False})
    assert report["scenario_pass_rate"] == 0.5
    assert report["metrics"] == {"m1": 0.5}
    assert report["failed"] == ["b"]
