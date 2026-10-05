"""Contrato formal de un turno de narración.

El contrato hace explícita la frontera entre determinismo y generación:
Python interpreta, recupera conocimiento, resuelve mecánica y prepara estado;
el LLM recibe ese resultado y genera únicamente la capa narrativa.
"""

from dataclasses import dataclass, field
from typing import Any


TURN_STAGES = (
    "input",
    "interpretation",
    "intent",
    "rule_need",
    "retrieval",
    "resolution",
    "state_update",
    "context_selection",
    "narrative_prompt",
    "llm",
    "post_process",
    "persist",
)


@dataclass
class TurnContract:
    """Estado trazable de un turno completo."""

    input_text: str
    system_slug: str
    character_snapshot: dict[str, Any] = field(default_factory=dict)

    interpretation: str = ""
    intent: str = ""
    rule_need: str = ""
    retrieved_context: str = ""
    state_snapshot: str = ""
    mechanical_resolution: dict[str, Any] | None = None
    state_delta: dict[str, Any] = field(default_factory=dict)

    narrative_prompt: str = ""
    llm_output: str = ""
    final_output: str = ""

    provenance: list[str] = field(default_factory=list)
    stage: str = "input"

    def advance(self, stage: str) -> None:
        """Avanza el contrato a una etapa conocida."""
        if stage not in TURN_STAGES:
            raise ValueError(f"Etapa de turno desconocida: {stage}")
        self.stage = stage

    def record_source(self, source: str) -> None:
        if source and source not in self.provenance:
            self.provenance.append(source)

    @property
    def mechanical_verdict(self) -> str:
        if not self.mechanical_resolution:
            return ""
        return str(self.mechanical_resolution.get("detalle", ""))

    @property
    def mechanical_band(self) -> str:
        if not self.mechanical_resolution:
            return ""
        return str(self.mechanical_resolution.get("banda", ""))

    def narrative_input(self) -> dict[str, Any]:
        """Payload explícito que puede entregarse al adaptador del LLM."""
        return {
            "input": self.input_text,
            "system": self.system_slug,
            "intent": self.intent,
            "rule_need": self.rule_need,
            "mechanical_resolution": self.mechanical_resolution,
            "state_snapshot": self.state_snapshot,
            "retrieved_context": self.retrieved_context,
            "prompt": self.narrative_prompt,
        }

    def mark_llm_output(self, text: str) -> None:
        self.llm_output = text or ""
        self.final_output = self.llm_output
        self.advance("post_process")

    def mark_persisted(self) -> None:
        self.advance("persist")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "input": self.input_text,
            "system": self.system_slug,
            "intent": self.intent,
            "rule_need": self.rule_need,
            "mechanical_resolution": self.mechanical_resolution,
            "state_delta": self.state_delta,
            "provenance": list(self.provenance),
        }
