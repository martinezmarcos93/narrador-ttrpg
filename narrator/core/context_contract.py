"""Contrato común de procedencia para contexto recuperado."""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_LAYERS = {"universal", "system", "manual", "campaign", "state"}


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
    def authority(self) -> int:
        return {"state": 50, "manual": 40, "system": 30, "campaign": 20, "universal": 10}[self.layer]

    def render(self) -> str:
        label = self.layer.upper()
        title = f" | {self.title}" if self.title else ""
        source = f" | fuente: {self.source}" if self.source else ""
        return f"[{label}{title}{source}]\n{self.text.strip()}"


def render_context(fragments: list[ContextFragment], max_words: int) -> str:
    ordered = sorted(fragments, key=lambda f: (f.authority, f.score), reverse=True)
    output, total = [], 0
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
