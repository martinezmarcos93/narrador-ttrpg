#!/usr/bin/env python3
"""Smoke E2E + pen-test básico de la API web contra un servidor HTTP real (L/K).

Levanta Flask en un puerto local con una campaña de ejemplo cargada en un
directorio temporal y verifica: salud, autenticación, aislamiento entre
usuarios, límites de tamaño, JSON malformado, path traversal en /static,
cabeceras de seguridad, ausencia de stack traces y (con --llm) un turno real.

    python scripts/smoke_web.py            # sin LLM (rápido)
    python scripts/smoke_web.py --llm --model qwen3:1.7b
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    import requests
    import yaml
    from werkzeug.serving import make_server

    from narrator.core.campaign import load_campaign, read_manifest
    from narrator.core.narrator_service import NarratorService
    from narrator.web.app import create_app
    from narrator.web.service import WebApplicationService
    from narrator.web.store import WebStore

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--model", default="qwen3:1.7b")
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "config.yaml").write_text(yaml.safe_dump({
            "systems_path": str(ROOT / "data/systems"),
            "vault": {"path": str(tmp / "vault"), "live_updates": False},
            "cerebro": {"path": str(ROOT / "cerebro")},
            "estado": {"path": str(tmp / "estado.yaml")},
        }), encoding="utf-8")
        narrator = NarratorService(config_path=str(tmp / "config.yaml"))
        load_campaign(read_manifest(ROOT / "data/campaigns/noches_de_ceniza.yaml"),
                      narrator.state_manager, tmp / "vault")
        store = WebStore(tmp / "web.db")
        _, ana = store.crear_clave("ana")
        _, beto = store.crear_clave("beto")
        os.environ["NARRATOR_MAX_REQUEST_BYTES"] = "4096"
        os.environ.pop("NARRATOR_API_KEY", None)
        llm = None
        if args.llm:
            from narrator.core.llm_client import LLMClient

            llm = LLMClient(model=args.model)
        app = create_app(web_service=WebApplicationService(narrator, store, llm=llm))
        server = make_server("127.0.0.1", 0, app, threaded=True)
        base = f"http://127.0.0.1:{server.server_port}"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        A = {"Authorization": f"Bearer {ana}"}
        B = {"Authorization": f"Bearer {beto}"}
        try:
            r = requests.get(f"{base}/api/v1/health", timeout=10)
            check("salud pública", r.status_code == 200)
            check("cabeceras de seguridad", all(h in r.headers for h in (
                "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options")))
            check("sin clave -> 401", requests.post(f"{base}/api/v1/sessions", json={}, timeout=10).status_code == 401)
            check("clave inventada -> 401", requests.get(
                f"{base}/api/v1/sessions", headers={"Authorization": "Bearer nrr_falsa"}, timeout=10).status_code == 401)
            sid = requests.post(f"{base}/api/v1/sessions", json={"campaign": "Noches de Ceniza",
                                "system": "vtm_v20"}, headers=A, timeout=10).json()["session_id"]
            check("aislamiento entre usuarios", requests.get(
                f"{base}/api/v1/sessions/{sid}/world", headers=B, timeout=10).status_code == 404)
            big = requests.post(f"{base}/api/v1/turns", headers=A, timeout=10,
                                data=json.dumps({"session_id": sid, "text": "x" * 10000}),)
            check("cuerpo excesivo -> 413", big.status_code == 413)
            bad = requests.post(f"{base}/api/v1/turns", headers={**A, "Content-Type": "application/json"},
                                data="{roto", timeout=10)
            check("JSON malformado -> 400 sin traza", bad.status_code == 400 and "Traceback" not in bad.text)
            leaked = []
            for path in ("/static/%2e%2e/%2e%2e/config/config.yaml",
                         "/static/..%2f..%2fconfig%2fconfig.yaml",
                         "/static/%2e%2e%2f%2e%2e%2festado_campana.yaml"):
                resp = requests.get(f"{base}{path}", timeout=10)
                if resp.status_code == 200 or "sistema_activo" in resp.text:
                    leaked.append(path)
            check("path traversal en /static", not leaked, ", ".join(leaked))
            check("interfaz servida", requests.get(f"{base}/", timeout=10).status_code == 200)
            if args.llm:
                turn = requests.post(f"{base}/api/v1/turns", headers=A, timeout=300,
                                     json={"session_id": sid, "text": "Le pregunto a la Hermana Clara qué pasa"})
                body = turn.json()
                check("turno real con LLM", turn.status_code == 200 and bool(body.get("text")),
                      (body.get("text") or "")[:160])
                check("turno sin fugas de secretos", body.get("leaks") == 0)
        finally:
            server.shutdown()

    for name, ok, detail in checks:
        print(f"{'OK ' if ok else 'FALLA'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
