"""Protección ante prompt injection en documentos recuperados (B3/L).

Manuales, notas del vault y neuronas son **datos**, no instrucciones. Antes de
llegar al prompt, su texto pasa por ``sanitize_document_text``, que:

1. elimina bloques técnicos que el motor interpreta (```json-proposal, ```json),
   para que un documento no pueda "proponer" cambios de estado;
2. elimina etiquetas técnicas del narrador ([[NUEVO_NPC]], [state: ...]);
3. reemplaza frases que intentan dar órdenes al modelo ("ignorá las
   instrucciones", "you are now...", marcadores de rol de chat).

El estado de campaña (capa ``state``) lo genera Python y no se sanea.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FENCED_TECH = re.compile(r"```\s*(?:json-proposal|json)\b.*?(?:```|$)", re.IGNORECASE | re.DOTALL)
_TECH_TAGS = re.compile(
    r"\[\[/?(?:NUEVO_NPC|NUEVA_LOCACION)\]\]|\[state:[^\]]*\]", re.IGNORECASE
)
_ROLE_MARKERS = re.compile(
    r"<\|?/?(?:im_start|im_end|system|assistant|user)\|?>|^\s*(?:system|assistant)\s*:",
    re.IGNORECASE | re.MULTILINE,
)
_INSTRUCTION_PATTERNS = [
    r"ignor[aáe]\w*\s+(?:todas?\s+)?(?:las\s+|tus\s+)?(?:instrucciones|reglas|indicaciones)",
    r"olvid[aáe]\w*\s+(?:todas?\s+)?(?:las\s+|tus\s+)?(?:instrucciones|reglas|indicaciones)",
    r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
    r"a\s+partir\s+de\s+ahora\s+(?:eres|sos|serás|vas\s+a\s+ser)",
    r"you\s+are\s+now\s+",
    r"nuevas\s+instrucciones\s*:",
    r"new\s+instructions\s*:",
    r"(?:revel[aáe]\w*|mostr[aá]\w*|reveal)\s+(?:el|los|la|las|the)?\s*(?:secretos?|system\s+prompt|prompt\s+del\s+sistema)",
    r"(?:system|sistema)\s+prompt",
    r"###\s*(?:instruction|instrucci[oó]n)",
]
_INSTRUCTION_RE = re.compile("|".join(_INSTRUCTION_PATTERNS), re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?¡¿\n])\s+")

PLACEHOLDER = "[instrucción embebida omitida]"


@dataclass
class SanitizeResult:
    text: str
    findings: list[str] = field(default_factory=list)

    @property
    def flagged(self) -> bool:
        return bool(self.findings)


def sanitize_document_text(text: str) -> SanitizeResult:
    findings: list[str] = []
    clean = str(text or "")

    if _FENCED_TECH.search(clean):
        findings.append("bloque_tecnico")
        clean = _FENCED_TECH.sub("[bloque técnico omitido]", clean)
    if _TECH_TAGS.search(clean):
        findings.append("etiqueta_tecnica")
        clean = _TECH_TAGS.sub("", clean)
    if _ROLE_MARKERS.search(clean):
        findings.append("marcador_de_rol")
        clean = _ROLE_MARKERS.sub("", clean)

    if _INSTRUCTION_RE.search(clean):
        findings.append("instruccion_embebida")
        sentences = _SENTENCE_SPLIT.split(clean)
        clean = " ".join(
            PLACEHOLDER if _INSTRUCTION_RE.search(sentence) else sentence
            for sentence in sentences
        )
    return SanitizeResult(clean.strip(), findings)
