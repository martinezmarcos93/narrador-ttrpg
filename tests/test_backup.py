import zipfile

import pytest

from narrator.core.backup import crear_respaldo, listar_respaldos, restaurar_respaldo


def _project(tmp_path):
    (tmp_path / "estado_campana.yaml").write_text("meta: {campana: A}\n", encoding="utf-8")
    (tmp_path / "vault" / "NPCs").mkdir(parents=True)
    (tmp_path / "vault" / "NPCs" / "Ana.md").write_text("# Ana\n", encoding="utf-8")
    return tmp_path


def test_backup_restore_roundtrip_with_safety_copy(tmp_path):
    root = _project(tmp_path)
    archive = crear_respaldo(root)
    (root / "estado_campana.yaml").write_text("meta: {campana: ROTO}\n", encoding="utf-8")
    safety = restaurar_respaldo(archive, root)
    assert "campana: A" in (root / "estado_campana.yaml").read_text(encoding="utf-8")
    assert "ROTO" in zipfile.ZipFile(safety).read("estado_campana.yaml").decode("utf-8")
    assert (root / "vault" / "NPCs" / "Ana.md").exists()


def test_rotation_keeps_last_n(tmp_path):
    root = _project(tmp_path)
    for _ in range(4):
        crear_respaldo(root, keep=2)
    assert len(listar_respaldos(root / "backups")) == 2


def test_restore_rejects_path_traversal(tmp_path):
    root = _project(tmp_path)
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../fuera.txt", "x")
    with pytest.raises(ValueError):
        restaurar_respaldo(evil, root)
