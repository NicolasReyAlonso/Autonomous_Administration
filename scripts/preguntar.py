#!/usr/bin/env python3
"""Pregunta sobre la normativa de la ULPGC/EII: busca los artículos y Gemma redacta la respuesta.

Necesita el servidor de LM Studio arrancado con Gemma 4 (ver rag/responder.py).

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/preguntar.py "¿Cuántas convocatorias tengo por asignatura?"
    python scripts/preguntar.py                     # modo interactivo (línea vacía o Ctrl+D para salir)
    python scripts/preguntar.py --contexto "..."    # muestra también los fragmentos enviados al modelo
    python scripts/preguntar.py --sin-pensar "..."  # sin razonamiento previo: ~9 s en vez de ~25 s
    python scripts/preguntar.py --fecha 2027-01-15 "..."  # normativa aplicable en esa fecha (por defecto, hoy)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import fecha_iso  # noqa: E402
from rag.responder import (K_FRAGMENTOS, URL_POR_DEFECTO, MODELO_LLM,  # noqa: E402
                           Respuesta, Responder, describir_fragmento)


def imprimir_fuentes(respuesta: Respuesta) -> None:
    citadas = set(respuesta.citas())
    print("\nFuentes:")
    for n, r in enumerate(respuesta.resultados, 1):
        f = r.fragmento
        marca = "*" if n in citadas else " "
        print(f" {marca}[{n}] {describir_fragmento(f)}")
        if n in citadas:
            print(f"       {f['url']}")
    if not citadas:
        print("  (la respuesta no cita ningún fragmento)")


def preguntar(responder: Responder, pregunta: str, contexto: bool, razonamiento: bool,
              fecha: str | None = None) -> None:
    aviso = "(buscando y pensando…)" if responder.pensar else "(buscando…)"
    print(aviso, end="\r", file=sys.stderr, flush=True)
    respuesta, primero = None, True
    for trozo in responder.responder_a_trozos(pregunta, fecha):
        if isinstance(trozo, Respuesta):
            respuesta = trozo
            continue
        if primero:
            print(" " * len(aviso), end="\r", file=sys.stderr, flush=True)
            primero = False
        print(trozo, end="", flush=True)
    print()
    if contexto:
        print("\n--- Mensaje enviado al modelo ---\n" + respuesta.mensajes[-1]["content"])
    if razonamiento and respuesta.razonamiento:
        print("\n--- Razonamiento del modelo ---\n" + respuesta.razonamiento)
    imprimir_fuentes(respuesta)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pregunta", nargs="*", help="si se omite, modo interactivo")
    ap.add_argument("--k", type=int, default=K_FRAGMENTOS, help="fragmentos que se pasan al modelo")
    ap.add_argument("--url", default=URL_POR_DEFECTO, help="URL de la API compatible con OpenAI")
    ap.add_argument("--modelo", default=MODELO_LLM, help="identificador del modelo en el servidor")
    ap.add_argument("--contexto", action="store_true", help="muestra los fragmentos enviados al modelo")
    ap.add_argument("--razonamiento", action="store_true", help="muestra lo que pensó el modelo antes de responder")
    ap.add_argument("--sin-pensar", action="store_true",
                    help="desactiva el razonamiento previo: ~3 veces más rápido, quizá menos preciso")
    ap.add_argument("--fecha", type=lambda s: fecha_iso(s), default=None, metavar="AAAA-MM-DD",
                    help="fecha de la consulta (la de la solicitud): decide qué normativa se aplica; por defecto, hoy")
    args = ap.parse_args()

    try:
        responder = Responder.cargar(args.url, args.modelo, args.k, pensar=not args.sin_pensar)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
    print(f"Modelo: {responder.llm.modelo} ({responder.llm.url})\n", file=sys.stderr)

    if args.pregunta:
        preguntar(responder, " ".join(args.pregunta), args.contexto, args.razonamiento, args.fecha)
        return
    while True:
        try:
            pregunta = input("\nPregunta> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pregunta:
            break
        preguntar(responder, pregunta, args.contexto, args.razonamiento, args.fecha)


if __name__ == "__main__":
    main()
