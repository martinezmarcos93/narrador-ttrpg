#!/usr/bin/env python3
"""Respaldo/recuperación: python scripts/backup.py crear|listar|restaurar <zip>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from narrator.core.backup import crear_respaldo, listar_respaldos, restaurar_respaldo

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["crear", "listar", "restaurar"])
    parser.add_argument("archivo", nargs="?")
    parser.add_argument("--keep", type=int, default=10)
    args = parser.parse_args()
    if args.accion == "crear":
        print(crear_respaldo(ROOT, keep=args.keep))
    elif args.accion == "listar":
        for path in listar_respaldos(ROOT / "backups"):
            print(path.name)
    else:
        if not args.archivo:
            parser.error("indicá el zip a restaurar")
        print("respaldo previo:", restaurar_respaldo(args.archivo, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
