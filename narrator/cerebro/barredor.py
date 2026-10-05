"""
Barredor — recorre los manuales declarados en `data/cerebro/fuentes.yaml`
y los convierte en neuronas del cerebro. Es determinístico: no usa el LLM.

Una neurona = una sección del manual. La estructura sale del índice del PDF
(marcadores) y, donde el índice no alcanza, de los títulos detectados por
tamaño de letra. Las secciones largas se parten en tramos encadenados.

Uso:
    python -m narrator.cerebro.barredor --listar
    python -m narrator.cerebro.barredor --sistema vtm_v20
    python -m narrator.cerebro.barredor --fuente v20-basico
    python -m narrator.cerebro.barredor --todo
"""

import argparse
import bisect
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from narrator import PROJECT_ROOT, resolve_path
from narrator.cerebro import extractor_pdf
from narrator.cerebro.extractor_pdf import LARGO_MAX_TITULO, normalizar
from narrator.cerebro.neurona import Neurona, nombre_seguro, slug
from narrator.logger import logger

FUENTES_PATH = PROJECT_ROOT / "data" / "cerebro" / "fuentes.yaml"
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
CONFIG_LOCAL_PATH = PROJECT_ROOT / "config" / "local.yaml"

# Un tramo de neurona apunta a este tamaño: entra holgado en el prompt de un
# modelo chico y es lo bastante corto para que el embedding sea preciso.
MAX_PALABRAS = 350
MIN_PALABRAS_COLA = 60      # un último tramo más corto se funde con el anterior
MIN_PALABRAS_NODO = 8       # una sección hoja con menos texto es ruido
MAX_VER_TAMBIEN = 8
# Con un índice así de denso el PDF ya declara todas sus secciones: los
# títulos sueltos por tamaño de letra serían citas y rótulos de tablas.
DENSIDAD_TOC_COMPLETO = 1.0

_FIN_ORACION = tuple('.!?:…”"»)')
_VINETAS = ("•", "●", "▪", "■", "–", "—")
_GUION_BLANDO = "­"


@dataclass
class Nodo:
    titulo: str
    nivel: int
    pagina: int
    padre: "Nodo | None" = None
    lineas: list = field(default_factory=list)
    hijos: list = field(default_factory=list)
    parrafos: list = field(default_factory=list)   # [(texto, página)]
    puntos: int = 0                                # "••• Título" → 3
    tipo: str = "seccion"
    tramos: list = field(default_factory=list)     # párrafos agrupados por tramo
    ids: list = field(default_factory=list)        # un id por tramo


# ── Estructura: del PDF al árbol de secciones ─────────────────────────

def _coincide(titulo_norm: str, linea_norm: str) -> bool:
    if not titulo_norm or not linea_norm:
        return False
    if titulo_norm == linea_norm:
        return True
    corto, largo = sorted((titulo_norm, linea_norm), key=len)
    return (
        len(corto) >= 4
        and len(corto) / len(largo) >= 0.6
        and (largo.startswith(corto) or largo.endswith(corto))
    )


def _toc_en_orden(toc: list) -> list:
    """Se queda con la mayor secuencia de entradas del índice cuyas páginas
    no retroceden. Descarta los marcadores sueltos que saltan por el libro
    (accesos directos a la ficha, listas de clanes al final): romperían el
    recorrido secuencial."""
    colas: list = []      # colas[k] = índice de la entrada que cierra la mejor secuencia de largo k+1
    paginas_cola: list = []
    previo = [-1] * len(toc)
    for i, (_, _, pagina) in enumerate(toc):
        k = bisect.bisect_right(paginas_cola, pagina)
        previo[i] = colas[k - 1] if k else -1
        if k == len(colas):
            colas.append(i)
            paginas_cola.append(pagina)
        else:
            colas[k] = i
            paginas_cola[k] = pagina
    elegidos = []
    i = colas[-1] if colas else -1
    while i != -1:
        elegidos.append(toc[i])
        i = previo[i]
    return elegidos[::-1]


