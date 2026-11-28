#!/usr/bin/env python3
"""Convierte las instancias sintéticas en ejemplos de entrenamiento con el prompt del resolutor.

Para cada caso de data/sinteticas/instancias.jsonl hace la misma búsqueda (con la fecha de
presentación) y construye el mismo prompt que rag/resolver.py al resolver; la respuesta es el
gold en JSON, con los campos y el orden de ESQUEMA. Las citas [n] de cada requisito salen de sus
«fuentes» (documento y artículo) buscadas entre los fragmentos que recibe el modelo: si la
búsqueda no trajo ese artículo, el requisito queda sin cita, como pasaría al resolver.

Uso (desde la raíz del proyecto, con el venv activado):
    python scripts/preparar_entrenamiento.py              # ~2 min con la GPU
    python scripts/preparar_entrenamiento.py --fichas     # cuenta además las fichas (tokens) con el tokenizador de Gemma

Salida: data/sinteticas/entrenamiento.jsonl y validacion.jsonl (10 %, estratificado por trámite),
una línea por ejemplo: {"id", "tramite", "rama", "decision", "messages": [system, user, assistant]}.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import RAIZ, Buscador, Resultado  # noqa: E402
from rag.resolver import buscar_para_caso, construir_mensajes, fecha_de_resolucion  # noqa: E402

CARPETA = RAIZ / "data" / "sinteticas"
MODELO_TOKENIZADOR = "google/gemma-4-E4B-it"


def citas(fuentes: list[dict], resultados: list[Resultado]) -> list[int]:
    nums: list[int] = []
    for f in fuentes:
        coinciden = [n for n, r in enumerate(resultados, 1)
                     if f["documento"].lower() in r.fragmento["titulo_doc"].lower()
                     and (not f["articulo"] or r.fragmento["numero"] == f["articulo"])]
        nums += coinciden[:2]
    return sorted(set(nums))


def objetivo(gold: dict, resultados: list[Resultado]) -> dict:
    """El gold con el esquema de la salida del resolutor (rag/resolver.py, ESQUEMA), en su orden."""
    return {
        "norma_aplicable": gold["norma_aplicable"],
        "requisitos": [{"requisito": q["requisito"], "norma": q["norma"],
                        "fragmentos": citas(q.get("fuentes", []), resultados),
                        "motivo": q["motivo"], "cumple": q["cumple"]} for q in gold["requisitos"]],
        "decision": gold["decision"],
        "organo": gold["organo"],
        "recurso": gold["recurso"],
        "resolucion": gold["resolucion"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrada", type=Path, default=CARPETA / "instancias.jsonl")
    ap.add_argument("--validacion", type=float, default=0.1, help="fracción para validación")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--fichas", action="store_true", help="cuenta las fichas con el tokenizador de Gemma 4")
    args = ap.parse_args()

    casos = [json.loads(l) for l in args.entrada.read_text(encoding="utf-8").splitlines() if l.strip()]
    buscador = Buscador.cargar()
    ejemplos, sin_cita, t = [], 0, time.time()
    for n, c in enumerate(casos, 1):
        resultados = buscar_para_caso(buscador, c)
        mensajes = construir_mensajes(c, resultados, fecha_de_resolucion(c))
        obj = objetivo(c["gold"], resultados)
        sin_cita += sum(not q["fragmentos"] for q in obj["requisitos"])
        ejemplos.append({"id": c["id"], "tramite": c["tramite"], "rama": c["rama"], "decision": c["gold"]["decision"],
                         "messages": mensajes + [{"role": "assistant", "content": json.dumps(obj, ensure_ascii=False)}]})
        if n % 100 == 0:
            print(f"  {n}/{len(casos)}  ({time.time() - t:.0f} s)", flush=True)

    rng = random.Random(args.semilla)
    validacion = set()
    for tramite in sorted({e["tramite"] for e in ejemplos}):
        ids = [e["id"] for e in ejemplos if e["tramite"] == tramite]
        validacion |= set(rng.sample(ids, max(1, round(args.validacion * len(ids)))))
    for nombre, sub in (("entrenamiento", [e for e in ejemplos if e["id"] not in validacion]),
                        ("validacion", [e for e in ejemplos if e["id"] in validacion])):
        ruta = CARPETA / f"{nombre}.jsonl"
        ruta.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in sub), encoding="utf-8")
        print(f"{len(sub):4} ejemplos en {ruta.relative_to(RAIZ)}")
    total_req = sum(len(json.loads(e["messages"][-1]["content"])["requisitos"]) for e in ejemplos)
    print(f"Requisitos sin cita (la búsqueda no trajo su artículo): {sin_cita}/{total_req}")

    caracteres = [(sum(len(m["content"]) for m in e["messages"][:-1]), len(e["messages"][-1]["content"])) for e in ejemplos]
    print(f"Caracteres: prompt mediana {statistics.median(p for p, _ in caracteres):.0f} · máx {max(p for p, _ in caracteres)}; "
          f"respuesta mediana {statistics.median(r for _, r in caracteres):.0f} · máx {max(r for _, r in caracteres)}")
    if args.fichas:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODELO_TOKENIZADOR)
        prompts, respuestas = [], []
        for e in ejemplos:
            completo = tok.apply_chat_template(e["messages"], tokenize=True, return_dict=False)
            solo_prompt = tok.apply_chat_template(e["messages"][:-1], tokenize=True, add_generation_prompt=True,
                                                  return_dict=False)
            prompts.append(len(solo_prompt))
            respuestas.append(len(completo) - len(solo_prompt))
        print(f"Fichas: prompt mediana {statistics.median(prompts):.0f} · máx {max(prompts)}; respuesta mediana "
              f"{statistics.median(respuestas):.0f} · máx {max(respuestas)}; total por época {sum(prompts) + sum(respuestas):,}")


if __name__ == "__main__":
    main()
