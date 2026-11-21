#!/usr/bin/env python3
"""Construye los índices de búsqueda a partir de data/processed/chunks.jsonl.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/indexar_normativa.py                       # BM25 + modelo por defecto
    python scripts/indexar_normativa.py --modelos BAAI/bge-m3 intfloat/multilingual-e5-base
    python scripts/indexar_normativa.py --solo-bm25

Los modelos se descargan de Hugging Face la primera vez (se guardan en
~/.cache/huggingface). Usa la GPU disponible: CUDA en el PC, MPS en el Mac.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import (MODELO_POR_DEFECTO, cargar_fragmentos, construir_bm25,  # noqa: E402
                          construir_denso, dispositivo)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modelos", nargs="+", default=[MODELO_POR_DEFECTO])
    ap.add_argument("--solo-bm25", action="store_true")
    ap.add_argument("--lote", type=int, default=16, help="tamaño de lote al codificar")
    args = ap.parse_args()

    fragmentos = cargar_fragmentos()
    print(f"{len(fragmentos)} fragmentos · dispositivo: {dispositivo()}")

    t = time.time()
    carpeta = construir_bm25(fragmentos)
    print(f"BM25 listo en {time.time() - t:.1f} s -> {carpeta}")
    if args.solo_bm25:
        return

    for modelo in args.modelos:
        t = time.time()
        print(f"\nCodificando con {modelo} ...")
        carpeta = construir_denso(fragmentos, modelo, lote=args.lote)
        print(f"{modelo} listo en {time.time() - t:.0f} s -> {carpeta}")


if __name__ == "__main__":
    main()