def ubicar_toc(lineas: list, toc: list) -> "tuple[dict, dict]":
    """Ubica cada entrada del índice en la línea del texto donde aparece.

    Devuelve (marcas, virtuales): `marcas[i] = (nivel, título)` para las
    entradas encontradas en la línea i; `virtuales[i] = [(nivel, título,
    página)]` para las que no aparecen como texto (se abren antes de la
    línea i, al comienzo de su página)."""
    paginas = [ln.pagina for ln in lineas]
    normas = [normalizar(ln.texto) for ln in lineas]
    marcas: dict = {}
    virtuales: dict = {}
    cursor = 0
    for nivel, titulo, pagina in _toc_en_orden(toc):
        objetivo = normalizar(titulo)
        if pagina < 1 or not objetivo:
            continue
        hallado = None
        # Primero entre las líneas con letra de título (página exacta y
        # vecinas, por índices corridos); después cualquier línea de la página.
        for pag, solo_titulos in ((pagina, True), (pagina + 1, True),
                                  (pagina - 1, True), (pagina, False)):
            desde = max(cursor, bisect.bisect_left(paginas, pag))
            hasta = bisect.bisect_right(paginas, pag)
            for i in range(desde, hasta):
                if i in marcas or (solo_titulos and not lineas[i].es_titulo):
                    continue
                if len(lineas[i].texto) <= LARGO_MAX_TITULO and _coincide(objetivo, normas[i]):
                    hallado = i
                    break
            if hallado is not None:
                break
        if hallado is not None:
            marcas[hallado] = (nivel, titulo)
            cursor = hallado + 1
        else:
            # El cursor solo avanza con títulos hallados de verdad: una
            # entrada sin texto no debe tapar a las que vienen después.
            pos = max(cursor, bisect.bisect_left(paginas, pagina))
            virtuales.setdefault(pos, []).append((nivel, titulo, pagina))
    return marcas, virtuales


def construir_arbol(lineas: list, toc: list, titulo_raiz: str,
                    titulos_por_letra: bool) -> Nodo:
    marcas, virtuales = ubicar_toc(lineas, toc)
    tamanos = sorted(
        {round(ln.tam) for i, ln in enumerate(lineas) if ln.es_titulo and i not in marcas},
        reverse=True,
    )
    raiz = Nodo(titulo=titulo_raiz, nivel=0, pagina=1, tipo="libro")
    pila = [raiz]
    nivel_toc = 0

    def abrir(titulo: str, nivel: int, pagina: int):
        while pila[-1].nivel >= nivel:
            pila.pop()
        # Nivel de un poder: "••• Título" en el texto, "3 - Título" en el índice.
        puntos = 0
        if vinetas := re.match(r"^([•●]+)\s*(.+)$", titulo):
            puntos, titulo = len(vinetas.group(1)), vinetas.group(2)
        elif numerado := re.match(r"^(\d{1,2}) - (.+)$", titulo):
            puntos, titulo = int(numerado.group(1)), numerado.group(2)
        nodo = Nodo(titulo=titulo.strip(), nivel=nivel, pagina=pagina,
                    padre=pila[-1], puntos=puntos)
        pila[-1].hijos.append(nodo)
        pila.append(nodo)

    for i, ln in enumerate(lineas):
        for nivel, titulo, pagina in virtuales.get(i, []):
            abrir(titulo, nivel, pagina)
            nivel_toc = nivel
        if i in marcas:
            nivel, titulo = marcas[i]
            abrir(titulo, nivel, ln.pagina)
            nivel_toc = nivel
        elif titulos_por_letra and ln.es_titulo:
            rango = min(tamanos.index(round(ln.tam)), 3)
            abrir(ln.texto, nivel_toc + 1 + rango, ln.pagina)
        else:
            pila[-1].lineas.append(ln)
    for nivel, titulo, pagina in virtuales.get(len(lineas), []):
        abrir(titulo, nivel, pagina)
    return raiz


def recorrer(nodo: Nodo):
    yield nodo
    for hijo in nodo.hijos:
        yield from recorrer(hijo)


# ── Texto: de líneas sueltas a párrafos ───────────────────────────────

