"""Barredor del cerebro: PDF sintético → árbol de secciones → neuronas."""

import re

import pymupdf
import pytest
import yaml

from narrator.cerebro import barredor, extractor_pdf
from narrator.cerebro.barredor import Nodo
from narrator.cerebro.extractor_pdf import Linea
from narrator.cerebro.neurona import nombre_seguro, slug

FUENTE = {"id": "manual", "sistema": "juego", "titulo": "Manual de Prueba",
          "archivo": "manual.pdf", "idioma": "es"}


def _linea(texto, pagina=1, y=0.0, x0=50.0, bloque=0, tam=10.0, titulo=False):
    return Linea(pagina=pagina, texto=texto, tam=tam, negrita=False,
                 x0=x0, x1=x0 + 200, y0=y, y1=y + tam, bloque=bloque, es_titulo=titulo)


@pytest.fixture
def manual_pdf(tmp_path):
    """Dos páginas a dos columnas, con encabezado repetido e índice."""
    doc = pymupdf.open()
    for n in range(1, 7):
        page = doc.new_page(width=600, height=800)
        page.insert_text((50, 40), f"MANUAL DE PRUEBA {n}", fontsize=10)
        if n == 1:
            page.insert_text((50, 120), "Disciplinas", fontsize=20)
            page.insert_textbox((50, 140, 280, 400), "Texto de la columna izquierda. " * 12, fontsize=10)
            page.insert_text((320, 120), "Dominación", fontsize=14)
            page.insert_textbox((320, 140, 550, 400), "Texto de la columna derecha. " * 12, fontsize=10)
        else:
            if n == 2:
                page.insert_text((50, 110), "Apéndice", fontsize=20)
            page.insert_textbox((50, 120, 550, 400), f"Relleno de la página {n}. " * 20, fontsize=10)
    doc.set_toc([[1, "Disciplinas", 1], [2, "Dominación", 1], [1, "Apéndice", 2]])
    ruta = tmp_path / "manual.pdf"
    doc.save(ruta)
    doc.close()
    return ruta


def test_extraer_ordena_columnas_y_quita_encabezados(manual_pdf):
    datos = extractor_pdf.extraer(str(manual_pdf))
    textos = [ln.texto for ln in datos["lineas"]]
    assert not any("MANUAL DE PRUEBA" in t for t in textos)
    pagina1 = [ln.texto for ln in datos["lineas"] if ln.pagina == 1]
    # Toda la columna izquierda antes que el título de la derecha.
    assert max(i for i, t in enumerate(pagina1) if "izquierda" in t) < pagina1.index("Dominación")
    assert [ln.texto for ln in datos["lineas"] if ln.es_titulo] == [
        "Disciplinas", "Dominación", "Apéndice"]


def test_barrer_fuente_arma_jerarquia_desde_el_indice(manual_pdf):
    neuronas, resumen = barredor.barrer_fuente(FUENTE, manual_pdf.parent, excluir=set())
    por_titulo = {n.titulo: n for n in neuronas}
    assert resumen["paginas"] == 6
    disciplinas, dominacion = por_titulo["Disciplinas"], por_titulo["Dominación"]
    assert "izquierda" in disciplinas.texto and "derecha" not in disciplinas.texto
    assert "derecha" in dominacion.texto
    assert (dominacion.id, "Dominación") in disciplinas.contiene
    assert dominacion.migas[-1] == (disciplinas.id, "Disciplinas")
    assert dominacion.id.startswith("sistemas/juego/manual/disciplinas/")


def test_escribir_genera_markdown_con_frontmatter(manual_pdf, tmp_path):
    neuronas, _ = barredor.barrer_fuente(FUENTE, manual_pdf.parent, excluir=set())
    salida = tmp_path / "cerebro"
    barredor.escribir(neuronas, FUENTE, salida)
    archivo = salida / "sistemas/juego/manual/disciplinas/Dominación.md"
    _, frontmatter, cuerpo = archivo.read_text(encoding="utf-8").split("---\n", 2)
    meta = yaml.safe_load(frontmatter)
    assert meta["sistema"] == "juego" and meta["tipo"] == "seccion" and meta["paginas"] == "1"
    assert cuerpo.lstrip().startswith("# Dominación")


def test_toc_en_orden_descarta_marcadores_que_saltan():
    toc = [(1, "A", 1), (2, "B", 3), (2, "Salto al apéndice", 400), (2, "C", 4), (1, "D", 9)]
    assert [t for _, t, _ in barredor._toc_en_orden(toc)] == ["A", "B", "C", "D"]


