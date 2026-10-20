#!/usr/bin/env python3
"""Valida y carga un manifiesto de campaña en el estado y el vault configurados."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from narrator.core.campaign import load_campaign, read_manifest, validate_manifest
    from narrator.core.state_manager import StateManager

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--state", default="estado_campana.yaml")
    parser.add_argument("--vault", default="vault")
    parser.add_argument("--check", action="store_true", help="solo valida, no carga")
    args = parser.parse_args()

    data = read_manifest(args.manifest)
    errors = validate_manifest(data, ROOT / "data" / "systems")
    if errors or args.check:
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    state = StateManager(args.state)
    state.load()
    summary = load_campaign(data, state, args.vault, systems_path=ROOT / "data" / "systems")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