def _unir(acumulado: str, nuevo: str) -> str:
    if acumulado.endswith(_GUION_BLANDO):
        return acumulado[:-1] + nuevo
    if (acumulado.endswith("-") and len(acumulado) > 1 and acumulado[-2].isalpha()
            and nuevo[:1].islower()):
        return acumulado[:-1] + nuevo
    return f"{acumulado} {nuevo}"


def _limpiar(texto: str) -> str:
    texto = texto.replace(_GUION_BLANDO, "").replace("\t", " | ")
    return re.sub(r"\s+", " ", texto).strip()


def armar_parrafos(lineas: list) -> list:
    """Reconstruye los párrafos: une los cortes de renglón (y de palabra),
    separa por sangría, salto vertical, viñeta o fila de tabla.
    Devuelve [(texto, página)]."""
    borde_derecho: dict = {}
    for ln in lineas:
        clave = (ln.pagina, ln.bloque)
        borde_derecho[clave] = max(borde_derecho.get(clave, 0), ln.x1)

    parrafos: list = []
    acumulado, pagina, previa = "", 0, None

    def cerrar():
        texto = _limpiar(acumulado)
        if texto:
            parrafos.append((texto, pagina))

    for k, ln in enumerate(lineas):
        vecina_grande = (k > 0 and lineas[k - 1].es_titulo) or (
            k + 1 < len(lineas) and lineas[k + 1].es_titulo)
        # Título que no abrió sección (el índice del PDF manda): queda como
        # rótulo en negrita. Varias líneas grandes seguidas no son un rótulo
        # sino un pasaje en otra tipografía (cartas, citas): texto normal.
        if ln.es_titulo and not vecina_grande:
            cerrar()
            parrafos.append((f"**{_limpiar(ln.texto)}**", ln.pagina))
            acumulado, previa = "", None
            continue
        if previa is None:
            acumulado, pagina = ln.texto, ln.pagina
        else:
            fin = previa.texto.rstrip().endswith(_FIN_ORACION)
            if "\t" in ln.texto or "\t" in previa.texto:
                nuevo = True
            elif ln.texto.startswith(_VINETAS):
                nuevo = True
            elif (ln.pagina, ln.bloque) != (previa.pagina, previa.bloque):
                nuevo = fin
            elif ln.y0 - previa.y1 > previa.tam * 0.5:
                nuevo = True
            else:
                corta = previa.x1 < borde_derecho[(previa.pagina, previa.bloque)] - 20
                nuevo = fin and (ln.x0 - previa.x0 > 3 or corta)
            if nuevo:
                cerrar()
                acumulado, pagina = ln.texto, ln.pagina
            else:
                acumulado = _unir(acumulado, ln.texto)
        previa = ln
    cerrar()
    return parrafos


def separar_entradas(nodo: Nodo, patron: "re.Pattern") -> None:
    """Listas de entradas sin título tipográfico (Dones, hechizos, méritos):
    cada párrafo que calza con el patrón abre una neurona hija propia."""
    cortes = [(i, m) for i, (texto, _) in enumerate(nodo.parrafos)
              if (m := patron.match(texto))]
    if len(cortes) < 2:
        return
    entradas = []
    for n, (i, m) in enumerate(cortes):
        fin = cortes[n + 1][0] if n + 1 < len(cortes) else len(nodo.parrafos)
        entradas.append(Nodo(
            titulo=m.group(1).strip(), nivel=nodo.nivel + 1,
            pagina=nodo.parrafos[i][1], padre=nodo,
            parrafos=nodo.parrafos[i:fin], tipo="entrada",
        ))
    nodo.parrafos = nodo.parrafos[:cortes[0][0]]
    nodo.hijos = entradas + nodo.hijos


def _palabras(texto: str) -> int:
    return len(texto.split())


