#!/usr/bin/env python3
"""Genera instancias sintéticas con su resolución de referencia para entrenar (paquete generador/).

Cada caso elige una rama de la decisión (qué requisito falla, si falla alguno), construye datos
coherentes con ella y escribe el gold con las reglas de la norma aplicable y las plantillas de
los casos de data/instancias/ (que quedan como conjunto de prueba: aquí no se repiten sus nombres).

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/generar_instancias.py                    # cantidades por defecto, semilla 2026
    python scripts/generar_instancias.py --n compensatoria=40 cambio_grupo=10 --semilla 7
    python scripts/generar_instancias.py --muestra gen-fa-0003   # imprime un caso

Salida: data/sinteticas/instancias.jsonl (no va a git: se regenera igual con la misma semilla).
Cada caso pasa las comprobaciones de formato de scripts/evaluar_instancias.py sobre su propio
gold, la coherencia entre la decisión y los requisitos y la concordancia de género.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generador import cambio_grupo, compensatoria, fecha_alternativa, septima  # noqa: E402
from rag.busqueda import RAIZ  # noqa: E402
from rag.resolver import INSTANCIAS, cargar_caso, rutas_casos  # noqa: E402
from scripts.evaluar_instancias import comprobar_formato  # noqa: E402

SALIDA = RAIZ / "data" / "sinteticas" / "instancias.jsonl"
MODULOS = {"compensatoria": compensatoria, "fecha_alternativa": fecha_alternativa, "septima_convocatoria": septima,
           "cambio_grupo": cambio_grupo}
POR_DEFECTO = {"compensatoria": 300, "fecha_alternativa": 120, "septima_convocatoria": 100, "cambio_grupo": 120}


def problemas(c: dict, nombres_prueba: set[str]) -> list[str]:
    g, texto = c["gold"], "\n".join(c["gold"]["resolucion"])
    fallos = []
    if not all((f := comprobar_formato(c, g["resolucion"])).values()):
        fallos.append(f"formato: {[k for k, v in f.items() if not v]}")
    incumplidos = [q for q in g["requisitos"] if not q["cumple"]]
    if (g["decision"] == "estimar") == bool(incumplidos):
        fallos.append(f"decisión {g['decision']} con {len(incumplidos)} requisitos incumplidos")
    mujer = c["instancia"]["solicitante"]["nombre"].split()[0] in compensatoria.persona.__globals__["NOMBRES_F"]
    if mujer and re.search(r"\binteresado\b|\bdon\b|\bD\. [A-ZÁÉÍÓÚ]", texto):
        fallos.append("masculino en caso femenino")
    if not mujer and re.search(r"\binteresada\b|\bdoña\b|D\.ª", texto):
        fallos.append("femenino en caso masculino")
    if c["instancia"]["solicitante"]["nombre"] in nombres_prueba:
        fallos.append("nombre de un caso de prueba")
    for seccion in ("HECHOS", "FUNDAMENTOS DE DERECHO"):
        if seccion in g["resolucion"]:
            i = g["resolucion"].index(seccion) + 1
            if not g["resolucion"][i].startswith("Primero.-"):
                fallos.append(f"{seccion} sin «Primero.-»")
    return fallos


def huella(c: dict) -> str:
    return hashlib.sha1(json.dumps([c["instancia"], c["expediente"]], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", nargs="*", default=[], metavar="TRÁMITE=N", help=f"casos por trámite (por defecto {POR_DEFECTO})")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--muestra", metavar="ID", help="imprime el caso con ese id (tras generar)")
    args = ap.parse_args()

    cuantos = dict(POR_DEFECTO)
    for par in args.n:
        tramite, n = par.split("=")
        if tramite not in MODULOS:
            sys.exit(f"Trámite desconocido: {tramite} (hay {', '.join(MODULOS)})")
        cuantos[tramite] = int(n)

    nombres_prueba = {cargar_caso(r)["instancia"]["solicitante"]["nombre"] for r in rutas_casos([INSTANCIAS])}
    rng = random.Random(args.semilla)
    casos, vistos, descartados = [], set(), Counter()
    for tramite, modulo in MODULOS.items():
        for c in modulo.generar(rng, cuantos[tramite]):
            if (h := huella(c)) in vistos:
                descartados["duplicado"] += 1
                continue
            if fallos := problemas(c, nombres_prueba):
                print(f"  ✗ {c['id']} ({c['rama']}): {'; '.join(fallos)}")
                descartados["no pasa las comprobaciones"] += 1
                continue
            vistos.add(h)
            casos.append(c)

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")

    print(f"\n{len(casos)} casos en {args.salida.relative_to(RAIZ) if args.salida.is_relative_to(RAIZ) else args.salida}"
          + (f" ({', '.join(f'{v} {k}' for k, v in descartados.items())} descartados)" if descartados else ""))
    for tramite in sorted({c["tramite"] for c in casos}):
        sub = [c for c in casos if c["tramite"] == tramite]
        decisiones = Counter(c["gold"]["decision"] for c in sub)
        print(f"  {tramite:26} {len(sub):4}   " + "  ".join(f"{d} {n}" for d, n in decisiones.most_common()))
        for rama, n in sorted(Counter(c["rama"] for c in sub).items()):
            print(f"      {rama:34} {n:4}")
    if args.muestra:
        c = next((c for c in casos if c["id"] == args.muestra), None)
        print(json.dumps(c, ensure_ascii=False, indent=1) if c else f"No hay ningún caso {args.muestra}")


if __name__ == "__main__":
    main()
