#!/usr/bin/env python3
"""Evalúa el resolutor de instancias (rag/resolver.py) con los casos de data/instancias.

Fase 1: resuelve cada instancia y la compara automáticamente con su `gold`:
  Decisión    acierto en estimar / desestimar / requerir_subsanacion / inadmitir, en total,
              por trámite y en una matriz de confusión.
  Pares       pares de variantes (`variante_de`) con las dos decisiones bien: miden si el
              modelo distingue el único dato que cambia (fecha, nota, firma...).
  Fallo       en los casos que no se estiman, el modelo marca algún requisito como incumplido.
  Formato     del documento: tipo (resolución, requerimiento o respuesta del profesorado)
              igual al del gold, partes obligatorias, cierre con lugar, fecha y firma, sin
              números de fragmento [n], nombre y DNI del interesado, pie de recursos.
Fase 2 (opcional): un modelo juez compara con el gold la norma aplicable, la motivación de la
  decisión, el órgano y el recurso (correcto / parcial / incorrecto).

Cada resolución lleva la fecha de la del gold, para que las fechas sean comparables.
Todo se guarda en outputs/instancias/*.jsonl.

Uso (desde la raíz del proyecto, con el venv activado y LM Studio sirviendo Gemma 4 E4B con
un contexto de 24576 o más):
    python scripts/evaluar_instancias.py                       # todas (~20 min pensando)
    python scripts/evaluar_instancias.py --tramite cambio_grupo
    python scripts/evaluar_instancias.py --casos comp-001 comp-008
    python scripts/evaluar_instancias.py --sin-pensar          # ~3 veces más rápido
    python scripts/evaluar_instancias.py --juez google/gemma-4-e4b
    python scripts/evaluar_instancias.py --rejuzgar outputs/instancias/X.jsonl --juez otro-modelo
    python scripts/evaluar_instancias.py --resumen outputs/instancias/X.jsonl
    python scripts/evaluar_instancias.py --local google/gemma-4-E2B-it                 # transformers, sin LM Studio
    python scripts/evaluar_instancias.py --local google/gemma-4-E2B-it --adaptador outputs/adapters/resolver-e2b

Sin --juez no hay fase 2: en el PC (8 GB) Gemma 4 12B no carga, y con el mismo E4B de juez
tiende a darse la razón. Las métricas de la fase 1 no dependen de ningún juez.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import RAIZ  # noqa: E402
from rag.resolver import (DECISIONES, MODELO_LLM, URL_POR_DEFECTO, Resolver, cargar_caso,  # noqa: E402
                          fecha_de_resolucion, rutas_casos)
from rag.responder import RE_CITA, ClienteLLM, RespuestaCortada  # noqa: E402
from scripts.evaluar_respuestas import guardar, leer, liberar_gpu  # noqa: E402

SALIDA = RAIZ / "outputs" / "instancias"
ABREV = {"estimar": "est", "desestimar": "des", "requerir_subsanacion": "sub", "inadmitir": "ina"}
VEREDICTOS = ("correcto", "parcial", "incorrecto")
ASPECTOS = ("norma", "motivacion", "organo", "recurso")
PUNTOS = {"correcto": 1.0, "parcial": 0.5}
MAX_TOKENS_JUEZ = 2048

# --------------------------------------------------------------------------- #
# Formato del documento
# --------------------------------------------------------------------------- #
PARTES = {
    "RESOLUCIÓN": ("HECHOS", "FUNDAMENTOS DE DERECHO", "RESUELVE:"),
    "RESPUESTA": ("HECHOS", "FUNDAMENTOS DE DERECHO", "ACUERDA:"),
    "REQUERIMIENTO": ("le requiere", "diez días hábiles", "desistido"),
}


def tipo_documento(lineas: list[str]) -> str:
    primera = (lineas[0] if lineas else "").strip().upper()
    return next((t for t in PARTES if primera.startswith(t)), "otro")


def comprobar_formato(caso: dict, lineas: list[str]) -> dict[str, bool]:
    texto = "\n".join(lineas)
    tipo, esperado = tipo_documento(lineas), tipo_documento(caso["gold"]["resolucion"])
    sol = caso["instancia"]["solicitante"]
    comprobaciones = {
        "tipo": tipo == esperado,
        "partes": tipo in PARTES and all(p.lower() in texto.lower() for p in PARTES[tipo]),
        # Lugar y fecha, y después la firma y el hueco del nombre («[Nombre y apellidos…]»)
        "cierre": any(l.startswith("Las Palmas de Gran Canaria") for l in lineas)
                  and any(l.startswith("(firma") for l in lineas) and any(l.startswith("[Nombre") for l in lineas),
        "sin_citas": not RE_CITA.search(texto),
        # El requerimiento del Manual se dirige «a usted» y lleva el nombre al pie, sin DNI
        "interesado": sol["nombre"].lower() in texto.lower() and (esperado == "REQUERIMIENTO" or sol["dni"] in texto),
    }
    if esperado == "RESOLUCIÓN":
        comprobaciones["recursos"] = bool(re.search(r"recurso de (alzada|reposición)|reclamación", texto, re.I))
    elif esperado == "REQUERIMIENTO":
        comprobaciones["recursos"] = not re.search(r"recurso de alzada", texto, re.I)  # no lleva
    return comprobaciones


# --------------------------------------------------------------------------- #
# Fase 1: resolver
# --------------------------------------------------------------------------- #
def incumplidos(requisitos: list[dict]) -> list[str]:
    return [q["requisito"] for q in requisitos if not q.get("cumple", True)]


def registro_base(caso: dict, resolver: Resolver) -> dict:
    g = caso["gold"]
    return {"id": caso["id"], "tramite": caso["tramite"], "variante_de": caso.get("variante_de"),
            "fecha_presentacion": caso["instancia"]["fecha_presentacion"],
            "modelo": resolver.llm.modelo, "pensar": resolver.pensar, "presupuesto": resolver.presupuesto,
            "gold_decision": g["decision"], "gold_incumplidos": incumplidos(g["requisitos"])}


def resolver_casos(resolver: Resolver, casos: list[dict], ruta: Path) -> list[dict]:
    # Calentamiento: que la carga de los modelos no cuente en el tiempo del primer caso
    resolver.buscador.buscar("calentamiento", k=1)
    try:
        list(resolver.llm.generar([{"role": "user", "content": "Di hola."}], pensar=False, max_tokens=8))
    except RuntimeError:
        pass
    registros = []
    for n, caso in enumerate(casos, 1):
        r = registro_base(caso, resolver)
        try:
            res = resolver.resolver(caso, fecha_de_resolucion(caso))
        except (ValueError, RespuestaCortada) as e:   # salida inválida o cortada: se apunta y se sigue
            r.update(error=str(e), decision=None, acierto=False, segundos=None)
        else:
            s = res.salida
            r.update(decision=s["decision"], acierto=s["decision"] == r["gold_decision"],
                     incumplidos=incumplidos(s["requisitos"]), formato=comprobar_formato(caso, s["resolucion"]),
                     segundos=res.segundos, salida=s, razonamiento=res.razonamiento,
                     documentos=list(dict.fromkeys(x.fragmento["titulo_doc"] for x in res.resultados)),
                     fragmentos=[x.fragmento["id"] for x in res.resultados])
        registros.append(r)
        guardar(ruta, registros)
        marca = "!" if r.get("error") else ("✓" if r["acierto"] else "✗")
        print(f"  [{n:2}/{len(casos)}] {marca} {caso['id']:9} {r['gold_decision']:21} "
              f"→ {r['decision'] or 'error':21} {r['segundos'] or 0:5.1f} s", flush=True)
    return registros


# --------------------------------------------------------------------------- #
# Fase 2: juez
# --------------------------------------------------------------------------- #
SISTEMA_JUEZ = """\
Eres un jurista experto en procedimiento administrativo universitario. Comparas la resolución \
que ha preparado un asistente para una instancia con la resolución de referencia (correcta), \
y valoras cuatro aspectos:
- norma: si aplica las mismas normas que la referencia por la fecha de presentación (las \
normas generales de procedimiento que añada no restan).
- motivacion: si la decisión se apoya en los mismos requisitos que la referencia, con los \
datos correctos. Si la referencia deniega por un requisito y el asistente por otro, o estima lo \
que se deniega, es incorrecto. Si acierta el requisito decisivo pero comete errores en otros, \
es parcial.
- organo: si resuelve el mismo órgano.
- recurso: si indica el mismo recurso (o la misma vía si no hay recurso), ante el mismo órgano \
y en el mismo plazo.
Valores: correcto, parcial o incorrecto. Juzga el contenido, no el estilo. Escribe primero un \
comentario breve (dos o tres frases) con los errores que veas."""

FORMATO_JUEZ = {"type": "json_schema", "json_schema": {"name": "veredicto", "strict": True, "schema": {
    "type": "object",
    "properties": {"comentario": {"type": "string"},
                   **{a: {"type": "string", "enum": list(VEREDICTOS)} for a in ASPECTOS}},
    "required": ["comentario", *ASPECTOS],
    "additionalProperties": False,
}}}


def resumen_para_juez(datos: dict, maximo: int = 5000) -> str:
    reqs = "\n".join(f"  - {'cumple' if q['cumple'] else 'NO cumple'}: {q['requisito']} ({q['norma']}): {q['motivo']}"
                     for q in datos["requisitos"])
    texto = "\n".join(datos["resolucion"])
    if len(texto) > maximo:
        texto = texto[:maximo] + " […]"
    return (f"Decisión: {datos['decision']}\nNormas: {'; '.join(datos['norma_aplicable']['normas'])}\n"
            f"Por qué esas normas: {datos['norma_aplicable']['motivo']}\nÓrgano: {datos['organo']}\n"
            f"Recurso: {datos['recurso']}\nRequisitos:\n{reqs}\n\nTexto:\n{texto}")


def juzgar(juez: ClienteLLM, registro: dict, caso: dict) -> dict:
    usuario = (f"Instancia presentada el {caso['instancia']['fecha_presentacion']}: "
               f"{caso['instancia'].get('solicita', '')}\n\n"
               f"RESOLUCIÓN DE REFERENCIA\n{resumen_para_juez(caso['gold'])}\n\n"
               f"RESOLUCIÓN DEL ASISTENTE\n{resumen_para_juez(registro['salida'])}")
    mensajes = [{"role": "system", "content": SISTEMA_JUEZ}, {"role": "user", "content": usuario}]
    try:
        salida = juez.generar(mensajes, pensar=False, temperatura=0.0, max_tokens=MAX_TOKENS_JUEZ,
                              extra={"response_format": FORMATO_JUEZ})
        return {"juicio": json.loads("".join(t for tipo, t in salida if tipo == "respuesta"))}
    except (ValueError, RespuestaCortada) as e:
        return {"juicio": {"comentario": f"Error del juez: {e}", **{a: "error" for a in ASPECTOS}}}


# --------------------------------------------------------------------------- #
# Resumen
# --------------------------------------------------------------------------- #
def pct(a: int, b: int) -> str:
    return f"{a:2}/{b:<2} ({100 * a / b:3.0f} %)" if b else "  –"


def resumir(registros: list[dict]) -> None:
    n, r0 = len(registros), registros[0]
    modo = "pensando" if r0["pensar"] else "sin pensar"
    print(f"\n{n} instancias · resuelve {r0['modelo']} ({modo}) · juez {r0.get('juez', '—')}\n")
    validos = [r for r in registros if not r.get("error")]
    aciertos = sum(r["acierto"] for r in registros)
    print(f"  Decisión correcta                       {pct(aciertos, n)}")
    for tramite in sorted({r["tramite"] for r in registros}):
        sub = [r for r in registros if r["tramite"] == tramite]
        print(f"    {tramite:36}  {pct(sum(r['acierto'] for r in sub), len(sub))}")

    por_id = {r["id"]: r for r in registros}
    pares = [(r, por_id[r["variante_de"]]) for r in registros if r.get("variante_de") in por_id]
    if pares:
        print(f"  Pares de variantes con las dos bien      {pct(sum(a['acierto'] and b['acierto'] for a, b in pares), len(pares))}")
    no_est = [r for r in validos if r["gold_decision"] != "estimar"]
    if no_est:
        print(f"  Marca algún requisito incumplido (casos que no se estiman)  "
              f"{pct(sum(bool(r['incumplidos']) for r in no_est), len(no_est))}")
    if errores := [r for r in registros if r.get("error")]:
        print(f"  Salidas inválidas o cortadas             {pct(len(errores), n)}")
    if validos:
        print(f"  Tiempo medio                             {sum(r['segundos'] for r in validos) / len(validos):.1f} s")

        print("\n  Formato del documento:")
        claves = list(dict.fromkeys(k for r in validos for k in r["formato"]))
        for k in claves:
            con = [r for r in validos if k in r["formato"]]
            print(f"    {k:12} {pct(sum(r['formato'][k] for r in con), len(con))}")

    print("\n  Matriz de confusión (filas: gold; columnas: modelo):")
    print("    " + " " * 22 + "".join(f"{ABREV[d]:>5}" for d in DECISIONES) + "  error")
    for g in DECISIONES:
        fila = [r for r in registros if r["gold_decision"] == g]
        if fila:
            cuenta = Counter(r["decision"] for r in fila)
            print(f"    {g:22}" + "".join(f"{cuenta[d] or '·':>5}" for d in DECISIONES) + f"{cuenta[None] or '·':>7}")

    juzgados = [r for r in validos if "juicio" in r]
    if juzgados:
        print("\n  Juez (correcto = 1, parcial = 0,5):")
        for a in ASPECTOS:
            puntos = sum(PUNTOS.get(r["juicio"][a], 0.0) for r in juzgados)
            print(f"    {a:12} {100 * puntos / len(juzgados):3.0f} %")

    print("\n  Detalle (gold → modelo; F = comprobaciones de formato superadas; juez: N M O R):")
    for r in registros:
        marca = "!" if r.get("error") else ("✓" if r["acierto"] else "✗")
        f = r.get("formato") or {}
        juez = " ".join((r["juicio"][a] or "?")[0].upper() for a in ASPECTOS) if "juicio" in r else ""
        print(f"   {marca} {r['id']:9} {ABREV[r['gold_decision']]} → {ABREV.get(r['decision'], 'err')}  "
              f"F {sum(f.values())}/{len(f)}  {juez}")
        if r.get("error"):
            print(f"{'':14}{r['error'][:160]}")
            continue
        if not r["acierto"]:
            print(f"{'':14}gold incumple: {'; '.join(r['gold_incumplidos']) or '—'}")
            print(f"{'':14}modelo incumple: {'; '.join(r['incumplidos']) or '—'}")
        if fallos := [k for k, v in f.items() if not v]:
            print(f"{'':14}formato: falla {', '.join(fallos)}")
        if "juicio" in r and any(r["juicio"][a] != "correcto" for a in ASPECTOS):
            print(f"{'':14}juez: {r['juicio']['comentario'][:220]}")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="*", help="ficheros o carpetas de instancias (por defecto, todas)")
    ap.add_argument("--tramite", nargs="*", help="solo estos trámites (p. ej. cambio_grupo)")
    ap.add_argument("--casos", nargs="*", help="solo estos ids (p. ej. comp-001 fa-004)")
    ap.add_argument("--sin-pensar", action="store_true", help="sin razonamiento previo")
    ap.add_argument("--url", default=URL_POR_DEFECTO, help="URL de la API compatible con OpenAI")
    ap.add_argument("--modelo", default=MODELO_LLM, help="modelo que resuelve (por defecto Gemma 4 E4B)")
    ap.add_argument("--local", metavar="MODELO_HF", help="resolver con transformers en local (rag/local.py), sin "
                    "LM Studio; sin razonamiento previo")
    ap.add_argument("--adaptador", type=Path, help="adaptador LoRA para --local")
    ap.add_argument("--juez", help="modelo juez para la fase 2 (sin él, no hay fase 2)")
    ap.add_argument("--rejuzgar", type=Path, metavar="JSONL", help="juzga resoluciones ya guardadas (con --juez)")
    ap.add_argument("--resumen", type=Path, metavar="JSONL", help="solo muestra el resumen de un fichero")
    args = ap.parse_args()

    casos = {c["id"]: c for c in map(cargar_caso, rutas_casos(args.rutas or None)) if "gold" in c}
    if args.resumen:
        registros = leer(args.resumen)
        for r in registros:  # con las comprobaciones de formato y el gold actuales
            if r.get("salida") and r["id"] in casos:
                r["formato"] = comprobar_formato(casos[r["id"]], r["salida"]["resolucion"])
        resumir(registros)
        return
    try:
        if args.rejuzgar:
            ruta, registros = args.rejuzgar, leer(args.rejuzgar)
            if not args.juez:
                sys.exit("Error: --rejuzgar necesita --juez")
        else:
            elegidos = [c for c in casos.values()
                        if (not args.tramite or c["tramite"] in args.tramite)
                        and (not args.casos or c["id"] in args.casos)]
            if not elegidos:
                sys.exit("No hay instancias con gold que cumplan los filtros")
            if args.local:
                from rag.busqueda import Buscador
                from rag.local import ClienteLocal
                resolver = Resolver(Buscador.cargar(), ClienteLocal(args.local, args.adaptador), pensar=False)
            else:
                resolver = Resolver.cargar(args.url, args.modelo, pensar=not args.sin_pensar)
            modo = "sin-pensar" if not resolver.pensar else "pensar"
            ruta = SALIDA / f"{datetime.now():%Y%m%d-%H%M}_{resolver.llm.modelo.replace('/', '_')}_{modo}.jsonl"
            print(f"Fase 1: {resolver.llm.modelo} resuelve {len(elegidos)} instancias ({modo})")
            registros = resolver_casos(resolver, elegidos, ruta)
            del resolver
            liberar_gpu()
            if not args.juez:
                resumir(registros)
                print(f"\nResultados en {ruta.relative_to(RAIZ)}")
                return
        juez = ClienteLLM(args.url, args.juez)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")

    if juez.modelo == registros[0]["modelo"]:
        print(f"Aviso: el juez es el mismo modelo que resuelve ({juez.modelo}); tenderá a darse la razón.")
    print(f"\nFase 2: {juez.modelo} juzga las resoluciones")
    for n, r in enumerate(registros, 1):
        if r.get("error") or r["id"] not in casos:
            continue
        t = time.time()
        try:
            r.update(juzgar(juez, r, casos[r["id"]]), juez=juez.modelo)
        except RuntimeError as e:
            sys.exit(f"Error: {e}\nLas resoluciones están guardadas en {ruta}; júzgalas con --rejuzgar {ruta}")
        guardar(ruta, registros)
        print(f"  [{n:2}/{len(registros)}] {time.time() - t:5.1f} s  {r['id']}  "
              + " ".join(f"{a}={r['juicio'][a]}" for a in ASPECTOS), flush=True)

    resumir(registros)
    print(f"\nResultados en {ruta.relative_to(RAIZ) if ruta.is_relative_to(RAIZ) else ruta}")


if __name__ == "__main__":
    main()
