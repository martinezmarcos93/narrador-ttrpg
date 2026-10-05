"""
Extractor de PDF — convierte un manual en una secuencia de líneas en orden
de lectura, con la tipografía de cada una (para detectar títulos).

Resuelve lo que rompe una extracción ingenua de un manual de rol:
- páginas a dos columnas (ordena por columna, no por orden interno del PDF);
- encabezados y pies repetidos ("CAPÍTULO CUATRO: DISCIPLINAS 222");
- capitulares (la letra gigante que abre un capítulo);
- títulos partidos en varias líneas.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

from narrator.logger import logger

# Una línea es título si su letra supera a la del cuerpo en esta proporción.
RATIO_TITULO = 1.18
LARGO_MAX_TITULO = 100
# Franja superior/inferior de la página donde viven encabezados y pies.
MARGEN_CABECERA = 0.10


@dataclass
class Linea:
    pagina: int          # 1 = primera página del PDF
    texto: str
    tam: float
    negrita: bool
    x0: float
    x1: float
    y0: float
    y1: float
    bloque: int          # índice del bloque dentro de la página, ya en orden de lectura
    es_titulo: bool = False


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y solo alfanuméricos — para comparar títulos."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def _ordenar_bloques(bloques: list, ancho: float) -> list:
    """Orden de lectura a dos columnas: los bloques que cruzan el centro de la
    página (títulos de capítulo, tablas anchas) parten la página en bandas;
    dentro de cada banda va primero la columna izquierda y después la derecha."""
    medio = ancho / 2
    holgura = ancho * 0.08
    claves = []
    banda = 0
    for b in sorted(bloques, key=lambda b: (b["bbox"][1], b["bbox"][0])):
        x0, y0, x1, _ = b["bbox"]
        if x0 < medio - holgura and x1 > medio + holgura:
            banda += 1
            claves.append(((banda, 0, y0), b))
            banda += 1
        else:
            columna = 0 if (x0 + x1) / 2 < medio else 1
            claves.append(((banda, columna, y0), b))
    return [b for _, b in sorted(claves, key=lambda par: par[0])]


def _linea_de(linea_pdf: dict, pagina: int, bloque: int) -> "Linea | None":
    # Texto rotado (lomos, marcas de agua): no es contenido.
    dx, dy = linea_pdf.get("dir", (1, 0))
    if abs(dx - 1) > 0.01 or abs(dy) > 0.01:
        return None
    spans = [s for s in linea_pdf["spans"] if s["text"].strip()]
    if not spans:
        return None
    texto = "".join(s["text"] for s in linea_pdf["spans"]).strip()
    principal = max(spans, key=lambda s: len(s["text"]))
    letras_negrita = sum(
        len(s["text"]) for s in spans if s["flags"] & 16 or "bold" in s["font"].lower()
    )
    x0, y0, x1, y1 = linea_pdf["bbox"]
    return Linea(
        pagina=pagina, texto=texto, tam=principal["size"],
        negrita=letras_negrita > len(texto) / 2,
        x0=x0, x1=x1, y0=y0, y1=y1, bloque=bloque,
    )


def _tam_cuerpo(lineas: list) -> float:
    """Tamaño de letra dominante del libro (ponderado por cantidad de texto)."""
    pesos = Counter()
    for ln in lineas:
        pesos[round(ln.tam * 2) / 2] += len(ln.texto)
    return pesos.most_common(1)[0][0] if pesos else 10.0


def _quitar_cabeceras(lineas: list, altos: dict, n_paginas: int) -> list:
    """Descarta números de página y encabezados/pies que se repiten."""
    def en_margen(ln):
        alto = altos[ln.pagina]
        return ln.y1 < alto * MARGEN_CABECERA or ln.y0 > alto * (1 - MARGEN_CABECERA)

    def clave(ln):
        return re.sub(r"\d+", "", normalizar(ln.texto))

    paginas_por_clave: dict = {}
    for ln in lineas:
        if en_margen(ln):
            paginas_por_clave.setdefault(clave(ln), set()).add(ln.pagina)
    minimo = max(4, n_paginas // 40)

    limpias = []
    for ln in lineas:
        if en_margen(ln):
            k = clave(ln)
            if not k or len(paginas_por_clave[k]) >= minimo:
                continue
        limpias.append(ln)
    return limpias


def _unir_capitulares(lineas: list, cuerpo: float) -> list:
    """La capitular llega como una línea de 1-2 letras gigantes: se pega a la
    línea siguiente en vez de tomarla por título."""
    salida = []
    pendiente = ""
    for ln in lineas:
        if len(ln.texto) <= 2 and ln.tam >= cuerpo * RATIO_TITULO and ln.texto.isalpha():
            pendiente += ln.texto
            continue
        if pendiente:
            ln.texto = pendiente + ln.texto
            pendiente = ""
        salida.append(ln)
    return salida


def _marcar_titulos(lineas: list, cuerpo: float) -> list:
    """Marca como título las líneas de letra grande y funde las consecutivas
    (un título partido en dos renglones es un solo título)."""
    salida = []
    for ln in lineas:
        grande = ln.tam >= cuerpo * RATIO_TITULO
        letras = sum(c.isalpha() for c in ln.texto)
        ln.es_titulo = grande and letras >= 3 and len(ln.texto) <= LARGO_MAX_TITULO
        previa = salida[-1] if salida else None
        if (
            ln.es_titulo and previa is not None and previa.es_titulo
            and previa.pagina == ln.pagina
            and abs(previa.tam - ln.tam) < 0.4
            and 0 <= ln.y0 - previa.y1 < ln.tam
            and len(previa.texto) + len(ln.texto) < LARGO_MAX_TITULO
        ):
            previa.texto = f"{previa.texto} {ln.texto}"
            previa.y1 = ln.y1
            previa.x1 = max(previa.x1, ln.x1)
            continue
        salida.append(ln)
    return salida


def extraer(ruta: str) -> dict:
    """Lee el PDF y devuelve
    {"lineas": [Linea], "toc": [(nivel, título, página)], "paginas": int, "cuerpo": float}.
    """
    pymupdf.TOOLS.mupdf_display_errors(False)
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    lineas: list = []
    altos: dict = {}
    with pymupdf.open(ruta) as doc:
        n_paginas = len(doc)
        toc = [(nivel, titulo.strip(), pagina) for nivel, titulo, pagina in doc.get_toc()]
        for i, page in enumerate(doc, start=1):
            altos[i] = page.rect.height
            try:
                bloques = [b for b in page.get_text("dict", flags=flags)["blocks"]
                           if b.get("type") == 0]
            except Exception as e:
                logger.error(f"Barredor: página {i} ilegible en {ruta}: {e}", exc_info=True)
                continue
            for n_bloque, bloque in enumerate(_ordenar_bloques(bloques, page.rect.width)):
                for linea_pdf in bloque.get("lines", []):
                    ln = _linea_de(linea_pdf, i, n_bloque)
                    if ln is not None:
                        lineas.append(ln)

    cuerpo = _tam_cuerpo(lineas)
    lineas = _quitar_cabeceras(lineas, altos, n_paginas)
    lineas = _unir_capitulares(lineas, cuerpo)
    lineas = _marcar_titulos(lineas, cuerpo)
    return {"lineas": lineas, "toc": toc, "paginas": n_paginas, "cuerpo": cuerpo}
