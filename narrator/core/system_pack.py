"""Contrato ejecutable para los paquetes de sistema TTRPG.

El paquete es la autoridad de configuración del sistema activo. No contiene
estado de campaña ni texto de manual: solo describe cómo enrutar y resolver
conocimiento y reglas específicas del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


REQUIRED_FIELDS = (
    "slug",
    "sistema",
    "edition",
    "vocabulario",
    "character_sheet_schema",
    "resolution",
    "lorebook",
    "knowledge",
    "llm_system_prompt",
)


@dataclass(frozen=True)
class KnowledgePolicy:
    brain_system: str
    preferred_sources: tuple[str, ...] = ("manual", "system", "universal")
    universal_fallback: bool = True

    def __post_init__(self) -> None:
        allowed = {"manual", "system", "universal", "campaign", "state"}
        invalid = set(self.preferred_sources) - allowed
        if invalid:
            raise ValueError(f"Fuentes de conocimiento inválidas: {sorted(invalid)}")


@dataclass(frozen=True)
class SystemPack:
    slug: str
    sistema: str
    edition: str
    vocabulario: dict[str, Any] = field(default_factory=dict)
    character_sheet_schema: dict[str, Any] = field(default_factory=dict)
    resolution: dict[str, Any] = field(default_factory=dict)
    lorebook: list[dict[str, Any]] = field(default_factory=list)
    factions: dict[str, dict[str, Any]] = field(default_factory=dict)
    fronts: dict[str, dict[str, Any]] = field(default_factory=dict)
    llm_system_prompt: str = ""
    knowledge: KnowledgePolicy = field(
        default_factory=lambda: KnowledgePolicy(brain_system="generic")
    )
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], expected_slug: str | None = None) -> "SystemPack":
        missing = [key for key in REQUIRED_FIELDS if key not in data]
        if missing:
            raise ValueError(f"System Pack inválido: faltan campos {', '.join(missing)}")

        slug = str(data["slug"])
        if expected_slug and slug != expected_slug:
            raise ValueError(
                f"System Pack '{expected_slug}' declara slug '{slug}'"
            )

        knowledge_data = data.get("knowledge") or {}
        if not isinstance(knowledge_data, dict):
            raise ValueError("System Pack: 'knowledge' debe ser un mapa YAML")

        preferred = knowledge_data.get(
            "preferred_sources", ["manual", "system", "universal"]
        )
        if isinstance(preferred, str):
            preferred = [preferred]

        policy = KnowledgePolicy(
            brain_system=str(knowledge_data.get("brain_system") or slug),
            preferred_sources=tuple(str(x) for x in preferred),
            universal_fallback=bool(knowledge_data.get("universal_fallback", True)),
        )

        return cls(
            slug=slug,
            sistema=str(data["sistema"]),
            edition=str(data["edition"]),
            vocabulario=data.get("vocabulario") or {},
            character_sheet_schema=data.get("character_sheet_schema") or {},
            resolution=data.get("resolution") or {},
            lorebook=data.get("lorebook") or [],
            factions={
                str(item.get("slug") or name): dict(item)
                for name, item in (data.get("factions") or {}).items()
                if isinstance(item, dict)
            },
            fronts={
                str(item.get("slug") or name): dict(item)
                for name, item in (data.get("fronts") or {}).items()
                if isinstance(item, dict)
            },
            llm_system_prompt=str(data.get("llm_system_prompt") or ""),
            knowledge=policy,
            raw=dict(data),
        )

    @classmethod
    def load(cls, slug: str, systems_path: str | Path = "data/systems") -> "SystemPack":
        path = Path(systems_path) / f"{slug}.yaml"
        if not path.exists():
            path = Path(systems_path) / "generic.yaml"
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return cls.from_dict(data, expected_slug=None if path.name == "generic.yaml" else slug)


    def validate_front_contract(self) -> list[str]:
        """Valida identificadores declarativos de facciones/frentes del pack."""
        errors = []
        for slug, faction in self.factions.items():
            if not str(slug).strip():
                errors.append("facción sin slug")
            if not str(faction.get("nombre") or slug).strip():
                errors.append(f"facción '{slug}' sin nombre")
        for slug, front in self.fronts.items():
            if not str(slug).strip():
                errors.append("frente sin slug")
            if not str(front.get("nombre") or slug).strip():
                errors.append(f"frente '{slug}' sin nombre")
            faction = str(front.get("faccion") or "").strip()
            if faction and faction not in self.factions:
                errors.append(f"frente '{slug}' referencia facción inexistente '{faction}'")
        return errors

    def front_definition(self, slug: str) -> dict[str, Any]:
        return dict(self.fronts.get(str(slug).strip(), {}))

    def knowledge_query(self, base_query: str) -> str:
        """Añade el identificador del sistema sin contaminar el texto narrativo."""
        return f"{base_query} sistema {self.sistema} {self.edition}".strip()
