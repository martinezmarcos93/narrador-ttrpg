import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("manual_pipeline", ROOT / "scripts" / "manual_pipeline.py")
manual_pipeline = importlib.util.module_from_spec(spec)
sys.modules["manual_pipeline"] = manual_pipeline
spec.loader.exec_module(manual_pipeline)

IDENTITY = {"slug": "vtm_v20", "edition": "V20", "confidence": 0.97, "warning": ""}
CATALOG = {"fuentes": [{"id": "v20-basico", "sistema": "vtm_v20",
                        "archivo": "White Wolf/Vampiro 20 aniversario.pdf"}]}


def test_catalogued_pdf_goes_through_barredor():
    plan = manual_pipeline.plan_pipeline(Path("/x/Vampiro 20 aniversario.pdf"), IDENTITY, CATALOG, None)
    assert plan.route == "barredor"
    assert plan.fuente_id == "v20-basico"
    assert plan.output == "cerebro/sistemas/vtm_v20/v20-basico"


def test_unknown_pdf_goes_through_chunk_ingestion():
    plan = manual_pipeline.plan_pipeline(Path("/x/suplemento.pdf"), IDENTITY, CATALOG, None)
    assert plan.route == "ingesta"
    assert plan.output == "cerebro/importados/vtm_v20"