def partir(parrafos: list, max_palabras: int = MAX_PALABRAS) -> list:
    """Agrupa párrafos enteros en tramos de hasta ~max_palabras."""
    piezas = []
    for texto, pagina in parrafos:
        if _palabras(texto) <= max_palabras * 2:
            piezas.append((texto, pagina))
            continue
        # Párrafo descomunal (texto sin cortes detectables): por oraciones.
        acumulado: list = []
        for oracion in re.split(r"(?<=[.!?])\s+", texto):
            if acumulado and _palabras(" ".join(acumulado)) + _palabras(oracion) > max_palabras:
                piezas.append((" ".join(acumulado), pagina))
                acumulado = []
            acumulado.append(oracion)
        if acumulado:
            piezas.append((" ".join(acumulado), pagina))

    tramos, actual, cuenta = [], [], 0
    for texto, pagina in piezas:
        n = _palabras(texto)
        if actual and cuenta + n > max_palabras:
            tramos.append(actual)
            actual, cuenta = [], 0
        actual.append((texto, pagina))
        cuenta += n
    if actual:
        if tramos and cuenta < MIN_PALABRAS_COLA:
            tramos[-1].extend(actual)
        else:
            tramos.append(actual)
    return tramos


def _texto_de(tramo: list) -> str:
    """Une párrafos con línea en blanco; las filas de tabla van pegadas."""
    salida = ""
    previa_tabla = False
    for texto, _ in tramo:
        es_tabla = " | " in texto
        if salida:
            salida += "\n" if (es_tabla and previa_tabla) else "\n\n"
        salida += texto
        previa_tabla = es_tabla
    return salida


# ── Lectura de fuentes ────────────────────────────────────────────────

def leer_pdf(ruta: Path, fuente: dict) -> "tuple[Nodo, int]":
    datos = extractor_pdf.extraer(str(ruta))
    modo = fuente.get("titulos_por_letra", "auto")
    if modo == "auto":
        densidad = len(datos["toc"]) / max(datos["paginas"], 1)
        modo = densidad < DENSIDAD_TOC_COMPLETO
    raiz = construir_arbol(datos["lineas"], datos["toc"], fuente["titulo"], bool(modo))
    for nodo in recorrer(raiz):
        nodo.parrafos = armar_parrafos(nodo.lineas)
        nodo.lineas = []
    return raiz, datos["paginas"]


def leer_txt(ruta: Path, fuente: dict) -> "tuple[Nodo, int]":
    crudo = ruta.read_bytes()
    try:
        texto = crudo.decode("utf-8")
    except UnicodeDecodeError:
        # Notas viejas escritas en Windows.
        texto = crudo.decode("cp1252", errors="replace")
    raiz = Nodo(titulo=fuente["titulo"], nivel=0, pagina=1, tipo="libro")
    for bloque in re.split(r"\n\s*\n", texto.replace("\r\n", "\n")):
        limpio = re.sub(r"\s+", " ", bloque).strip()
        if limpio:
            raiz.parrafos.append((limpio, 1))
    return raiz, 1


# ── Del árbol a las neuronas ──────────────────────────────────────────

def podar(raiz: Nodo, excluir: set) -> None:
    """Saca las secciones excluidas (créditos, índices) y las hojas vacías."""
    def visitar(nodo: Nodo) -> bool:
        nodo.hijos = [h for h in nodo.hijos
                      if normalizar(h.titulo) not in excluir and visitar(h)]
        palabras = sum(_palabras(t) for t, _ in nodo.parrafos)
        return bool(nodo.hijos) or palabras >= MIN_PALABRAS_NODO
    visitar(raiz)


def carpeta_de(fuente: dict) -> str:
    if fuente.get("capa", "sistema") == "sistema":
        return f"sistemas/{fuente['sistema']}/{fuente['id']}"
    return f"{fuente['capa']}/{fuente['id']}"


