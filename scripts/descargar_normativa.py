#!/usr/bin/env python3
"""Descarga la normativa general de la ULPGC y la normativa propia de la EII.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/descargar_normativa.py              # ULPGC + EII
    python scripts/descargar_normativa.py --solo eii   # solo una fuente

Qué descarga
  ULPGC  Todos los reglamentos de /reglamentos/reglamentos-todos (incluye los
         Estatutos), anotando a qué temas pertenece cada uno, y los documentos
         de normativa de las páginas de PAGINAS_EXTRA_ULPGC.
         No descarga el BOULPGC (el boletín oficial completo).
  EII    /es/escuela/normativa con todas sus páginas ("Cargar más") y las
         subpáginas de normativa que enlaza (Prácticas Externas, TFT...).

Resultado
  data/raw/<fuente>/*.pdf          documentos (no se suben a git)
  data/manifests/<fuente>.jsonl    una línea por documento con sus metadatos

Buenas prácticas
  - Lee el robots.txt de cada servidor y respeta su Crawl-delay
    (10 s en www.ulpgc.es; DEFAULT_DELAY si el servidor no indica nada).
  - Es reanudable: lo que ya está en el manifiesto y en disco no se vuelve a pedir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "normativa-ulpgc-rag/1.0 (proyecto academico)"
DEFAULT_DELAY = 2.0  # segundos entre peticiones si robots.txt no fija Crawl-delay

ULPGC = "https://www.ulpgc.es"
EII = "https://www.eii.ulpgc.es"

# Páginas de la ULPGC fuera del índice de reglamentos que también contienen
# normativa (enlazadas desde la web de la EII). Solo se cogen los PDF cuyo
# texto encaje con FILTRO_EXTRA, para no traer organigramas ni cartas de servicio.
PAGINAS_EXTRA_ULPGC = [f"{ULPGC}/gestion-academica/progresoypermanencia"]
FILTRO_EXTRA = re.compile(r"normativa|normas|reglamento|instrucci|modificaci", re.I)

RAIZ = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class Cliente:
    """Sesión HTTP educada: respeta robots.txt y espera entre peticiones por servidor."""

    def __init__(self) -> None:
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = USER_AGENT
        self.robots: dict[str, RobotFileParser] = {}
        self.ultima: dict[str, float] = {}

    def _robots(self, host: str) -> RobotFileParser:
        if host not in self.robots:
            rp = RobotFileParser()
            try:
                r = self.sesion.get(f"https://{host}/robots.txt", timeout=30)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[host] = rp
            self.ultima[host] = time.monotonic()
        return self.robots[host]

    def get(self, url: str) -> requests.Response:
        host = urlparse(url).netloc
        rp = self._robots(host)
        if not rp.can_fetch(USER_AGENT, url):
            raise PermissionError(f"robots.txt no permite {url}")
        espera = float(rp.crawl_delay(USER_AGENT) or DEFAULT_DELAY)
        pendiente = self.ultima.get(host, 0.0) + espera - time.monotonic()
        if pendiente > 0:
            time.sleep(pendiente)
        try:
            r = self.sesion.get(url, timeout=120)
        finally:
            self.ultima[host] = time.monotonic()
        r.raise_for_status()
        return r


# --------------------------------------------------------------------------- #
# Modelo de datos y manifiesto
# --------------------------------------------------------------------------- #
@dataclass
class Documento:
    url: str                      # enlace tal como aparece en la web
    fuente: str                   # "ulpgc" | "eii"
    titulo: str
    categorias: list[str] = field(default_factory=list)   # temas ULPGC / secciones EII
    encontrado_en: list[str] = field(default_factory=list)
    nota: str = ""                # texto que acompaña al enlace (p. ej. fecha de modificación)
    url_final: str = ""           # tras redirecciones
    archivo: str = ""             # ruta relativa a la raíz del proyecto
    sha256: str = ""
    bytes: int = 0
    tipo: str = ""                # Content-Type devuelto por el servidor
    descargado: str = ""          # fecha ISO de descarga
    duplicado_de: str = ""        # url de otro documento con idéntico contenido
    error: str = ""


def cargar_manifiesto(ruta: Path) -> dict[str, Documento]:
    docs: dict[str, Documento] = {}
    if ruta.exists():
        validos = {f.name for f in fields(Documento)}
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                d = json.loads(linea)
                docs[d["url"]] = Documento(**{k: v for k, v in d.items() if k in validos})
    return docs


def guardar_manifiesto(ruta: Path, docs: dict[str, Documento]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for d in docs.values():
            f.write(json.dumps(asdict(d), ensure_ascii=False) + "\n")
    tmp.replace(ruta)


def registrar(docs: dict[str, Documento], url: str, fuente: str, titulo: str,
              pagina: str, categoria: str = "", nota: str = "") -> None:
    """Añade un documento o, si ya existe, le suma la nueva categoría/página."""
    d = docs.get(url)
    if d is None:
        d = docs[url] = Documento(url=url, fuente=fuente, titulo=titulo, nota=nota)
    if len(titulo) > len(d.titulo):
        d.titulo = titulo
    if nota and not d.nota:
        d.nota = nota
    if categoria and categoria not in d.categorias:
        d.categorias.append(categoria)
    if pagina not in d.encontrado_en:
        d.encontrado_en.append(pagina)


# --------------------------------------------------------------------------- #
# Utilidades HTML
# --------------------------------------------------------------------------- #
def limpio(texto: str) -> str:
    return " ".join(texto.split())


def enlaces(raiz, base: str):
    """Genera (url_absoluta_sin_fragmento, texto, etiqueta <a>)."""
    for a in raiz.find_all("a", href=True):
        url = urldefrag(urljoin(base, a["href"].strip()))[0]
        yield url, limpio(a.get_text(" ")), a


def es_pdf(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def es_documento_eii(url: str) -> bool:
    p = urlparse(url)
    return p.netloc == urlparse(EII).netloc and (
        es_pdf(url) or re.fullmatch(r"(/es)?/document/\d+", p.path) is not None
    )


def de_ulpgc(url: str) -> bool:
    host = urlparse(url).netloc
    return host == "ulpgc.es" or host.endswith(".ulpgc.es")


def titulo_pagina(sopa: BeautifulSoup) -> str:
    h1 = sopa.find("h1")
    if h1 and limpio(h1.get_text(" ")):
        return limpio(h1.get_text(" "))
    return limpio(sopa.title.get_text(" ")) if sopa.title else ""


# --------------------------------------------------------------------------- #
# Recolección de enlaces
# --------------------------------------------------------------------------- #
def recolectar_ulpgc(cli: Cliente, docs: dict[str, Documento]) -> None:
    base = f"{ULPGC}/reglamentos/"

    print("ULPGC · índice de todos los reglamentos")
    r = cli.get(base + "reglamentos-todos")
    for url, texto, _ in enlaces(BeautifulSoup(r.text, "html.parser"), r.url):
        if es_pdf(url) and de_ulpgc(url):
            registrar(docs, url, "ulpgc", texto, r.url)

    print("ULPGC · índice por temas")
    r = cli.get(base + "reglamentos-por-tema")
    temas: dict[str, str] = {}
    for url, texto, _ in enlaces(BeautifulSoup(r.text, "html.parser"), r.url):
        if re.search(r"/reglamentos/reglamentos-tema/\d+$", url):
            temas.setdefault(url, texto)

    for i, (url_tema, nombre) in enumerate(temas.items(), 1):
        print(f"ULPGC · tema {i}/{len(temas)}: {nombre}")
        r = cli.get(url_tema)
        for url, texto, _ in enlaces(BeautifulSoup(r.text, "html.parser"), r.url):
            if es_pdf(url) and de_ulpgc(url):
                registrar(docs, url, "ulpgc", texto, r.url, categoria=nombre)

    for pagina in PAGINAS_EXTRA_ULPGC:
        print(f"ULPGC · página extra: {pagina}")
        r = cli.get(pagina)
        sopa = BeautifulSoup(r.text, "html.parser")
        seccion = titulo_pagina(sopa)
        for url, texto, _ in enlaces(sopa, r.url):
            if es_pdf(url) and de_ulpgc(url) and FILTRO_EXTRA.search(texto):
                registrar(docs, url, "ulpgc", texto, r.url, categoria=seccion)


def seccion_eii(a, pagina: str, seccion_pagina: str) -> tuple[str, str]:
    """Devuelve (categoría, título completo) de un enlace de la web de la EII."""
    # Tabla "ULPGC | EII": la primera celda de la fila es el tema.
    tr = a.find_parent("tr")
    if tr:
        celdas = tr.find_all("td")
        if celdas and a not in celdas[0].find_all("a"):
            tema = limpio(celdas[0].get_text(" "))
            if tema:
                return tema, ""
    # Listado paginado de resoluciones: el título completo está en otra celda.
    campo = a.find_parent("div", class_="views-field")
    if campo:
        nombre = campo.find_previous_sibling("div", class_="views-field-name")
        titulo = limpio(nombre.get_text(" ")) if nombre else ""
        if pagina.startswith(f"{EII}/es/escuela/normativa"):
            return "Resoluciones y acuerdos de la Dirección", titulo
        return seccion_pagina, titulo
    return seccion_pagina, ""


def recolectar_eii(cli: Cliente, docs: dict[str, Documento]) -> None:
    pendientes = [f"{EII}/es/escuela/normativa"]
    visitadas: set[str] = set()
    while pendientes:
        pagina = pendientes.pop(0)
        if pagina in visitadas:
            continue
        visitadas.add(pagina)
        print(f"EII · {pagina}")
        r = cli.get(pagina)
        if r.url != pagina and r.url in visitadas:  # misma página con otra URL
            continue
        visitadas.add(r.url)
        sopa = BeautifulSoup(r.text, "html.parser")
        seccion_pagina = titulo_pagina(sopa)
        contenido = sopa.find(id="content") or sopa

        for url, texto, a in enlaces(contenido, r.url):
            p = urlparse(url)
            if es_documento_eii(url):
                categoria, titulo_largo = seccion_eii(a, pagina, seccion_pagina)
                nota = ""
                if a.parent and a.parent.name == "p":
                    nota = limpio(a.parent.get_text(" ").replace(a.get_text(" "), "", 1))
                registrar(docs, url, "eii", titulo_largo or texto, r.url,
                          categoria=categoria, nota=nota)
            elif p.netloc == urlparse(EII).netloc and "/admin/" not in p.path:
                # Paginación ("Cargar más") y subpáginas de normativa.
                es_paginacion = p.path == urlparse(pagina).path and "page=" in p.query
                if es_paginacion or "normativa" in p.path.lower():
                    if url not in visitadas:
                        pendientes.append(url)


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #
def nombre_archivo(titulo: str, url: str, sha: str, ext: str) -> str:
    base = titulo or Path(urlparse(url).path).stem
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()[:80] or "documento"
    return f"{base}-{sha[:8]}{ext}"


def descargar(cli: Cliente, docs: dict[str, Documento], carpeta: Path,
              manifiesto: Path) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    por_hash = {d.sha256: d for d in docs.values() if d.sha256 and not d.duplicado_de}
    total = len(docs)
    for i, d in enumerate(docs.values(), 1):
        if d.archivo and (RAIZ / d.archivo).exists():
            continue
        print(f"[{i}/{total}] {d.titulo[:90]}")
        try:
            r = cli.get(d.url)
        except (requests.RequestException, PermissionError) as e:
            d.error = str(e)
            print(f"    ERROR: {e}")
            guardar_manifiesto(manifiesto, docs)
            continue
        datos = r.content
        sha = hashlib.sha256(datos).hexdigest()
        ext = ".pdf" if datos[:5] == b"%PDF-" else (Path(urlparse(r.url).path).suffix or ".bin")
        d.url_final, d.sha256, d.bytes = r.url, sha, len(datos)
        d.tipo = r.headers.get("content-type", "").split(";")[0]
        d.descargado = datetime.now(timezone.utc).isoformat(timespec="seconds")
        d.error = ""
        if sha in por_hash and por_hash[sha] is not d:
            original = por_hash[sha]
            d.duplicado_de, d.archivo = original.url, original.archivo
            print(f"    duplicado de: {original.titulo[:70]}")
        else:
            ruta = carpeta / nombre_archivo(d.titulo, r.url, sha, ext)
            ruta.write_bytes(datos)
            d.archivo = ruta.relative_to(RAIZ).as_posix()
            por_hash[sha] = d
        guardar_manifiesto(manifiesto, docs)


def resumen(fuente: str, docs: dict[str, Documento]) -> None:
    unicos = [d for d in docs.values() if d.archivo and not d.duplicado_de]
    dup = sum(1 for d in docs.values() if d.duplicado_de)
    err = [d for d in docs.values() if d.error]
    no_pdf = [d for d in unicos if not d.archivo.endswith(".pdf")]
    mb = sum(d.bytes for d in unicos) / 1e6
    print(f"\n== {fuente.upper()}: {len(docs)} enlaces · {len(unicos)} documentos únicos "
          f"({mb:.1f} MB) · {dup} duplicados · {len(err)} errores · {len(no_pdf)} no-PDF")
    for d in err:
        print(f"   ERROR  {d.url}  ->  {d.error}")
    for d in no_pdf:
        print(f"   NO-PDF {d.archivo}  ({d.tipo})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--solo", choices=["ulpgc", "eii"], help="descargar solo una fuente")
    ap.add_argument("--datos", default="data", help="carpeta de datos (por defecto: data)")
    args = ap.parse_args()

    datos = RAIZ / args.datos
    fuentes = [args.solo] if args.solo else ["eii", "ulpgc"]
    recolectores = {"ulpgc": recolectar_ulpgc, "eii": recolectar_eii}
    cli = Cliente()

    for fuente in fuentes:
        manifiesto = datos / "manifests" / f"{fuente}.jsonl"
        docs = cargar_manifiesto(manifiesto)
        recolectores[fuente](cli, docs)
        guardar_manifiesto(manifiesto, docs)
        descargar(cli, docs, datos / "raw" / fuente, manifiesto)
        resumen(fuente, docs)


if __name__ == "__main__":
    main()
