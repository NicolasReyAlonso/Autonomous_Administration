#!/usr/bin/env python3
"""Mide la calidad de las respuestas del RAG (búsqueda + Gemma) con data/eval/preguntas.jsonl.

Funciona en dos fases para que LM Studio cambie de modelo una sola vez (solo mantiene uno
cargado y cada cambio cuesta ~25 s):
  1. El modelo que responde (Gemma 4 E4B) contesta todas las preguntas.
  2. Un modelo juez (por defecto Gemma 4 12B si está disponible) compara cada respuesta con
     el texto de los artículos correctos y da un veredicto: correcta / parcial /
     incorrecta / sin_respuesta, con el motivo.

Todo se guarda en outputs/evaluaciones/*.jsonl, para revisarlo a mano y para comparar
con el modelo después del entrenamiento LoRA.

Uso (desde la raíz del proyecto, con el venv activado y LM Studio sirviendo):
    python scripts/evaluar_respuestas.py                       # las 31 preguntas (~30 min)
    python scripts/evaluar_respuestas.py --sin-pensar          # respuestas sin razonamiento previo
    python scripts/evaluar_respuestas.py --preguntas 0 5 15    # solo algunas
    python scripts/evaluar_respuestas.py --rejuzgar outputs/evaluaciones/X.jsonl --juez otro-modelo
    python scripts/evaluar_respuestas.py --resumen outputs/evaluaciones/X.jsonl

Métricas:
  Búsqueda     % de preguntas con algún fragmento correcto entre los k que recibe el modelo.
  Cita         % de respuestas que citan algún fragmento correcto.
  Puntuación   (correctas + 0,5 · parciales) / preguntas, según el juez. Se da también por
               separado según la búsqueda encontrara o no el fragmento correcto, para
               distinguir los fallos de búsqueda de los de generación.

El juez también es un modelo pequeño: sus veredictos son orientativos. Conviene revisar a
mano los que no salen 'correcta' (el resumen muestra el motivo de cada uno).
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import RAIZ, cargar_fragmentos  # noqa: E402
from rag.responder import (K_FRAGMENTOS, MODELO_LLM, RE_CITA, URL_POR_DEFECTO,  # noqa: E402
                           ClienteLLM, Responder, describir_fragmento)
from scripts.evaluar_busqueda import PREGUNTAS, es_relevante  # noqa: E402

SALIDA = RAIZ / "outputs" / "evaluaciones"
PREFERENCIAS_JUEZ = ("gemma-4-12b", "gemma-4")
MAX_REFERENCIA = 12_000  # caracteres (~3500 tokens): LM Studio carga el modelo con 8192 de contexto
PUNTOS = {"correcta": 1.0, "parcial": 0.5}
SIMBOLOS = {"correcta": "✓", "parcial": "~", "incorrecta": "✗", "sin_respuesta": "∅", "error": "!"}

SISTEMA_JUEZ = """\
Eres un evaluador experto en normativa universitaria. Recibes la pregunta de un estudiante, \
el texto de referencia (los artículos de la normativa que contienen la respuesta), una nota \
del evaluador sobre de dónde sale la respuesta y la respuesta de un asistente. Decide si la \
respuesta es correcta según la referencia.

Veredictos:
- correcta: responde a la pregunta y lo esencial (cifras, plazos, requisitos, órganos, \
procedimiento) coincide con la referencia. Puede añadir información de otras normas mientras \
no contradiga la referencia.
- parcial: va bien encaminada, pero le falta algo esencial de la referencia o mezcla lo \
correcto con algún dato secundario erróneo.
- incorrecta: afirma algo erróneo como dato principal, contradice la referencia o se inventa \
información.
- sin_respuesta: el asistente dice que no ha encontrado la información o no responde a la \
pregunta. Usa este veredicto aunque la referencia sí contenga la respuesta: "no lo sé" no es \
lo mismo que responder algo falso, y se cuenta aparte.

