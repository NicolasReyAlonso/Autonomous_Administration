"""Extrae las fichas de trámite de la sede electrónica impresas como PDF.

La sede (administracion.ulpgc.es) no se puede descargar automáticamente (su robots.txt
solo permite la portada), así que cada ficha se imprime desde el navegador
(Chrome → Imprimir → Guardar como PDF) en data/plantillas/tramites/.

Este script lee esos PDF y escribe data/plantillas/tramites.jsonl, una ficha por línea:
  nombre, codigo_sia, url_catalogo, presentacion (ventana de presentación electrónica,
  si la indica), secciones {Descripción, Requisitos, Documentación Obligatoria, ...},
  enlaces por sección [{texto, url}], fichero y fecha de impresión.

Los apartados se reconocen por su formato (negrita de 14 pt) y el título por su tamaño
(22 pt). Uso: python scripts/extraer_tramites.py
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "data" / "plantillas" / "tramites"
SALIDA = RAIZ / "data" / "plantillas" / "tramites.jsonl"

FIN = "ACERCA DE ESTA PÁGINA"
# Cabecera y pie que Chrome añade a cada página, y la barra de navegación de la sede
RUIDO = [
    re.compile(r"^\d\d/\d\d/\d\d, \d\d:\d\d$"),
    re.compile(r"^Sede Electrónica de Universidad de Las Palmas de Gran Canaria - "),
    re.compile(r"^https://administracion\.ulpgc\.es/catalog/"),
    re.compile(r"^\d+/\d+$"),
    re.compile(r"^\d{1,2} de \w+ \d{4}, \d\d:\d\d:\d\d$"),
    re.compile(r"^(Inicio|Trámites|Identifícate|SEDE ELECTRÓNICA|Menú)$"),
    re.compile(r"^.$"),  # restos de líneas cortadas en el salto de página
]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def es_ruido(linea: str) -> bool:
    return any(r.search(linea) for r in RUIDO)


def extraer(pdf: Path) -> dict:
    doc = pymupdf.open(pdf)
    titulo, lineas = [], []  # lineas: (página, y, texto, es_encabezado)
    url = None
    for n, pag in enumerate(doc):
        for bloque in pag.get_text("dict")["blocks"]:
            for l in bloque.get("lines", []):
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                texto = nfc("".join(s["text"] for s in spans).strip())
                if m := re.search(r"https://administracion\.ulpgc\.es/catalog/t/[0-9a-f-]+", texto):
                    url = url or m.group(0)
                if es_ruido(texto):
                    continue
                negrita = all(s["flags"] & 16 for s in spans)
                tam = round(max(s["size"] for s in spans))
                if negrita and tam >= 20:
                    titulo.append(texto)
                    continue
                lineas.append((n, l["bbox"][1], texto, negrita and tam == 14))

    secciones: dict[str, list[str]] = {"_cabecera": []}
    marcas: list[tuple[int, float, str]] = []  # dónde empieza cada sección, para los enlaces
    actual = "_cabecera"
    for n, y, texto, encabezado in lineas:
        if texto == FIN:
            marcas.append((n, y, "_fin"))
            break
        if encabezado:
            actual = texto
            secciones[actual] = []
            marcas.append((n, y, actual))
        else:
            secciones[actual].append(texto)

    def seccion_en(n: int, y: float) -> str:
        sec = "_cabecera"
        for mn, my, nombre in marcas:
            if (mn, my) <= (n, y):
                sec = nombre
        return sec

    enlaces: dict[str, list[dict]] = {}
    for n, pag in enumerate(doc):
        for l in pag.get_links():
            uri = l.get("uri", "")
            if not uri or "administracion.ulpgc.es/?x=" in uri or uri.startswith(("mailto:", "tel:")):
                continue
            sec = seccion_en(n, l["from"].y0)
            if sec.startswith("_"):
                continue
            texto = nfc(" ".join(pag.get_textbox(l["from"]).split()))
            lista = enlaces.setdefault(sec, [])
            if uri not in [e["url"] for e in lista]:
                lista.append({"texto": texto, "url": uri})

    nombre = " ".join(titulo)
    cabecera = secciones.pop("_cabecera")
    sia = next((re.sub(r"\D", "", c) for c in cabecera if c.startswith("Código SIA")), None)
    # La cabecera también trae el título en la miga de pan de la página 1: se quita
    resto = " ".join(c for c in cabecera if not c.startswith("Código SIA"))
    resto = " ".join(resto.split()).replace(" ".join(nombre.split()), "").strip()
    if resto == "Iniciar tramitación electrónica":
        resto = "Abierta (Iniciar tramitación electrónica)"
    presentacion = resto or None
    fecha = doc.metadata.get("creationDate", "")
    impreso = datetime.strptime(fecha[2:16], "%Y%m%d%H%M%S").date().isoformat() if fecha else None
    return {
        "nombre": nombre,
        "codigo_sia": sia,
        "url_catalogo": url,
        "presentacion": presentacion,
        "secciones": {k: "\n".join(v) for k, v in secciones.items()},
        "enlaces": enlaces,
        "fichero": nfc(pdf.name),
        "impreso": impreso,
    }


def main() -> None:
    fichas = [extraer(p) for p in sorted(CARPETA.glob("*.pdf"))]
    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in fichas), encoding="utf-8")
    for f in fichas:
        print(f"{f['codigo_sia'] or '-':>8}  {len(f['secciones'])} secc.  {f['nombre'][:90]}")
    print(f"\n{len(fichas)} fichas -> {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
