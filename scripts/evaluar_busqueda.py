#!/usr/bin/env python3
"""Mide la calidad de la búsqueda con el banco de preguntas data/eval/preguntas.jsonl.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/evaluar_busqueda.py --modelos BAAI/bge-m3 Qwen/Qwen3-Embedding-0.6B
    python scripts/evaluar_busqueda.py --modelos BAAI/bge-m3 --detalle   # pregunta a pregunta

Un resultado acierta si es un fragmento del documento esperado y, cuando la
pregunta indica artículos, de uno de esos artículos.

Métricas: Acierto@k = % de preguntas con un fragmento correcto entre los k primeros.
          MRR@10   = media de 1/posición del primer acierto (0 si no hay en el top 10).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import RAIZ, Buscador  # noqa: E402

PREGUNTAS = RAIZ / "data" / "eval" / "preguntas.jsonl"


def es_relevante(fragmento: dict, relevantes: list[dict]) -> bool:
    return any(fragmento["doc_id"] == r["doc_id"]
               and (not r["articulos"] or fragmento["numero"] in r["articulos"])
               for r in relevantes)


def evaluar(buscador: Buscador, preguntas: list[dict], modo: str) -> list[int | None]:
    """Posición (1-10) del primer fragmento correcto para cada pregunta, o None."""
    posiciones = []
    for q in preguntas:
        resultados = buscador.buscar(q["pregunta"], k=10, modo=modo)
        pos = next((n for n, r in enumerate(resultados, 1)
                    if es_relevante(r.fragmento, q["relevantes"])), None)
        posiciones.append(pos)
    return posiciones


def metricas(pos: list[int | None]) -> dict[str, float]:
    n = len(pos)
    m = {f"@{k}": 100 * sum(p is not None and p <= k for p in pos) / n for k in (1, 3, 5, 10)}
    m["MRR"] = sum(1 / p for p in pos if p) / n
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modelos", nargs="*", default=[])
    ap.add_argument("--detalle", action="store_true", help="muestra el resultado de cada pregunta")
    args = ap.parse_args()

    preguntas = [json.loads(l) for l in PREGUNTAS.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(preguntas)} preguntas\n")
    print(f"{'método':48} {'Acierto@1':>9} {'@3':>6} {'@5':>6} {'@10':>6} {'MRR@10':>7}")

    filas: dict[str, list] = {}
    base = Buscador.cargar(modelo=None)
    filas["BM25"] = evaluar(base, preguntas, "bm25")
    for modelo in args.modelos:
        b = Buscador.cargar(modelo)
        filas[f"denso · {modelo}"] = evaluar(b, preguntas, "denso")
        filas[f"híbrido · BM25 + {modelo}"] = evaluar(b, preguntas, "hibrido")
        del b

    for nombre, pos in filas.items():
        m = metricas(pos)
        print(f"{nombre[:48]:48} {m['@1']:8.0f}% {m['@3']:5.0f}% {m['@5']:5.0f}% "
              f"{m['@10']:5.0f}% {m['MRR']:7.3f}")

    if args.detalle:
        nombres = list(filas)
        print("\nPosición del primer acierto por pregunta (– = no está en el top 10):")
        print("  " + " | ".join(f"{i}" for i in range(len(nombres))) + "   pregunta")
        for i, q in enumerate(preguntas):
            celdas = [str(filas[n][i] or "–").rjust(2) for n in nombres]
            print("  " + " | ".join(celdas) + f"   {q['pregunta'][:75]}")
        for i, n in enumerate(nombres):
            print(f"  [{i}] {n}")


if __name__ == "__main__":
    main()