Juzga solo el contenido, no el estilo ni la longitud. Explica el motivo en una o dos frases \
antes de dar el veredicto."""

FORMATO_JUEZ = {"type": "json_schema", "json_schema": {"name": "veredicto", "strict": True, "schema": {
    "type": "object",
    "properties": {"motivo": {"type": "string"},
                   "veredicto": {"type": "string", "enum": ["correcta", "parcial", "incorrecta", "sin_respuesta"]}},
    "required": ["motivo", "veredicto"],
    "additionalProperties": False,
}}}


def leer(ruta: Path) -> list[dict]:
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def guardar(ruta: Path, registros: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registros), encoding="utf-8")


def liberar_gpu() -> None:
    """Suelta la memoria del modelo de embeddings para que LM Studio tenga más sitio para el juez."""
    gc.collect()
    if "torch" in sys.modules:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


# --------------------------------------------------------------------------- #
# Fase 1: responder
# --------------------------------------------------------------------------- #
def responder_preguntas(responder: Responder, preguntas: list[dict], indices: list[int],
                        ruta: Path) -> list[dict]:
    # Calentamiento: que la carga de los modelos (embeddings y, en LM Studio, el cambio de
    # modelo, ~25 s) no cuente en el tiempo de la primera pregunta
    responder.preparar("calentamiento")
    try:
        list(responder.llm.generar([{"role": "user", "content": "Di hola."}], pensar=False, max_tokens=8))
    except RuntimeError:
        pass  # si se corta por max_tokens, da igual: el modelo ya está cargado
    registros = []
    for n, i in enumerate(indices, 1):
        q = preguntas[i]
        t = time.time()
        r = responder.responder(q["pregunta"])
        segundos = time.time() - t
        correctas = [p for p, res in enumerate(r.resultados, 1) if es_relevante(res.fragmento, q["relevantes"])]
        registros.append({
            "indice": i, "pregunta": q["pregunta"], "nota": q["nota"], "relevantes": q["relevantes"],
            "modelo": responder.llm.modelo, "pensar": responder.pensar, "k": responder.k,
            "respuesta": r.texto, "razonamiento": r.razonamiento, "segundos": round(segundos, 1),
            "fragmentos": [res.fragmento["id"] for res in r.resultados],
            "posiciones_correctas": correctas,  # posiciones (1..k) de los fragmentos correctos enviados
            "citas": r.citas(),
            "cita_correcta": any(c in correctas for c in r.citas()),
        })
        guardar(ruta, registros)
        print(f"  [{n:2}/{len(indices)}] {segundos:5.1f} s  {q['pregunta'][:80]}", flush=True)
    return registros


# --------------------------------------------------------------------------- #
# Fase 2: juzgar
# --------------------------------------------------------------------------- #
def referencia(registro: dict, fragmentos: list[dict]) -> str:
    """Texto de los fragmentos correctos; primero los que recibió el modelo, por si hay que recortar."""
    enviados = {fid: p for p, fid in enumerate(registro["fragmentos"])}
    correctos = sorted((f for f in fragmentos if es_relevante(f, registro["relevantes"])),
                       key=lambda f: enviados.get(f["id"], len(enviados)))
    bloques, total = [], 0
    for f in correctos:
        bloque = f"{describir_fragmento(f)}\n{f['texto'].strip()}"
        if total + len(bloque) > MAX_REFERENCIA:
            bloques.append("[... referencia recortada ...]")
            break
        bloques.append(bloque)
        total += len(bloque)
    return "\n\n".join(bloques)


def juzgar(juez: ClienteLLM, registro: dict, fragmentos: list[dict]) -> dict:
    respuesta = RE_CITA.sub("", registro["respuesta"]).strip()  # los [n] no le dicen nada al juez
    usuario = (f"Pregunta del estudiante:\n{registro['pregunta']}\n\n"
               f"Nota del evaluador:\n{registro['nota']}\n\n"
               f"Texto de referencia:\n{referencia(registro, fragmentos)}\n\n"
               f"Respuesta del asistente:\n{respuesta}")
    mensajes = [{"role": "system", "content": SISTEMA_JUEZ}, {"role": "user", "content": usuario}]
    try:
        texto = "".join(t for tipo, t in juez.generar(mensajes, pensar=False, temperatura=0.0, max_tokens=600,
                                                      extra={"response_format": FORMATO_JUEZ})
                        if tipo == "respuesta")
        return json.loads(texto)
    except (ValueError, RuntimeError) as e:
        return {"motivo": f"Error del juez: {e}", "veredicto": "error"}


# --------------------------------------------------------------------------- #
# Resumen
# --------------------------------------------------------------------------- #
def puntuacion(registros: list[dict]) -> float:
    return 100 * sum(PUNTOS.get(r.get("veredicto"), 0.0) for r in registros) / len(registros)


def resumir(registros: list[dict]) -> None:
    n, r0 = len(registros), registros[0]
    modo = "pensando" if r0["pensar"] else "sin pensar"
    print(f"\n{n} preguntas · responde {r0['modelo']} ({modo}, k={r0['k']}) · juez {r0.get('juez', '—')}\n")

    busqueda = sum(bool(r["posiciones_correctas"]) for r in registros)
    cita = sum(r["cita_correcta"] for r in registros)
    print(f"  Búsqueda: fragmento correcto entre los {r0['k']} enviados   {busqueda:2}/{n}  ({100 * busqueda / n:.0f} %)")
    print(f"  La respuesta cita algún fragmento correcto       {cita:2}/{n}  ({100 * cita / n:.0f} %)")
    print(f"  Tiempo medio por respuesta                       {sum(r['segundos'] for r in registros) / n:.1f} s")

    juzgados = [r for r in registros if "veredicto" in r]
    if juzgados:
        cuenta = Counter(r["veredicto"] for r in juzgados)
        print("\n  Veredictos del juez:")
        for v, s in SIMBOLOS.items():
            if cuenta[v]:
                print(f"    {s} {v:14} {cuenta[v]:2}  ({100 * cuenta[v] / len(juzgados):.0f} %)")
        print(f"\n  Puntuación (correcta = 1, parcial = 0,5)         {puntuacion(juzgados):.0f} %")
        con = [r for r in juzgados if r["posiciones_correctas"]]
        sin = [r for r in juzgados if not r["posiciones_correctas"]]
        if con:
            print(f"    con el fragmento correcto en el contexto     {puntuacion(con):.0f} %  ({len(con)} preguntas)")
        if sin:
            print(f"    sin él (fallo de la búsqueda)                {puntuacion(sin):.0f} %  ({len(sin)} preguntas)")

    print("\n  Detalle (B = posición del fragmento correcto en el contexto, C = lo cita):")
    for r in registros:
        s = SIMBOLOS.get(r.get("veredicto"), " ")
        pos = ",".join(map(str, r["posiciones_correctas"])) or "–"
        print(f"   {s} {r['indice']:2}  B {pos:5} C {'sí' if r['cita_correcta'] else 'no'}  "
              f"{r['segundos']:5.1f} s  {r['pregunta'][:70]}")
        if r.get("veredicto") not in (None, "correcta"):
            print(f"{'':12}→ {r['motivo']}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preguntas", type=int, nargs="*", help="índices (desde 0) de las preguntas a evaluar")
    ap.add_argument("--k", type=int, default=K_FRAGMENTOS, help="fragmentos que se pasan al modelo")
    ap.add_argument("--sin-pensar", action="store_true", help="respuestas sin razonamiento previo")
    ap.add_argument("--url", default=URL_POR_DEFECTO, help="URL de la API compatible con OpenAI")
    ap.add_argument("--modelo", default=MODELO_LLM, help="modelo que responde (por defecto Gemma 4 E4B)")
    ap.add_argument("--juez", help="modelo juez (por defecto Gemma 4 12B, o el Gemma 4 que haya)")
    ap.add_argument("--rejuzgar", type=Path, metavar="JSONL", help="vuelve a juzgar respuestas ya guardadas")
    ap.add_argument("--resumen", type=Path, metavar="JSONL", help="solo muestra el resumen de un fichero")
    args = ap.parse_args()

    if args.resumen:
        resumir(leer(args.resumen))
        return

    try:
        if args.rejuzgar:
            ruta, registros = args.rejuzgar, leer(args.rejuzgar)
        else:
            preguntas = leer(PREGUNTAS)
            indices = args.preguntas if args.preguntas is not None else list(range(len(preguntas)))
            responder = Responder.cargar(args.url, args.modelo, args.k, pensar=not args.sin_pensar)
            modo = "sin-pensar" if args.sin_pensar else "pensar"
            ruta = SALIDA / f"{datetime.now():%Y%m%d-%H%M}_{responder.llm.modelo.replace('/', '_')}_{modo}_k{args.k}.jsonl"
            print(f"Fase 1: {responder.llm.modelo} responde {len(indices)} preguntas ({modo})")
            registros = responder_preguntas(responder, preguntas, indices, ruta)
            del responder
            liberar_gpu()

        juez = ClienteLLM(args.url, args.juez, preferencias=PREFERENCIAS_JUEZ)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
    if juez.modelo == registros[0]["modelo"]:
        print(f"Aviso: el juez es el mismo modelo que responde ({juez.modelo}); tenderá a darse la razón.")
    print(f"\nFase 2: {juez.modelo} juzga las respuestas")
    fragmentos = cargar_fragmentos()
    for n, r in enumerate(registros, 1):
        t = time.time()
        r.update(juzgar(juez, r, fragmentos), juez=juez.modelo)
        guardar(ruta, registros)
        print(f"  [{n:2}/{len(registros)}] {time.time() - t:5.1f} s  {SIMBOLOS[r['veredicto']]} {r['pregunta'][:80]}",
              flush=True)

    resumir(registros)
    print(f"\nResultados en {ruta.relative_to(RAIZ) if ruta.is_relative_to(RAIZ) else ruta}")


if __name__ == "__main__":
    main()
