"""Test Fase 17: extracción de fichas PDF vía campos de formulario
(AcroForm) con PyMuPDF — vía alternativa a texto+LLM."""

import pymupdf as fitz

from narrator.core.sheet_parser import extract_form_fields, map_form_fields


def _pdf_con_campos(tmp_path, campos: dict) -> str:
    """Crea un PDF sintético con campos de formulario para testear —
    no usa datos reales de ningún sistema, solo valida el mecanismo."""
    doc = fitz.open()
    page = doc.new_page()
    y = 10
    for name, value in campos.items():
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(10, y, 200, y + 20)
        w.field_value = value
        page.add_widget(w)
        y += 25
    path = tmp_path / "ficha.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def test_extract_form_fields_pdf_con_campos(tmp_path):
    path = _pdf_con_campos(tmp_path, {"Nombre": "Kael", "Str-1": "3"})
    fields = extract_form_fields(path)
    assert fields == {"Nombre": "Kael", "Str-1": "3"}


def test_extract_form_fields_pdf_sin_campos(tmp_path):
    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "sin_campos.pdf"
    doc.save(str(path))
    doc.close()
    assert extract_form_fields(str(path)) == {}


def test_extract_form_fields_pdf_inexistente_no_rompe(tmp_path):
    assert extract_form_fields(str(tmp_path / "no_existe.pdf")) == {}


def test_map_form_fields_renombra_segun_mapeo():
    fields = {"Nombre": "Kael", "Str-1": "3", "SinMapeo": "x"}
    field_map = {"Nombre": "nombre", "Str-1": "fuerza"}
    resultado = map_form_fields(fields, field_map)
    assert resultado == {"nombre": "Kael", "fuerza": "3"}


def test_map_form_fields_descarta_valores_vacios():
    fields = {"Nombre": "", "Str-1": "3"}
    field_map = {"Nombre": "nombre", "Str-1": "fuerza"}
    assert map_form_fields(fields, field_map) == {"fuerza": "3"}