def asignar_ids(raiz: Nodo, base: str) -> None:
    """Da a cada tramo de cada nodo su id (= ruta dentro del vault). Las dos
    primeras secciones de la cadena forman la carpeta; el resto, el nombre."""
    usados: set = set()   # en minúsculas: el vault vive en un disco NTFS

    def libre(candidato: str) -> bool:
        return candidato.lower() not in usados

    for nodo in recorrer(raiz):
        cadena = []
        actual = nodo.padre
        while actual is not None and actual.nivel > 0:
            cadena.append(actual)
            actual = actual.padre
        cadena.reverse()
        carpeta = "/".join([base] + [slug(a.titulo) for a in cadena[:2]])
        nombre = nombre_seguro(nodo.titulo)
        if not libre(f"{carpeta}/{nombre}") and nodo.padre is not None and nodo.padre.nivel > 0:
            nombre = nombre_seguro(f"{nodo.titulo} — {nodo.padre.titulo}")
        n = 2
        unico = nombre
        while not libre(f"{carpeta}/{unico}"):
            unico = f"{nombre} [{n}]"
            n += 1
        usados.add(f"{carpeta}/{unico}".lower())

        tramos = partir(nodo.parrafos) or [[]]
        nodo.tramos = tramos
        if len(tramos) == 1:
            nodo.ids = [f"{carpeta}/{unico}"]
        else:
            nodo.ids = [f"{carpeta}/{unico}"] + [
                f"{carpeta}/{unico} ({k} de {len(tramos)})" for k in range(2, len(tramos) + 1)
            ]
            usados.update(i.lower() for i in nodo.ids)


def neuronas_de(raiz: Nodo, fuente: dict) -> list:
    capa = fuente.get("capa", "sistema")
    tags = [f"capa/{capa}", f"fuente/{fuente['id']}"]
    if fuente.get("sistema"):
        tags.insert(1, f"sistema/{fuente['sistema']}")

    neuronas = []
    for nodo in recorrer(raiz):
        migas = []
        actual = nodo.padre
        while actual is not None:
            migas.append((actual.ids[0], actual.titulo))
            actual = actual.padre
        migas.reverse()
        total = len(nodo.tramos)
        for k, tramo in enumerate(nodo.tramos):
            texto = _texto_de(tramo)
            paginas = [p for _, p in tramo] or [nodo.pagina]
            meta = {
                "tipo": nodo.tipo,
                "capa": capa,
                "sistema": fuente.get("sistema", ""),
                "fuente": fuente["id"],
                "libro": fuente["titulo"],
                "paginas": (str(paginas[0]) if paginas[0] == paginas[-1]
                            else f"{paginas[0]}-{paginas[-1]}"),
                "idioma": fuente.get("idioma", "es"),
                "origen": fuente.get("origen", "manual"),
                "nivel": nodo.nivel,
                "palabras": _palabras(texto),
                "tags": tags,
            }
            if nodo.puntos:
                meta["puntos"] = nodo.puntos
            if total > 1:
                meta["tramo"] = f"{k + 1}/{total}"
            titulo = nodo.titulo if total == 1 else f"{nodo.titulo} ({k + 1} de {total})"
            neuronas.append(Neurona(
                id=nodo.ids[k], titulo=titulo, texto=texto, meta=meta, migas=migas,
                contiene=[(h.ids[0], h.titulo) for h in nodo.hijos] if k == 0 else [],
                anterior=(nodo.ids[k - 1], nodo.titulo) if k > 0 else None,
                siguiente=(nodo.ids[k + 1], nodo.titulo) if k + 1 < total else None,
            ))
    return neuronas


