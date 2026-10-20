#!/usr/bin/env python3
"""Ingest PDFs into brain Markdown neurons.

This script intentionally stops before embedding. Run it locally, inspect the
generated provenance/metadata, then run the brain indexer against the result.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from narrator.cerebro.document_loader import load_pdf, write_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest PDF documents into the AI Narrator brain.")
    parser.add_argument("pdf", nargs="+", type=Path)
    parser.add_argument("--output", default="cerebro/importados")
    parser.add_argument(
        "--system", default="auto",
        help="slug del System Pack o 'auto' para detectarlo desde el texto del PDF",
    )
    parser.add_argument("--campaign", default="")
    parser.add_argument("--kind", default="manual")
    parser.add_argument("--layer", default="manual")
    parser.add_argument("--max-chars", type=int, default=5000)
    args = parser.parse_args()

    total = 0
    for source in args.pdf:
        system = args.system
        if system == "auto":
            import pymupdf

            from narrator.core.system_detection import identify_manual

            with pymupdf.open(source) as doc:
                sample = "\n".join(page.get_text() for page in list(doc)[:30])
            identity = identify_manual(sample, "data/systems")
            system = identity.slug
            print(f"{source}: sistema {identity.nombre} (confianza {identity.confidence:.0%})"
                  + (f", edición {identity.edition}" if identity.edition else ""))
            if identity.warning:
                print(f"  aviso: {identity.warning}")
        chunks = load_pdf(
            source,
            system=system,
            campaign=args.campaign,
            kind=args.kind,
            layer=args.layer,
            max_chars=args.max_chars,
        )
        paths = write_chunks(chunks, args.output)
        total += len(paths)
        print(f"{source}: {len(paths)} chunks -> {args.output}")
    print(f"Total chunks: {total}")
    print("Next local step: inspect metadata, then build the brain index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
