#!/usr/bin/env python3
"""Extrae el texto de la normativa descargada y lo divide en fragmentos para el RAG.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/procesar_normativa.py

Entrada
  data/manifests/*.jsonl     generados por scripts/descargar_normativa.py
  data/raw/<fuente>/*.pdf
  data/overrides.json        correcciones manuales de vigencia / exclusión

Salida
  data/processed/chunks.jsonl            un fragmento por línea, con metadatos
  data/processed/textos/<fuente>/*.md    texto limpio de cada documento, para revisarlo

Cómo divide
  1. Corrige caracteres mal codificados en los PDF (ligaduras de Calibri como
     "Ɵ" -> "ti", viñetas de la fuente Symbol, guiones raros...).
  2. Quita cabeceras, pies y números de página (bloques repetidos en muchas páginas).
  3. Detecta la estructura: TÍTULO > CAPÍTULO > SECCIÓN > Artículo / Disposición /
     Preámbulo / Anexo. Cada artículo o disposición es una unidad.
  4. Una unidad que supere MAX_CARACTERES se parte por párrafos (y, si hace falta,
     por frases), repitiendo el último párrafo corto como solape.
  Los documentos sin artículos (resoluciones, guías) se parten solo por párrafos.
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
SALIDA = DATOS / "processed"

MAX_CARACTERES = 1800  # ~450 tokens: cabe en modelos de embeddings de 512 tokens
SOLAPE_MAX = 300       # el último párrafo se repite en el trozo siguiente si es así de corto
MIN_CARACTERES = 40    # fragmentos más cortos (encabezados sueltos) se descartan

# --------------------------------------------------------------------------- #
# 1. Normalización de caracteres
# --------------------------------------------------------------------------- #
# Encontrados en el corpus (ver README del paso): PDF exportados desde Word con
# Calibri asignan las ligaduras a caracteres Unicode equivocados.
REEMPLAZOS = {
    "Ɵ": "ti",   # Ɵ  normaƟva -> normativa
    "ơ": "tí",   # ơ  Arơculo -> Artículo
    "İ": "fí",   # İ  İsica -> física
    "ı́": "í",  # ı + tilde combinada
    "ı": "i",    # ı sin punto
    "": "•", "": "•", "": "•", "∙": "•", "♦": "•",
    "‐": "-", "－": "-", "−": "-", "⁻": "-",
    " ": " ", " ": " ", " ": "\n", "": " ",
    "„": '"', "‟": '"', "ˮ": '"',
    "\x83": "",
}
RE_REEMPLAZOS = re.compile("|".join(sorted(map(re.escape, REEMPLAZOS), key=len, reverse=True)))


def normalizar(texto: str) -> str:
    texto = RE_REEMPLAZOS.sub(lambda m: REEMPLAZOS[m.group(0)], texto)
    texto = unicodedata.normalize("NFKC", texto)        # ﬁ -> fi, letras matemáticas...
    texto = re.sub(r"(?<=[áéíóúÁÉÍÓÚ])́", "", texto)  # tilde duplicada: podrá́
    texto = re.sub(r"([^\W\d_])\1{4,}", "", texto)       # rellenos tipo "nnnnnnnn"
    texto = re.sub(r"\.{4,}|_{4,}|…{2,}", " ", texto)    # líneas de puntos y subrayados
    return texto


# --------------------------------------------------------------------------- #
# 2. Extracción por bloques y limpieza de cabeceras/pies
# --------------------------------------------------------------------------- #
@dataclass
class Linea:
    texto: str
    pagina: int  # 1-based
    bloque: int  # identificador global del bloque (para reconstruir párrafos)


RE_SOLO_PAGINA = re.compile(r"^\s*(p[áa]g(ina|\.)?\s*)?\d{1,3}(\s*(de|/)\s*\d{1,3})?\s*$", re.I)
RE_INDICE = re.compile(r"(\.{4,}|…{2,}|_{4,}|\.\s\.\s\.\s)\s*\d{1,3}\s*$")  # "Objeto ..... 5"
MARGEN = 0.12  # fracción de la altura de página considerada cabecera / pie


def clave_repeticion(texto: str) -> str:
    return re.sub(r"\d+", "#", " ".join(texto.lower().split()))


@dataclass
class Bloque:
    texto: str
    en_margen: bool  # está en la franja superior o inferior de la página


def extraer_lineas(ruta: Path) -> tuple[list[Linea], int]:
    doc = pymupdf.open(ruta)
    paginas: list[list[Bloque]] = []
    for pagina in doc:
        alto = pagina.rect.height or 1
        bloques = []
        # sort=False: orden interno del PDF, que respeta las columnas. Ordenar por
        # coordenadas mezclaba las dos columnas de los documentos con formato BOULPGC.
        for x0, y0, x1, y1, crudo, _, tipo in pagina.get_text("blocks", sort=False):
            if tipo != 0:
                continue
            # Las entradas del índice se detectan antes de normalizar (por sus puntos).
            texto = "\n".join(normalizar(l) for l in crudo.splitlines() if not RE_INDICE.search(l))
            if texto.strip():
                bloques.append(Bloque(texto, y1 < MARGEN * alto or y0 > (1 - MARGEN) * alto))
        paginas.append(bloques)
    n = len(paginas)

    # Cabeceras y pies: bloques del margen que se repiten en muchas páginas, o que
    # son solo un número de página. Nunca se quita un encabezado ("Artículo 5").
    repetidos: set[str] = set()
    if n >= 3:
        cuenta = Counter(k for bloques in paginas
                         for k in {clave_repeticion(b.texto) for b in bloques if b.en_margen})
        repetidos = {k for k, c in cuenta.items() if c >= max(3, 0.4 * n)}

    def es_ruido(b: Bloque) -> bool:
        if not b.en_margen or tipo_encabezado(b.texto.splitlines()[0].strip()):
            return False
        return clave_repeticion(b.texto) in repetidos or bool(RE_SOLO_PAGINA.match(b.texto))

    lineas: list[Linea] = []
    id_bloque = 0
    for num, bloques in enumerate(paginas, 1):
        for b in bloques:
            id_bloque += 1
            if es_ruido(b):
                continue
            for t in b.texto.splitlines():
                t = " ".join(t.split())
                if t and not (b.en_margen and RE_SOLO_PAGINA.match(t)):
                    lineas.append(Linea(t, num, id_bloque))
    return lineas, n


# --------------------------------------------------------------------------- #
# 3. Estructura
# --------------------------------------------------------------------------- #
ORD = (r"(?:PRELIMINAR|[IVXLC]+|\d+\.?\s*[ªº]?|PRIMER[OA]?|SEGUND[OA]|TERCER[OA]?|CUART[OA]"
       r"|QUINT[OA]|SEXT[OA]|S[ÉE]PTIM[OA]|OCTAV[OA]|NOVEN[OA]|D[ÉE]CIM[OA]|[ÚU]NIC[OA])")
RE_TITULO = re.compile(rf"^T[ÍI]TULO\s+{ORD}(?![\wáéíóú])", re.I)
RE_CAPITULO = re.compile(rf"^CAP[ÍI]TULO\s+{ORD}(?![\wáéíóú])", re.I)
RE_SECCION = re.compile(rf"^SECCI[ÓO]N\s+{ORD}(?![\wáéíóú])", re.I)
RE_ARTICULO = re.compile(
    r"^(?:Art[íi]culo|ART[ÍI]CULO|Art\.)\s*(\d+|[úu]nico|ÚNICO)\s*(?:\.?\s*[ºª])?"
    r"\s*(bis|ter|quater)?\s*(?=[\.\-–—:]|$)")
RE_DISPOSICION = re.compile(
    r"^(?:DISPOSICI[ÓO]N|Disposici[óo]n)(ES|es)?\s+(ADICIONAL|TRANSITORIA|DEROGATORIA|FINAL)", re.I)
RE_PREAMBULO = re.compile(r"^(PRE[ÁA]MBULO|EXPOSICI[ÓO]N DE MOTIVOS|INTRODUCCI[ÓO]N)\b", re.I)
RE_ANEXO = re.compile(r"^(ANEXO|Anexo)\b(\s+[IVXLC\d]+)?(?=\s*[\.\-–—:]|\s*$|\s+[A-ZÁÉÍÓÚ]{2})")
RE_PARTE = re.compile(r"^(MODALIDAD|PARTE)\s+([A-Z]|[IVXLC]+|\d+)\b")  # partes con numeración propia


def es_mayusculas(t: str) -> bool:
    letras = [c for c in t if c.isalpha()]
    return len(letras) >= 3 and all(c.isupper() for c in letras)


def tras_ordinal_valido(linea: str, fin: int) -> bool:
    """Tras 'CAPÍTULO II' debe venir fin de línea, un separador o texto en mayúsculas;
    así 'Título II de la Ley...' (una referencia) no cuenta como encabezado."""
    resto = linea[fin:].strip()
    return not resto or resto[0] in ".:-–—" or es_mayusculas(linea)


def tipo_encabezado(linea: str, inicio_bloque: bool = True) -> tuple[str, str] | None:
    """Devuelve (tipo, número) si la línea es un encabezado estructural.

    `inicio_bloque`: si la línea abre un bloque de texto del PDF. Un "Anexo IV" o
    una "Disposición adicional" en minúsculas a mitad de párrafo son referencias,
    no encabezados.
    """
    if len(linea) > 220:
        return None
    if not inicio_bloque and re.match(r"^(Anexo|Disposici[óo]n)\b", linea):
        return None
    for tipo, rx in (("titulo", RE_TITULO), ("capitulo", RE_CAPITULO), ("seccion", RE_SECCION)):
        m = rx.match(linea)
        if m and tras_ordinal_valido(linea, m.end()):
            return tipo, ""
    m = RE_ARTICULO.match(linea)
    if m:
        return "articulo", (m.group(1) + (" " + m.group(2) if m.group(2) else "")).lower()
    m = RE_DISPOSICION.match(linea)
    if m and len(linea) <= 160:
        if m.group(1):  # "DISPOSICIONES FINALES": agrupa, no es una disposición
            return "grupo", ""
        return "disposicion", m.group(2).lower()
    if RE_PREAMBULO.match(linea) and len(linea) <= 40:
        return "preambulo", ""
    if RE_ANEXO.match(linea) and len(linea) <= 160:
        return "anexo", ""
    if RE_PARTE.match(linea) and len(linea) <= 160:
        return "parte", ""
    return None


@dataclass
class Unidad:
    tipo: str            # articulo | disposicion | preambulo | anexo | parte | texto
    numero: str
    encabezado: str
    ruta: list[str]      # [ANEXO/MODALIDAD..., TÍTULO..., CAPÍTULO..., SECCIÓN...]
    lineas: list[Linea] = field(default_factory=list)
    parte: str = ""      # anexo o modalidad al que pertenece (puede reiniciar la numeración)


def ruta_vacia(parte: str = "") -> dict[str, str]:
    return {"parte": parte, "titulo": "", "capitulo": "", "seccion": ""}


def estructurar(lineas: list[Linea]) -> list[Unidad]:
    unidades: list[Unidad] = []
    ruta = ruta_vacia()
    actual: Unidad | None = None
    i = 0
    while i < len(lineas):
        ln = lineas[i]
        tipo = tipo_encabezado(ln.texto, i == 0 or lineas[i - 1].bloque != ln.bloque)
        if tipo is None:
            if actual is None:
                partes = [p for p in ruta.values() if p]
                actual = Unidad("texto", "", partes[-1] if partes else "Encabezamiento",
                                partes, parte=ruta["parte"])
                unidades.append(actual)
            actual.lineas.append(ln)
            i += 1
            continue

        # Encabezados en mayúsculas que continúan en la línea siguiente.
        texto = ln.texto
        j = i + 1
        while (tipo[0] in ("titulo", "capitulo", "seccion", "disposicion", "anexo", "parte")
               and es_mayusculas(texto) and j < len(lineas) and j - i <= 2
               and es_mayusculas(lineas[j].texto) and len(lineas[j].texto) <= 120
               and tipo_encabezado(lineas[j].texto) is None):
            texto += " " + lineas[j].texto
            j += 1

        clase, numero = tipo
        if clase == "grupo":
            ruta = ruta_vacia(ruta["parte"])
            actual = None
        elif clase in ("titulo", "capitulo", "seccion"):
            ruta[clase] = texto
            if clase == "titulo":
                ruta["capitulo"] = ruta["seccion"] = ""
            elif clase == "capitulo":
                ruta["seccion"] = ""
            actual = None
        else:
            if clase == "preambulo":
                ruta = ruta_vacia()
            elif clase == "disposicion":  # una disposición dentro de un anexo sigue en él
                ruta = ruta_vacia(ruta["parte"])
            elif clase in ("anexo", "parte"):  # pueden reiniciar la numeración de artículos
                ruta = ruta_vacia(texto)
            actual = Unidad(clase, numero, texto, [p for p in ruta.values() if p],
                            [Linea(texto, ln.pagina, ln.bloque)], parte=ruta["parte"])
            unidades.append(actual)
        i = j
    return quitar_indice(unidades)


def quitar_indice(unidades: list[Unidad]) -> list[Unidad]:
    """Quita los restos de un índice sin puntos.

    - Si un artículo (mismo número y parte) o una disposición (mismo encabezado)
      aparece varias veces, las apariciones anteriores a la más larga se quitan
      si están en una racha de índice: sin texto, o justo detrás de una unidad
      sin texto (una entrada de índice puede arrastrar una nota al pie). Así no
      se pierden artículos reales cuando un anexo reutiliza la numeración.
    - Se quitan los encabezados sin texto que van seguidos o precedidos de otro
      encabezado sin texto (racha de índice). Uno aislado puede ser un artículo de
      una sola línea ("Artículo 28. Los CGI realizarán...") y se conserva.
    """
    def clave(u: Unidad) -> tuple:
        if u.tipo == "articulo":
            return (u.tipo, u.numero, u.parte)
        return (u.tipo, " ".join(u.encabezado.upper().split())[:60], u.parte)

    posicion = {id(u): i for i, u in enumerate(unidades)}
    grupos: dict[tuple, list[Unidad]] = defaultdict(list)
    for u in unidades:
        if u.tipo != "texto":
            grupos[clave(u)].append(u)

    def vacia(i: int) -> bool:
        return 0 <= i < len(unidades) and unidades[i].tipo != "texto" and longitud(unidades[i]) == 0

    def en_indice(u: Unidad) -> bool:
        i = posicion[id(u)]
        anterior = unidades[i - 1] if i > 0 else None
        return longitud(u) < 150 or (longitud(u) < 600 and anterior is not None
                                     and anterior.tipo != "texto" and longitud(anterior) < 60)

    fuera = set()
    for grupo in grupos.values():
        if len(grupo) > 1:
            mejor = max(grupo, key=longitud)
            fuera |= {id(u) for u in grupo
                      if posicion[id(u)] < posicion[id(mejor)] and en_indice(u)}
    for i, u in enumerate(unidades):
        if vacia(i) and (vacia(i - 1) or vacia(i + 1)):
            fuera.add(id(u))
    return [u for u in unidades if id(u) not in fuera]


def longitud(u: Unidad) -> int:
    return sum(len(l.texto) for l in u.lineas[1:]) if u.tipo != "texto" else \
        sum(len(l.texto) for l in u.lineas)


# --------------------------------------------------------------------------- #
# 4. Párrafos y troceado
# --------------------------------------------------------------------------- #
RE_ENUM = re.compile(r"^(\d{1,2}[\.\)]|[a-zñ][\)\.]|[•\-–·]|[ivx]{1,4}\))(\s|$)")
RE_FRASE = re.compile(r"(?<=[\.;:])\s+(?=[A-ZÁÉÍÓÚÑ0-9¿¡\"«(])")


def parrafos(lineas: list[Linea]) -> list[tuple[str, set[int]]]:
    out: list[tuple[str, set[int]]] = []
    texto, paginas, bloque = "", set(), None
    for ln in lineas:
        if texto and (ln.bloque != bloque or RE_ENUM.match(ln.texto)):
            out.append((texto, paginas))
            texto, paginas = "", set()
        if not texto:
            texto = ln.texto
        elif texto.endswith("-") and len(texto) > 1 and texto[-2].isalpha() and ln.texto[:1].islower():
            texto = texto[:-1] + ln.texto  # palabra partida con guion
        else:
            texto += " " + ln.texto
        paginas.add(ln.pagina)
        bloque = ln.bloque
    if texto:
        out.append((texto, paginas))
    return out


def partir_largo(texto: str) -> list[str]:
    """Divide un párrafo demasiado largo por frases y, si no basta, por palabras."""
    piezas, actual = [], ""
    for frase in RE_FRASE.split(texto):
        while len(frase) > MAX_CARACTERES:  # sin puntuación (tablas): corte por palabras
            corte = frase.rfind(" ", 0, MAX_CARACTERES)
            corte = corte if corte > 0 else MAX_CARACTERES
            if actual:
                piezas.append(actual)
                actual = ""
            piezas.append(frase[:corte])
            frase = frase[corte:].strip()
        if actual and len(actual) + 1 + len(frase) > MAX_CARACTERES:
            piezas.append(actual)
            actual = frase
        else:
            actual = f"{actual} {frase}".strip()
    if actual:
        piezas.append(actual)
    return piezas


def trocear(pars: list[tuple[str, set[int]]]) -> list[tuple[str, list[int]]]:
    expandidos = []
    for texto, pags in pars:
        if len(texto) > MAX_CARACTERES:
            expandidos += [(p, pags) for p in partir_largo(texto)]
        else:
            expandidos.append((texto, pags))

    trozos: list[list[tuple[str, set[int]]]] = []
    actual: list[tuple[str, set[int]]] = []
    for p in expandidos:
        if actual and sum(len(t) + 1 for t, _ in actual) + len(p[0]) > MAX_CARACTERES:
            trozos.append(actual)
            ultimo = actual[-1]
            cabe = len(ultimo[0]) + 1 + len(p[0]) <= MAX_CARACTERES
            actual = [ultimo] if len(ultimo[0]) <= SOLAPE_MAX and len(actual) > 1 and cabe else []
        actual.append(p)
    if actual:
        trozos.append(actual)
    return [("\n".join(t for t, _ in tr), sorted(set().union(*(pg for _, pg in tr))))
            for tr in trozos]


# --------------------------------------------------------------------------- #
# 5. Programa principal
# --------------------------------------------------------------------------- #
def cargar_documentos() -> list[dict]:
    docs = []
    for manifiesto in sorted((DATOS / "manifests").glob("*.jsonl")):
        for linea in manifiesto.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                d = json.loads(linea)
                if d.get("archivo") and not d.get("duplicado_de") and not d.get("error"):
                    docs.append(d)
    return docs


def vigencia(doc: dict, overrides: dict) -> tuple[bool, str, bool]:
    o = overrides.get(doc["url"], {})
    vigente, motivo = True, ""
    if re.search(r"derogad", doc["titulo"], re.I):
        vigente, motivo = False, "Marcado como derogado en la web de origen."
    if "vigente" in o:
        vigente, motivo = o["vigente"], o.get("motivo", motivo)
    return vigente, motivo, bool(o.get("excluir"))


def shingles(texto: str, n: int = 6) -> set[int]:
    palabras = re.findall(r"\w+", texto.lower())
    return {hash(" ".join(palabras[i:i + n])) for i in range(max(0, len(palabras) - n + 1))}


def main() -> None:
    overrides = json.loads((DATOS / "overrides.json").read_text(encoding="utf-8"))
    docs = cargar_documentos()
    SALIDA.mkdir(parents=True, exist_ok=True)

    chunks, sin_estructura, avisos, firmas = [], [], [], {}
    for d in docs:
        vigente, motivo, excluir = vigencia(d, overrides)
        if excluir:
            print(f"EXCLUIDO  {d['titulo'][:80]}  ({overrides[d['url']].get('motivo', '')})")
            continue
        lineas, n_paginas = extraer_lineas(RAIZ / d["archivo"])
        unidades = estructurar(lineas)
        n_art = sum(u.tipo == "articulo" for u in unidades)
        if n_art == 0:
            sin_estructura.append(d["titulo"])
        texto_doc = "\n".join(l.texto for l in lineas)
        firmas[d["url"]] = (d["titulo"], shingles(texto_doc))
        if len(texto_doc) < 200 * max(1, n_paginas) * 0.3:
            avisos.append(f"poco texto ({len(texto_doc)} car, {n_paginas} pág): {d['titulo'][:70]}")

        doc_id = d["sha256"][:12]
        md = [f"# {d['titulo']}", "", f"- Fuente: {d['fuente']}  ", f"- URL: {d.get('url_final') or d['url']}  ",
              f"- Vigente: {'sí' if vigente else 'NO — ' + motivo}  ",
              f"- Categorías: {', '.join(d['categorias'])}", ""]
        n_chunk = 0
        for u in unidades:
            trozos = [t for t in trocear(parrafos(u.lineas))
                      if len(t[0]) >= MIN_CARACTERES or re.search(r"derog|suprim", t[0], re.I)]
            if not trozos:
                continue
            md += ["", f"## {u.encabezado}" + (f"  _({' > '.join(u.ruta)})_" if u.ruta else ""), ""]
            for parte, (texto, paginas) in enumerate(trozos, 1):
                n_chunk += 1
                md.append(texto + "\n")
                chunks.append({
                    "id": f"{doc_id}-{n_chunk:03d}",
                    "doc_id": doc_id,
                    "fuente": d["fuente"],
                    "titulo_doc": d["titulo"],
                    "url": d.get("url_final") or d["url"],
                    "categorias": d["categorias"],
                    "vigente": vigente,
                    "motivo_no_vigente": motivo,
                    "ruta": u.ruta,
                    "tipo": u.tipo,
                    "numero": u.numero,
                    "encabezado": u.encabezado[:250],
                    "paginas": paginas,
                    "parte": parte,
                    "partes": len(trozos),
                    "texto": texto,
                })
        ruta_md = SALIDA / "textos" / d["fuente"] / (Path(d["archivo"]).stem + ".md")
        ruta_md.parent.mkdir(parents=True, exist_ok=True)
        ruta_md.write_text("\n".join(md), encoding="utf-8")
        print(f"{n_chunk:4} fragmentos · {n_art:3} artículos · {n_paginas:3} pág · {d['titulo'][:70]}")

    with (SALIDA / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ resumen
    largos = [len(c["texto"]) for c in chunks]
    por_tipo = Counter(c["tipo"] for c in chunks)
    print(f"\n== {len(docs)} documentos · {len(chunks)} fragmentos "
          f"({sum(not c['vigente'] for c in chunks)} no vigentes)")
    print(f"   longitud (caracteres): mediana {statistics.median(largos):.0f} · "
          f"p95 {sorted(largos)[int(0.95 * len(largos))]} · máx {max(largos)}")
    print(f"   por tipo: {dict(por_tipo)}")
    print(f"   documentos sin artículos (troceados por párrafos): {len(sin_estructura)}")
    raros = Counter(ch for c in chunks for ch in c["texto"]
                    if ord(ch) > 0x2000 and ch not in "–—‘’“”•…€")
    if raros:
        print(f"   caracteres raros restantes: {dict(raros.most_common(10))}")
    for a in avisos:
        print(f"   AVISO {a}")

    # Documentos casi idénticos (p. ej. el mismo reglamento publicado en dos webs).
    items = list(firmas.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (u1, (t1, s1)), (u2, (t2, s2)) = items[i], items[j]
            if s1 and s2:
                jac = len(s1 & s2) / len(s1 | s2)
                if jac >= 0.6:
                    print(f"   CASI DUPLICADOS ({jac:.0%}): «{t1[:60]}» y «{t2[:60]}»\n"
                          f"      {u1}\n      {u2}")


if __name__ == "__main__":
    main()
