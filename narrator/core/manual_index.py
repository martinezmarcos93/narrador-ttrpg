"""Recuperación específica sobre el manual adjunto a la sesión (B3).

El texto del manual (con saltos de página ``\\f`` si vienen de PyMuPDF) se
divide en pasajes de ~180 palabras con su página, y se rankea con BM25 sobre
tokens normalizados (sin tildes). Cada pasaje queda citable: "pág. N".
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from narrator.core.entity_registry import fold_name

_TOKEN_RE = re.compile(r"[a-z0-9ñ]{3,}")
_STOPWORDS = {
    "que", "los", "las", "del", "con", "por", "para", "una", "uno", "unos", "unas", "como",
    "mas", "pero", "sus", "este", "esta", "esto", "ese", "esa", "son", "fue", "ser", "hay",
    "sin", "sobre", "entre", "cuando", "donde", "todo", "toda", "todos", "puede", "pueden",
    "the", "and", "for", "with", "that", "this", "from", "are", "you", "your",
}
PASSAGE_WORDS = 180


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(fold_name(text)) if t not in _STOPWORDS]


@dataclass(frozen=True)
class Passage:
    index: int
    page: int
    text: str


def split_passages(text: str, max_words: int = PASSAGE_WORDS) -> list[Passage]:
    passages: list[Passage] = []
    pages = str(text or "").split("\f")
    for page_number, page in enumerate(pages, start=1):
        buffer: list[str] = []
        for paragraph in re.split(r"\n\s*\n", page):
            words = paragraph.split()
            if not words:
                continue
            while words:
                room = max_words - len(buffer)
                buffer.extend(words[:room])
                words = words[room:]
                if len(buffer) >= max_words:
                    passages.append(Passage(len(passages), page_number, " ".join(buffer)))
                    buffer = []
        if buffer:
            passages.append(Passage(len(passages), page_number, " ".join(buffer)))
    return passages


class ManualIndex:
    """Índice BM25 en memoria de un manual; se reconstruye solo si cambia el texto."""

    k1 = 1.5
    b = 0.75

    def __init__(self) -> None:
        self._digest = ""
        self.passages: list[Passage] = []
        self._tf: list[Counter] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0

    def build(self, text: str) -> None:
        digest = hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()
        if digest == self._digest:
            return
        self._digest = digest
        self.passages = split_passages(text)
        self._tf = [Counter(tokenize(p.text)) for p in self.passages]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        lengths = [sum(tf.values()) for tf in self._tf]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0

    def search(self, query: str, k: int = 2) -> list[tuple[Passage, float]]:
        """Pasajes más relevantes con score normalizado 0..1 (vacío si nada coincide)."""
        terms = set(tokenize(query))
        if not terms or not self.passages:
            return []
        n = len(self.passages)
        scored = []
        for passage, tf in zip(self.passages, self._tf):
            length = sum(tf.values()) or 1
            score = 0.0
            for term in terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                score += idf * freq * (self.k1 + 1) / (
                    freq + self.k1 * (1 - self.b + self.b * length / (self._avg_len or 1))
                )
            if score > 0:
                scored.append((passage, score))
        scored.sort(key=lambda item: (-item[1], item[0].index))
        top = scored[:k]
        best = top[0][1] if top else 1.0
        return [(p, round(s / best, 4)) for p, s in top]