def enlazar_menciones(neuronas: list, titulos_genericos: set) -> int:
    """"Ver también": enlaza cada neurona con las secciones que nombra.

    Solo cuentan títulos únicos dentro del conjunto. Un título de una sola
    palabra exige mayúscula en mitad de la oración ("gasta Rabia"): así se
    escriben los términos de juego, y evita enlazar palabras comunes."""
    ids_por_titulo: dict = {}
    for n in neuronas:
        if n.meta["tipo"] == "libro" or n.meta.get("tramo", "1/").split("/")[0] != "1":
            continue
        titulo = re.sub(r" \(1 de \d+\)$", "", n.titulo)
        ids_por_titulo.setdefault(titulo, []).append(n.id)
    candidatos = {
        t: ids[0] for t, ids in ids_por_titulo.items()
        if len(ids) == 1 and len(t) >= 4 and t[0].isupper()
        and normalizar(t) not in titulos_genericos and not t.isupper()
    }
    # Se indexan todos los títulos, también los ambiguos: si el texto dice
    # "Fuerza de Voluntad" no debe enlazar a "Fuerza" por ser su prefijo.
    por_primera: dict = {}
    for titulo in ids_por_titulo:
        primera = re.match(r"\w+", titulo)
        if primera:
            por_primera.setdefault(primera.group(0), []).append(titulo)
    for lista in por_primera.values():
        lista.sort(key=len, reverse=True)

    total = 0
    for n in neuronas:
        propios = {n.id} | {i for i, _ in n.migas[-1:]} | {i for i, _ in n.contiene}
        propios |= {x[0] for x in (n.anterior, n.siguiente) if x}
        hallados: dict = {}
        texto = n.texto
        for m in re.finditer(r"\w+", texto):
            for titulo in por_primera.get(m.group(0), ()):
                fin = m.start() + len(titulo)
                if not texto.startswith(titulo, m.start()):
                    continue
                if fin < len(texto) and (texto[fin].isalnum() or texto[fin] == "_"):
                    continue
                if " " not in titulo:
                    antes = texto[:m.start()].rstrip()
                    if not antes or antes[-1] in ".!?:•|*\n":
                        continue
                destino = candidatos.get(titulo)
                if destino and destino not in propios and destino not in hallados:
                    hallados[destino] = titulo
                break
            if len(hallados) >= MAX_VER_TAMBIEN:
                break
        n.ver_tambien = list(hallados.items())
        total += len(hallados)
    return total


# ── Orquestación ──────────────────────────────────────────────────────

def cargar_catalogo(ruta: Path = FUENTES_PATH) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _leer_yaml(ruta: Path) -> dict:
    if not ruta.exists():
        return {}
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def obtener_biblioteca(argumento: "str | None" = None) -> Path:
    """Carpeta local donde están los manuales: --biblioteca, la variable
    NARRADOR_BIBLIOTECA o `cerebro.biblioteca` en config/local.yaml."""
    ruta = (argumento or os.environ.get("NARRADOR_BIBLIOTECA")
            or _leer_yaml(CONFIG_LOCAL_PATH).get("cerebro", {}).get("biblioteca"))
    if not ruta:
        raise SystemExit(
            "No sé dónde están los manuales. Pasá --biblioteca, definí "
            "NARRADOR_BIBLIOTECA o copiá config/local.example.yaml a config/local.yaml."
        )
    return Path(ruta)


def obtener_salida(argumento: "str | None" = None) -> Path:
    ruta = argumento or _leer_yaml(CONFIG_PATH).get("cerebro", {}).get("path", "cerebro")
    return resolve_path(ruta)


def barrer_fuente(fuente: dict, biblioteca: Path, excluir: set) -> "tuple[list, dict]":
    """Una fuente → sus neuronas (todavía sin "ver también" ni escribir)."""
    ruta = biblioteca / fuente["archivo"]
    if not ruta.exists():
        raise FileNotFoundError(f"Fuente '{fuente['id']}': no existe {ruta}")
    lector = leer_txt if ruta.suffix.lower() in (".txt", ".md") else leer_pdf
    raiz, paginas = lector(ruta, fuente)

    if fuente.get("patron_entrada"):
        patron = re.compile(fuente["patron_entrada"])
        for nodo in list(recorrer(raiz)):
            separar_entradas(nodo, patron)
    podar(raiz, excluir)
    asignar_ids(raiz, carpeta_de(fuente))
    neuronas = neuronas_de(raiz, fuente)
    resumen = {
        "archivo": fuente["archivo"],
        "paginas": paginas,
        "neuronas": len(neuronas),
        "palabras": sum(n.meta["palabras"] for n in neuronas),
        "fecha": datetime.now().isoformat(timespec="seconds"),
    }
    return neuronas, resumen


