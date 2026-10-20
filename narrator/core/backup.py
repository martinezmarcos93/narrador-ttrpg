"""Respaldo y recuperación de los datos de una partida (Fase N).

Empaqueta en un zip con fecha: estado de campaña, vault, base de la capa web y
config local. Restaurar primero respalda lo actual (nunca se pierde nada).
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

from narrator.logger import logger

DEFAULT_ITEMS = ("estado_campana.yaml", "vault", "data/web", "config/local.yaml")


def crear_respaldo(root: str | Path, dest: str | Path = "backups", *,
                   items=DEFAULT_ITEMS, keep: int = 10, label: str = "") -> Path:
    root, dest = Path(root), Path(root) / dest if not Path(dest).is_absolute() else Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    archive = dest / f"narrador-{stamp}{('-' + label) if label else ''}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            path = root / item
            if path.is_file():
                zf.write(path, item)
            elif path.is_dir():
                for file in sorted(path.rglob("*")):
                    if file.is_file():
                        zf.write(file, file.relative_to(root).as_posix())
    for old in listar_respaldos(dest)[:-keep] if keep > 0 else []:
        old.unlink()
    logger.info("Respaldo creado: %s", archive)
    return archive


def listar_respaldos(dest: str | Path) -> list[Path]:
    return sorted(Path(dest).glob("narrador-*.zip"))


def restaurar_respaldo(archive: str | Path, root: str | Path, *, dest: str | Path = "backups") -> Path:
    """Restaura ``archive`` sobre ``root``; antes respalda el estado actual."""
    archive, root = Path(archive), Path(root)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        for name in names:
            target = (root / name).resolve()
            if root.resolve() not in target.parents and target != root.resolve():
                raise ValueError(f"ruta insegura en el respaldo: {name}")
        safety = crear_respaldo(root, dest, label="antes-de-restaurar", keep=0)
        zf.extractall(root)
    logger.info("Restaurado %s (respaldo previo: %s)", archive, safety)
    return safety
