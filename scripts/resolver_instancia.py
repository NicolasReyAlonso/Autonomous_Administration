#!/usr/bin/env python3
"""Resuelve instancias: busca la normativa aplicable en la fecha de presentación y Gemma 4
redacta la resolución (ver rag/resolver.py).

Necesita el servidor de LM Studio con Gemma 4 E4B cargado con un contexto de 24576 o más
(el prompt ocupa unas 13.000 fichas; con el contexto por defecto, 8192, no cabe).

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/resolver_instancia.py data/instancias/compensatoria/comp-001.json
    python scripts/resolver_instancia.py data/instancias/cambio_grupo/      # todas las de una carpeta
    python scripts/resolver_instancia.py comp-001.json --sin-pensar         # ~3 veces más rápido
    python scripts/resolver_instancia.py comp-001.json --contexto           # muestra el prompt
    python scripts/resolver_instancia.py comp-001.json --solo-busqueda      # sin modelo: qué normativa recibe
    python scripts/resolver_instancia.py comp-001.json --fecha-resolucion 2026-12-22

Si la instancia trae `gold`, se compara la decisión y los requisitos incumplidos. Para
evaluar todas las instancias y guardar los resultados: scripts/evaluar_instancias.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import Buscador, fecha_iso  # noqa: E402
from rag.resolver import (MODELO_LLM, URL_POR_DEFECTO, Resolucion, Resolver, buscar_para_caso,  # noqa: E402
                          cargar_caso, construir_mensajes, fecha_de_resolucion, rutas_casos)
from rag.responder import describir_fragmento  # noqa: E402


def imprimir_busqueda(resultados) -> None:
    print("Normativa enviada al modelo:")
    anterior = None
    for n, r in enumerate(resultados, 1):
        f = r.fragmento
        if f["doc_id"] != anterior:
            print(f"  · {f['titulo_doc'][:100]}")
            anterior = f["doc_id"]
        print(f"      [{n}] {(f['encabezado'] or '')[:70]}")


def imprimir_resolucion(caso: dict, res: Resolucion, razonamiento: bool) -> None:
    s = res.salida
    print(f"\nDecisión: {s['decision']}   ({res.segundos} s)")
    print(f"Norma aplicable: {'; '.join(s['norma_aplicable']['normas'])}\n  {s['norma_aplicable']['motivo']}")
    print("Requisitos:")
    for q in s["requisitos"]:
        citas = "".join(f"[{n}]" for n in q.get("fragmentos", []))
        print(f"  {'✓' if q['cumple'] else '✗'} {q['requisito']} — {q['norma']} {citas}\n      {q['motivo']}")
    print(f"Órgano: {s['organo']}\nRecurso: {s['recurso']}\n")
    print("\n".join(s["resolucion"]))
    if razonamiento and res.razonamiento:
        print("\n--- Razonamiento del modelo ---\n" + res.razonamiento)
    gold = caso.get("gold")
    if gold:
        ok = s["decision"] == gold["decision"]
        print(f"\n{'✓' if ok else '✗'} Gold: {gold['decision']}"
              + ("" if ok else f" (el modelo: {s['decision']})"))
        fallan = [q["requisito"] for q in gold["requisitos"] if not q["cumple"]]
        if fallan:
            print(f"  Requisitos incumplidos según el gold: {'; '.join(fallan)}")
        modelo = [q["requisito"] for q in s["requisitos"] if not q["cumple"]]
        print(f"  Requisitos incumplidos según el modelo: {'; '.join(modelo) or '—'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="+", help="ficheros de instancia o carpetas")
    ap.add_argument("--url", default=URL_POR_DEFECTO, help="URL de la API compatible con OpenAI")
    ap.add_argument("--modelo", default=MODELO_LLM, help="identificador del modelo en el servidor")
    ap.add_argument("--sin-pensar", action="store_true", help="sin razonamiento previo: más rápido")
    ap.add_argument("--fecha-resolucion", type=fecha_iso, metavar="AAAA-MM-DD",
                    help="fecha que lleva la resolución; por defecto, la del gold si lo hay, si no hoy")
    ap.add_argument("--contexto", action="store_true", help="muestra el prompt completo")
    ap.add_argument("--razonamiento", action="store_true", help="muestra lo que pensó el modelo")
    ap.add_argument("--solo-busqueda", action="store_true", help="no llama al modelo: solo la normativa")
    ap.add_argument("--json", action="store_true", help="imprime la salida del modelo en JSON")
    args = ap.parse_args()

    rutas = rutas_casos(args.rutas)
    if args.solo_busqueda:
        buscador = Buscador.cargar()
    else:
        try:
            resolver = Resolver.cargar(args.url, args.modelo, pensar=not args.sin_pensar)
        except RuntimeError as e:
            sys.exit(f"Error: {e}")
        buscador = resolver.buscador
        print(f"Modelo: {resolver.llm.modelo} ({resolver.llm.url})", file=sys.stderr)

    for ruta in rutas:
        caso = cargar_caso(ruta)
        fecha_res = args.fecha_resolucion or fecha_de_resolucion(caso)
        print(f"\n{'=' * 100}\n{caso.get('id', ruta.name)} · {caso['instancia'].get('asunto', '')} · "
              f"presentada el {caso['instancia']['fecha_presentacion']}\n{'=' * 100}")
        if args.solo_busqueda or args.contexto:
            resultados = buscar_para_caso(buscador, caso)
            imprimir_busqueda(resultados)
            if args.contexto:
                mensajes = construir_mensajes(caso, resultados, fecha_res or caso["instancia"]["fecha_presentacion"])
                print("\n--- Prompt ---\n" + mensajes[-1]["content"])
            if args.solo_busqueda:
                continue
        print("(buscando y resolviendo…)", file=sys.stderr)
        try:
            res = resolver.resolver(caso, fecha_res)
        except (RuntimeError, ValueError) as e:
            print(f"Error: {e}")
            continue
        if args.json:
            print(json.dumps(res.salida, ensure_ascii=False, indent=2))
        else:
            imprimir_resolucion(caso, res, args.razonamiento)


if __name__ == "__main__":
    main()