def escribir(neuronas: list, fuente: dict, salida: Path) -> None:
    """Reemplaza la carpeta generada de la fuente por las neuronas nuevas."""
    carpeta = (salida / carpeta_de(fuente)).resolve()
    if salida.resolve() not in carpeta.parents:
        raise ValueError(f"Carpeta de salida fuera del cerebro: {carpeta}")
    if carpeta.exists():
        shutil.rmtree(carpeta)
    for n in neuronas:
        destino = salida / f"{n.id}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(n.a_markdown(), encoding="utf-8")


def barrer(fuentes: list, catalogo: dict, biblioteca: Path, salida: Path) -> dict:
    excluir = {normalizar(t) for t in catalogo.get("excluir_titulos", [])}
    genericos = {normalizar(t) for t in catalogo.get("titulos_genericos", [])}
    manifiesto_path = salida / ".barrido.json"
    manifiesto = {}
    if manifiesto_path.exists():
        manifiesto = json.loads(manifiesto_path.read_text(encoding="utf-8"))

    # Las menciones se enlazan entre todos los libros de un mismo juego.
    por_grupo: dict = {}
    for fuente in fuentes:
        por_grupo.setdefault(fuente.get("sistema") or fuente.get("capa"), []).append(fuente)

    for grupo, lista in por_grupo.items():
        lotes = []
        for fuente in lista:
            logger.info(f"Barriendo {fuente['id']} ({fuente['archivo']})")
            try:
                neuronas, resumen = barrer_fuente(fuente, biblioteca, excluir)
            except Exception as e:
                logger.error(f"Barrido de '{fuente['id']}' falló: {e}", exc_info=True)
                manifiesto[fuente["id"]] = {"error": str(e)}
                continue
            lotes.append((fuente, neuronas, resumen))
        enlaces = enlazar_menciones([n for _, ns, _ in lotes for n in ns], genericos)
        for fuente, neuronas, resumen in lotes:
            escribir(neuronas, fuente, salida)
            manifiesto[fuente["id"]] = resumen
            logger.info(
                f"  {fuente['id']}: {resumen['neuronas']} neuronas, "
                f"{resumen['palabras']} palabras, {resumen['paginas']} págs."
            )
        logger.info(f"Grupo {grupo}: {enlaces} enlaces 'ver también'")

    salida.mkdir(parents=True, exist_ok=True)
    manifiesto_path.write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifiesto


def main(argv: "list | None" = None) -> int:
    parser = argparse.ArgumentParser(description="Barre manuales y genera las neuronas del cerebro.")
    parser.add_argument("--fuente", action="append", help="id de fuente (repetible)")
    parser.add_argument("--sistema", action="append", help="slug de sistema (repetible)")
    parser.add_argument("--todo", action="store_true", help="todas las fuentes del catálogo")
    parser.add_argument("--listar", action="store_true", help="muestra el catálogo y sale")
    parser.add_argument("--biblioteca", help="carpeta local de manuales")
    parser.add_argument("--salida", help="carpeta del vault del cerebro")
    args = parser.parse_args(argv)

    catalogo = cargar_catalogo()
    fuentes = catalogo.get("fuentes", [])
    if args.listar:
        for f in fuentes:
            print(f"{f['id']:24} {f.get('sistema') or f.get('capa'):12} {f['archivo']}")
        return 0
    if not args.todo:
        elegidas = [f for f in fuentes
                    if f["id"] in (args.fuente or []) or f.get("sistema") in (args.sistema or [])]
        if not elegidas:
            parser.error("Indicá --fuente, --sistema o --todo (ver --listar).")
        if args.fuente and not args.sistema:
            # Una fuente suelta se enlaza igual contra el resto de su juego.
            sistemas = {f.get("sistema") for f in elegidas}
            logger.info(f"Se barre solo {args.fuente}; los 'ver también' no cruzan a otros libros de {sistemas}.")
        fuentes = elegidas

    manifiesto = barrer(fuentes, catalogo, obtener_biblioteca(args.biblioteca),
                        obtener_salida(args.salida))
    return 1 if any("error" in manifiesto.get(f["id"], {}) for f in fuentes) else 0


if __name__ == "__main__":
    sys.exit(main())
