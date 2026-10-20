"""Contrato común de procedencia para contexto recuperado."""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_LAYERS = {"universal", "system", "manual", "campaign", "state"}
HOUSE_RULE_TYPES = {"regla_casa", "regla_de_la_casa", "house_rule"}


@dataclass(frozen=True)
class ContextFragment:
    text: str
    source: str
    layer: str
    title: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.layer not in VALID_LAYERS:
            raise ValueError(f"Capa de contexto inválida: {self.layer}")

    @property
    def is_house_rule(self) -> bool:
        """Excepción formal a la precedencia: una regla de la casa de la campaña
        prevalece sobre el manual (pero nunca sobre el estado)."""
        meta = self.metadata or {}
        kind = str(meta.get("tipo", meta.get("kind", ""))).strip().lower()
        return self.layer == "campaign" and (kind in HOUSE_RULE_TYPES or meta.get("house_rule") is True)

    @property
    def authority(self) -> int:
        if self.is_house_rule:
            return 45
        return {"state": 50, "manual": 40, "system": 30, "campaign": 20, "universal": 10}[self.layer]

    def safe_text(self) -> str:
        """Texto apto para el prompt: los documentos se sanean, el estado no."""
        if self.layer == "state":
            return self.text.strip()
        from narrator.core.injection_guard import sanitize_document_text

        return sanitize_document_text(self.text).text

    def injection_findings(self) -> list[str]:
        if self.layer == "state":
            return []
        from narrator.core.injection_guard import sanitize_document_text

        return sanitize_document_text(self.text).findings

    @property
    def citation(self) -> str:
        """Cita verificable del fragmento ('' si no tiene ubicación precisa)."""
        meta = self.metadata or {}
        if meta.get("citation"):
            return str(meta["citation"])
        book = meta.get("libro") or meta.get("book")
        pages = meta.get("paginas") or meta.get("pages") or meta.get("page")
        if book and pages:
            return f"{book}, pág. {pages}"
        if self.layer in {"universal", "state"} and meta.get("id"):
            return f"cerebro:{meta['id']}"
        return ""

    def render(self) -> str:
        label = "CAMPAIGN · REGLA DE LA CASA" if self.is_house_rule else self.layer.upper()
        title = f" | {self.title}" if self.title else ""
        source = f" | fuente: {self.source}" if self.source else ""
        cite = self.citation
        cite_txt = f" | cita: {cite}" if cite and cite not in (self.title or "") else ""
        return f"[{label}{title}{source}{cite_txt}]\n{self.safe_text()}"


def render_context(fragments: list[ContextFragment], max_words: int) -> str:
    ordered = sorted(fragments, key=lambda f: (f.authority, f.score), reverse=True)
    output, total = [], 0
    if any(f.is_house_rule for f in fragments) and any(f.layer == "manual" for f in fragments):
        notice = ("PRECEDENCIA: si una REGLA DE LA CASA contradice al manual, "
                  "vale la regla de la casa.")
        output.append(notice)
        total += len(notice.split())
    for fragment in ordered:
        block = fragment.render()
        words = len(block.split())
        if total + words > max_words:
            remaining = max_words - total
            if remaining > 30:
                output.append(" ".join(block.split()[:remaining]))
            break
        output.append(block)
        total += words
    return "\n---\n".join(output)
