#!/usr/bin/env python3
"""Administra claves de API de la capa web (crear, listar, revocar, rotar).

La clave en texto plano se muestra UNA sola vez; en la base queda su hash.
    python scripts/manage_api_keys.py crear ana
    python scripts/manage_api_keys.py listar
    python scripts/manage_api_keys.py rotar <id>
    python scripts/manage_api_keys.py revocar <id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from narrator.web.store import WebStore

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("accion", choices=["crear", "listar", "revocar", "rotar"])
    parser.add_argument("valor", nargs="?", help="dueño (crear) o id de clave (revocar/rotar)")
    parser.add_argument("--db", default=os.getenv("NARRATOR_WEB_DB", str(ROOT / "data/web/narrador_web.db")))
    args = parser.parse_args()
    store = WebStore(args.db)
    if args.accion == "listar":
        print(json.dumps(store.listar_claves(), ensure_ascii=False, indent=2))
        return 0
    if not args.valor:
        parser.error("falta el dueño o el id de la clave")
    if args.accion == "crear":
        key_id, token = store.crear_clave(args.valor)
    elif args.accion == "rotar":
        key_id, token = store.rotar_clave(args.valor)
    else:
        ok = store.revocar_clave(args.valor)
        print("revocada" if ok else "no existe o ya estaba revocada")
        return 0 if ok else 1
    print(json.dumps({"id": key_id, "clave": token,
                      "aviso": "guardala ahora: no se vuelve a mostrar"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
