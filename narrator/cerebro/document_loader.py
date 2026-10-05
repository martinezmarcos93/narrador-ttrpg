"""Document ingestion primitives for the persistent brain.

PDF extraction and chunking are deterministic and do not call the LLM. The
output is Markdown neurons with explicit provenance metadata; embeddings are a
separate local step.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import fitz
import yaml


@dataclass(frozen=True)
class DocumentChunk:
    doc_id: str
    title: str
    source_path: str
    system: str
    campaign: str
    kind: str
    layer: str
    chunk_index: int
    text: str
    content_hash: str


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    return value.strip("-_") or "document"


def extract_pdf_pages(path: str | Path) -> list[str]:
    source = Path(path)
    with fitz.open(source) as document:
        return [page.get_text("text") for page in document]


def chunk_text(text: str, *, max_chars: int = 5000) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def load_pdf(
    path: str | Path,
    *,
    system: str = "generic",
    campaign: str = "",
    kind: str = "manual",
    layer: str = "manual",
    max_chars: int = 5000,
) -> list[DocumentChunk]:
    source = Path(path)
    pages = extract_pdf_pages(source)
    text = "\n\n".join(page for page in pages if page.strip())
    doc_id = _slug(source.stem)
    title = source.stem
    return [
        DocumentChunk(
            doc_id=doc_id,
            title=title,
            source_path=str(source.resolve()),
            system=system,
            campaign=campaign,
            kind=kind,
            layer=layer,
            chunk_index=index,
            text=chunk,
            content_hash=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
        )
        for index, chunk in enumerate(chunk_text(text, max_chars=max_chars))
    ]


def write_chunks(chunks: list[DocumentChunk], output_dir: str | Path) -> list[Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for chunk in chunks:
        filename = f"{_slug(chunk.doc_id)}-{chunk.chunk_index:04d}.md"
        path = destination / filename
        metadata = {
            "id": f"{chunk.doc_id}#{chunk.chunk_index}",
            "title": chunk.title,
            "source": chunk.source_path,
            "system": chunk.system,
            "campaign": chunk.campaign,
            "kind": chunk.kind,
            "layer": chunk.layer,
            "chunk_index": chunk.chunk_index,
            "content_hash": chunk.content_hash,
        }
        path.write_text(
            "---\n"
            + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
            + "---\n\n"
            + chunk.text.strip()
            + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