def test_ubicar_toc_entrada_sin_texto_no_tapa_las_siguientes():
    lineas = [_linea("texto previo"), _linea("Brujah", y=20, titulo=True, tam=14),
              _linea("más texto", y=40)]
    marcas, virtuales = barredor.ubicar_toc(lineas, [(1, "Título gráfico", 1), (2, "Brujah", 1)])
    assert marcas == {1: (2, "Brujah")}
    assert virtuales == {0: [(1, "Título gráfico", 1)]}


def test_construir_arbol_lee_puntos_de_poderes():
    lineas = [_linea("••• Marchitar", titulo=True, tam=14), _linea("El poder marchita.", y=20)]
    raiz = barredor.construir_arbol(lineas, [(1, "3 - Marchitar", 1)], "Libro", False)
    poder = raiz.hijos[0]
    assert (poder.titulo, poder.puntos) == ("Marchitar", 3)


def test_armar_parrafos_une_cortes_de_palabra_y_separa_vinetas():
    lineas = [
        _linea("El vampiro puede domi­"),
        _linea("nar a su víctima.", y=12),
        _linea("• Primera opción", y=24),
        _linea("• Segunda opción", y=36),
    ]
    textos = [t for t, _ in barredor.armar_parrafos(lineas)]
    assert textos == ["El vampiro puede dominar a su víctima.", "• Primera opción", "• Segunda opción"]


def test_armar_parrafos_continua_entre_columnas_si_la_oracion_no_termino():
    lineas = [_linea("la oración sigue en la otra", bloque=0),
              _linea("columna y termina acá.", bloque=1, x0=320, y=0)]
    assert [t for t, _ in barredor.armar_parrafos(lineas)] == [
        "la oración sigue en la otra columna y termina acá."]


def test_separar_entradas_abre_una_neurona_por_don():
    nodo = Nodo(titulo="Dones Lupus", nivel=2, pagina=1, parrafos=[
        ("Introducción a los dones.", 1),
        ("• Sense Prey (Level One) — Ubica presas.", 1), ("System: tirada.", 1),
        ("• Heightened Senses (Level One) — Agudiza.", 2),
    ])
    barredor.separar_entradas(nodo, re.compile(r"^•\s*(.+?)\s*\(Level \w+\)\s*—"))
    assert nodo.parrafos == [("Introducción a los dones.", 1)]
    assert [(h.titulo, h.tipo, len(h.parrafos)) for h in nodo.hijos] == [
        ("Sense Prey", "entrada", 2), ("Heightened Senses", "entrada", 1)]


def test_partir_respeta_parrafos_y_funde_la_cola_corta():
    parrafos = [("palabra " * 200, 1), ("palabra " * 200, 2), ("cola corta", 3)]
    tramos = barredor.partir(parrafos, max_palabras=350)
    assert [len(t) for t in tramos] == [1, 2]


def test_asignar_ids_desambigua_titulos_repetidos_sin_distinguir_mayusculas():
    raiz = Nodo(titulo="Libro", nivel=0, pagina=1, tipo="libro")
    cap = Nodo(titulo="Capítulo", nivel=1, pagina=1, padre=raiz)
    a = Nodo(titulo="Sistema", nivel=2, pagina=1, padre=cap, parrafos=[("uno " * 10, 1)])
    b = Nodo(titulo="SISTEMA", nivel=2, pagina=2, padre=cap, parrafos=[("dos " * 10, 2)])
    raiz.hijos, cap.hijos = [cap], [a, b]
    barredor.asignar_ids(raiz, "sistemas/juego/libro")
    assert a.ids[0].lower() != b.ids[0].lower()


def test_enlazar_menciones_exige_mayuscula_en_mitad_de_oracion():
    def neurona(titulo, texto):
        return barredor.Neurona(id=f"s/{titulo}", titulo=titulo, texto=texto,
                                meta={"tipo": "seccion"})
    rabia = neurona("Rabia", "Reglas de la furia.")
    fuerza = neurona("Fuerza", "Atributo físico.")
    voluntad = neurona("Fuerza de Voluntad", "Reserva mental.")
    don = neurona("Don", "El jugador gasta Rabia y tira Fuerza de Voluntad. Rabia aparte.")
    comun = neurona("Otra", "Rabia al inicio de oración no cuenta.")
    barredor.enlazar_menciones([rabia, fuerza, voluntad, don, comun], set())
    assert [t for _, t in don.ver_tambien] == ["Rabia", "Fuerza de Voluntad"]
    assert comun.ver_tambien == []


def test_nombres_de_archivo_y_carpeta():
    assert nombre_seguro('¿Qué es un "Vampiro"?: guía') == "¿Qué es un Vampiro guía"
    assert slug("Capítulo Cuatro: Disciplinas") == "capitulo-cuatro-disciplinas"
