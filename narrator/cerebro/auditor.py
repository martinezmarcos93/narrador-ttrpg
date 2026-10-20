"""Auditoría determinista del Cerebro (B1).

Revisa las neuronas sin usar embeddings ni LLM:

- esquema: frontmatter canónico (id, title, system, kind, tags) y sin claves legacy;
- IDs: formato ``<capa>-<slug>``, únicos y consistentes con la capa;
- enlaces: cada ``[[id]]`` apunta a una neurona existente; neuronas huérfanas;
- cobertura: conceptos TTRPG requeridos (``data/cerebro/conceptos_requeridos.yaml``)
  sin ninguna neurona que los trate;
- ground truth: IDs relevantes del benchmark que no existen en el cerebro.

Uso: ``python scripts/audit_brain.py`` (ver ``--help``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from narrator.core.entity_registry import fold_name

CANONICAL_KEYS = ("id", "title", "system", "kind", "tags")
LEGACY_KEYS = {
    "titulo": "title",
    "sistema": "system",
    "tipo": "kind",
    "capa": "layer",
    "fuente": "source",
    "ver_tambien": "also",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*-[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[\[([^|\]]+)(?:\|[^\]]+)?\]\]")


@dataclass
class Neuron:
    path: Path
    meta: dict[str, Any]
    body: str

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or "").strip()

    @property
    def links(self) -> list[str]:
        return [link.strip() for link in LINK_RE.findall(self.body)]

    def text_for_coverage(self) -> str:
        tags = self.meta.get("tags") or []
        if not isinstance(tags, list):
            tags = [tags]
        title = self.meta.get("title", self.meta.get("titulo", ""))
        return fold_name(" ".join([self.id, str(title), " ".join(map(str, tags))]))


@dataclass
class AuditReport:
    neurons: int = 0
    schema_errors: list[str] = field(default_factory=list)
    id_errors: list[str] = field(default_factory=list)
    broken_links: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    concept_gaps: list[str] = field(default_factory=list)
    covered_concepts: dict[str, list[str]] = field(default_factory=dict)
    ground_truth_missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.schema_errors or self.id_errors or self.broken_links
            or self.concept_gaps or self.ground_truth_missing
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "neurons": self.neurons,
            "schema_errors": self.schema_errors,
            "id_errors": self.id_errors,
            "broken_links": self.broken_links,
            "orphans": self.orphans,
            "concept_gaps": self.concept_gaps,
            "covered_concepts": self.covered_concepts,
            "ground_truth_missing": self.ground_truth_missing,
        }


def load_neurons(root: Path) -> list[Neuron]:
    neurons = []
    for path in sorted(Path(root).rglob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta: dict[str, Any] = {}
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) == 3:
                try:
                    loaded = yaml.safe_load(parts[1]) or {}
                    meta = loaded if isinstance(loaded, dict) else {}
                except yaml.YAMLError:
                    meta = {"__yaml_error__": True}
                body = parts[2]
        neurons.append(Neuron(path, meta, body))
    return neurons


# Perfil "sistema": neuronas generadas por el barredor. Su id ES la ruta dentro
# del vault (los títulos se repiten entre manuales) y usan claves en español.
SYSTEM_PROFILE_KEYS = ("id", "titulo", "tipo", "capa", "sistema", "fuente")


def _check_system_schema(neuron: Neuron, root: Path, report: AuditReport) -> None:
    rel = neuron.path.relative_to(root).as_posix()
    if neuron.meta.get("__yaml_error__"):
        report.schema_errors.append(f"{rel}: frontmatter YAML inválido")
        return
    for key in SYSTEM_PROFILE_KEYS:
        if key not in neuron.meta:
            report.schema_errors.append(f"{rel}: falta '{key}'")
    expected = rel[:-3] if rel.endswith(".md") else rel
    prefix = root.name + "/" if root.name == "sistemas" else ""
    if neuron.id and neuron.id != prefix + expected and not neuron.id.endswith("/" + expected):
        report.id_errors.append(f"{rel}: id '{neuron.id}' no coincide con su ruta")


def _check_schema(neuron: Neuron, root: Path, report: AuditReport) -> None:
    rel = neuron.path.relative_to(root).as_posix()
    if neuron.meta.get("__yaml_error__"):
        report.schema_errors.append(f"{rel}: frontmatter YAML inválido")
        return
    for key in CANONICAL_KEYS:
        if key not in neuron.meta:
            report.schema_errors.append(f"{rel}: falta '{key}'")
    for legacy, canonical in LEGACY_KEYS.items():
        if legacy in neuron.meta:
            report.schema_errors.append(f"{rel}: clave legacy '{legacy}' (usar '{canonical}')")
    tags = neuron.meta.get("tags")
    if tags is not None and not isinstance(tags, list):
        report.schema_errors.append(f"{rel}: 'tags' debe ser lista")


def _check_ids(neurons: list[Neuron], root: Path, report: AuditReport) -> None:
    seen: dict[str, str] = {}
    for neuron in neurons:
        rel = neuron.path.relative_to(root).as_posix()
        nid = neuron.id
        if not nid:
            continue  # ya reportado por esquema
        if not ID_RE.match(nid):
            report.id_errors.append(f"{rel}: id '{nid}' no cumple <capa>-<slug> en minúsculas")
        system = str(neuron.meta.get("system") or "").strip()
        expected_prefix = "universal" if system in {"", "universal"} else system
        if not nid.startswith(f"{expected_prefix}-") and not nid.startswith(
            f"{expected_prefix.replace('_', '-')}-"
        ):
            report.id_errors.append(
                f"{rel}: id '{nid}' debería empezar con '{expected_prefix}-'"
            )
        if nid in seen:
            report.id_errors.append(f"{rel}: id duplicado '{nid}' (también en {seen[nid]})")
        seen[nid] = rel


def _check_links(neurons: list[Neuron], root: Path, report: AuditReport) -> None:
    ids = {n.id for n in neurons if n.id}
    linked: set[str] = set()
    for neuron in neurons:
        rel = neuron.path.relative_to(root).as_posix()
        for link in neuron.links:
            linked.add(link)
            if link not in ids:
                report.broken_links.append(f"{rel}: [[{link}]] no existe")
    for neuron in neurons:
        if neuron.id and neuron.id not in linked and neuron.meta.get("kind") != "index":
            report.orphans.append(neuron.id)


def _check_coverage(neurons: list[Neuron], concepts: dict[str, Any], report: AuditReport) -> None:
    texts = {n.id: n.text_for_coverage() for n in neurons if n.id}
    for concept, spec in sorted(concepts.items()):
        keywords = [fold_name(k) for k in (spec or {}).get("keywords", [concept])]
        hits = sorted(nid for nid, text in texts.items() if any(k in text for k in keywords))
        if hits:
            report.covered_concepts[concept] = hits
        else:
            report.concept_gaps.append(concept)


def _check_ground_truth(neurons: list[Neuron], ground_truth: Path, report: AuditReport) -> None:
    if not ground_truth.exists():
        return
    data = yaml.safe_load(ground_truth.read_text(encoding="utf-8")) or {}
    ids = {n.id for n in neurons}
    for case in data.get("cases", []):
        for rid in case.get("relevant_ids", []):
            if str(rid) not in ids:
                report.ground_truth_missing.append(f"{case.get('id')}: {rid}")


def audit_brain(
    root: str | Path,
    *,
    concepts_path: str | Path | None = None,
    ground_truth_path: str | Path | None = None,
    profile: str = "universal",
) -> AuditReport:
    """``profile``: "universal" (esquema canónico estricto) o "sistema" (barredor)."""
    if profile not in {"universal", "sistema"}:
        raise ValueError(f"perfil desconocido: {profile}")
    root = Path(root)
    neurons = load_neurons(root)
    report = AuditReport(neurons=len(neurons))
    if profile == "sistema":
        for neuron in neurons:
            _check_system_schema(neuron, root, report)
        seen: dict[str, str] = {}
        for neuron in neurons:
            if neuron.id in seen:
                report.id_errors.append(f"id duplicado '{neuron.id}'")
            seen[neuron.id] = neuron.path.name
        _check_links(neurons, root, report)
        report.orphans = []  # en manuales, las hojas sin menciones son normales
        return report
    for neuron in neurons:
        _check_schema(neuron, root, report)
    _check_ids(neurons, root, report)
    _check_links(neurons, root, report)
    if concepts_path and Path(concepts_path).exists():
        concepts = yaml.safe_load(Path(concepts_path).read_text(encoding="utf-8")) or {}
        _check_coverage(neurons, concepts.get("conceptos", {}), report)
    if ground_truth_path:
        _check_ground_truth(neurons, Path(ground_truth_path), report)
    return report
