#!/usr/bin/env python3
"""Juega una campaña de punta a punta sin GUI (Fase G + Fase 2 IA-vs-IA).

Carga el manifiesto en un directorio aislado, y en cada turno un jugador IA
(PlayerAgent) actúa y el narrador del motor responde con el pipeline real
(NarratorService.run_turn). Reporta métricas de coherencia:

- leak_rate: turnos con material secreto todavía oculto en la narración;
- proposal_validity: propuestas estructuradas aceptadas / emitidas;
- dice_first_miss_rate: resultados narrados sin tirada;
- causal_activations, latency_ms_mean, discoveries.

Uso:
    python scripts/play_campaign.py data/campaigns/noches_de_ceniza.yaml --turns 5 --model qwen3:1.7b
    ... --gate --max-leak-rate 0.1     # exit 1 si se superan umbrales
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def summarize(turns: list[dict]) -> dict:
    n = len(turns) or 1
    proposals = [t for t in turns if t.get("proposal")]
    applied = [t for t in proposals if (t.get("proposal_result") or {}).get("applied")]
    latencies = [t["contract"]["state_delta"].get("latency_ms", 0) for t in turns]
    return {
        "turns": len(turns),
        "leak_rate": round(sum(1 for t in turns if t["leaks"]) / n, 3),
        "proposal_validity": round(len(applied) / len(proposals), 3) if proposals else None,
        "proposals": len(proposals),
        "dice_first_miss_rate": round(sum(1 for t in turns if t.get("dice_first_miss")) / n, 3),
        "context_echo_rate": round(sum(1 for t in turns if t.get("context_echo")) / n, 3),
        "causal_activations": sum(
            int((t["contract"].get("causal_metrics") or {}).get("activations", 0)) for t in turns),
        "latency_ms_mean": round(sum(latencies) / n, 1),
        "intents": [t["intent"] for t in turns],
    }


def play(manifest: Path, *, turns: int, narrator_llm, player_llm, archetype: str,
         workdir: Path) -> dict:
    import yaml

    from narrator.agents.player_agent import PlayerAgent
    from narrator.core import secrets
    from narrator.core.campaign import load_campaign, read_manifest
    from narrator.core.dice_first_guard import check as dice_first_check
    from narrator.core.narrator_service import NarratorService

    data = read_manifest(manifest)
    config = workdir / "config.yaml"
    config.write_text(yaml.safe_dump({
        "systems_path": str(ROOT / "data" / "systems"),
        "vault": {"path": str(workdir / "vault"), "live_updates": False},
        "cerebro": {"path": str(ROOT / "cerebro"), "embedding_model": "nomic-embed-text"},
        "estado": {"path": str(workdir / "estado.yaml")},
    }, allow_unicode=True), encoding="utf-8")
    service = NarratorService(config_path=str(config))
    summary = load_campaign(data, service.state_manager, workdir / "vault",
                            systems_path=ROOT / "data" / "systems")
    service.state_manager.start_session()
    app_state = {
        "system_slug": summary["sistema"],
        "character": summary["protagonista"],
        "messages": [],
    }
    player = PlayerAgent(player_llm, archetype=archetype)
    scene = (f"Comienza la crónica '{summary['campana']}'. Estás en "
             f"{service.state_manager.get_location()}.")
    results = []
    for _ in range(turns):
        action = player.decide_action(scene, summary["protagonista"]) or "Observo a mi alrededor."
        turn = service.run_turn(app_state, action, narrator_llm)
        turn["action"] = action
        turn["dice_first_miss"] = bool(dice_first_check(action, turn["text"], dice_rolled=False))
        results.append(turn)
        scene = turn["text"] or scene
    discovered = {
        sid: entry["descubiertas"]["jugador"]
        for sid, entry in service.state_manager.data.get("secretos", {}).items()
    }
    report = summarize(results)
    report["discoveries"] = discovered
    report["final_leaks"] = secrets.find_leaks(
        " ".join(t["text"] for t in results), service.state_manager)
    report["transcript"] = [{"jugador": t["action"], "narrador": t["text"]} for t in results]
    return report


def main() -> int:
    from narrator.agents.player_agent import ARCHETYPES
    from narrator.core.llm_client import LLMClient

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--model", default="qwen3:1.7b")
    parser.add_argument("--player-model")
    parser.add_argument("--archetype", default="cauteloso", choices=list(ARCHETYPES))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--max-leak-rate", type=float, default=0.1)
    args = parser.parse_args()

    narrator = LLMClient(model=args.model)
    player = LLMClient(model=args.player_model or args.model)
    with tempfile.TemporaryDirectory() as tmp:
        report = play(args.manifest, turns=args.turns, narrator_llm=narrator,
                      player_llm=player, archetype=args.archetype, workdir=Path(tmp))
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    if args.gate and report["leak_rate"] > args.max_leak_rate:
        print("GATE: FALLÓ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
