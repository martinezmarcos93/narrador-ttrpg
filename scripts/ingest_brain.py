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
    parser.add_argument("--system", default="generic")
    parser.add_argument("--campaign", default="")
    parser.add_argument("--kind", default="manual")
    parser.add_argument("--layer", default="manual")
    parser.add_argument("--max-chars", type=int, default=5000)
    args = parser.parse_args()

    total = 0
    for source in args.pdf:
        chunks = load_pdf(
            source,
            system=args.system,
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
