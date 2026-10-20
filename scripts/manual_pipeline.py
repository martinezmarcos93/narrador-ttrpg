#!/usr/bin/env python3
"""Pipeline completo de un manual PDF hacia el cerebro (B3).

    identificar sistema/edición → barrer (si está en el catálogo) o ingerir por
    chunks → indexar embeddings (incremental) → auditar neuronas generadas

Uso:
    python scripts/manual_pipeline.py "/ruta/al/manual.pdf"
    python scripts/manual_pipeline.py manual.pdf --dry-run      # solo muestra el plan

Ver docs/PIPELINE-MANUALES.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class PipelinePlan:
    pdf: str
    system: str
    edition: str
    confidence: float
    warning: str
    route: str            # "barredor" | "ingesta"
    fuente_id: str        # id del catálogo si route == "barredor"
    output: str


def plan_pipeline(pdf: Path, identity: dict, catalog: dict, library: Path | None) -> PipelinePlan:
    """Decide la ruta sin efectos: barredor si el PDF está catalogado, ingesta si no."""
    fuente_id = ""
    for fuente in catalog.get("fuentes", []) or []:
        archivo = Path(str(fuente.get("archivo", "")))
        candidates = {archivo.name}
        if library:
            candidates.add(str((library / archivo).resolve()))
        if pdf.name in candidates or str(pdf.resolve()) in candidates:
            fuente_id = str(fuente.get("id"))
            break
    if fuente_id:
        route, output = "barredor", f"cerebro/sistemas/{identity['slug']}/{fuente_id}"
    else:
        route, output = "ingesta", f"cerebro/importados/{identity['slug']}"
    return PipelinePlan(
        pdf=str(pdf), system=identity["slug"], edition=identity.get("edition", ""),
        confidence=float(identity.get("confidence", 0.0)), warning=identity.get("warning", ""),
        route=route, fuente_id=fuente_id, output=output,
    )


def main() -> int:
    import pymupdf
    import yaml

    from narrator.cerebro.auditor import audit_brain
    from narrator.cerebro.indexador import IndiceCerebro
    from narrator.core.system_detection import identify_manual

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default="nomic-embed-text")
    args = parser.parse_args()

    with pymupdf.open(args.pdf) as doc:
        sample = "\n".join(page.get_text() for page in list(doc)[:30])
    identity = identify_manual(sample, ROOT / "data" / "systems").to_dict()
    catalog = yaml.safe_load((ROOT / "data/cerebro/fuentes.yaml").read_text(encoding="utf-8")) or {}
    local_cfg = ROOT / "config" / "local.yaml"
    library = None
    if local_cfg.exists():
        lib = (yaml.safe_load(local_cfg.read_text(encoding="utf-8")) or {}).get("cerebro", {}).get("biblioteca")
        library = Path(lib) if lib else None
    plan = plan_pipeline(args.pdf, identity, catalog, library)
    print(json.dumps(asdict(plan), ensure_ascii=False, indent=2))
    if plan.warning:
        print(f"aviso: {plan.warning}", file=sys.stderr)
    if args.dry_run:
        return 0

    if plan.route == "barredor":
        from narrator.cerebro.barredor import main as barrer

        if barrer(["--fuente", plan.fuente_id]) != 0:
            return 1
    else:
        from narrator.cerebro.document_loader import load_pdf, write_chunks

        chunks = load_pdf(args.pdf, system=plan.system, kind="manual", layer="manual")
        write_chunks(chunks, ROOT / plan.output)

    IndiceCerebro(ROOT / "cerebro", embedding_model=args.model).build(on_progress=print)
    profile = "sistema" if plan.route == "barredor" else "universal"
    if profile == "sistema":
        report = audit_brain(ROOT / "cerebro" / "sistemas", profile="sistema")
        print(json.dumps({k: len(v) if isinstance(v, list) else v
                          for k, v in report.to_dict().items() if k != "covered_concepts"},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
