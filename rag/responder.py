"""Respuesta a preguntas sobre la normativa: búsqueda híbrida + generación con Gemma 4.

El modelo de lenguaje se usa a través de un servidor con API compatible con OpenAI:
  - LM Studio (PC y Mac): pestaña Developer -> Start Server, o `lms server start`.
    Por defecto escucha en http://localhost:1234/v1 y carga el modelo al primer uso.
  - También vale `mlx_lm.server` (Mac), `llama-server` (llama.cpp), vLLM, Ollama...

Configuración por variables de entorno (o argumentos de Responder / scripts/preguntar.py):
  RAG_LLM_URL      URL base de la API          (por defecto http://localhost:1234/v1)
  RAG_LLM_MODELO   identificador del modelo    (por defecto el primero cuyo nombre
                                                contenga "gemma-4-e4b", luego "gemma")

Uso:
    from rag.responder import Responder
    r = Responder.cargar()
    respuesta = r.responder("¿Cuántas convocatorias tengo por asignatura?")
    print(respuesta.texto)
    for f in respuesta.fuentes():
        print(f.fragmento["titulo_doc"], f.fragmento["encabezado"])
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import requests

from rag.busqueda import Buscador, Resultado, fecha_iso

URL_POR_DEFECTO = os.environ.get("RAG_LLM_URL", "http://localhost:1234/v1")
MODELO_LLM = os.environ.get("RAG_LLM_MODELO")
PREFERENCIAS_MODELO = ("gemma-4-e4b", "gemma-4", "gemma")

K_FRAGMENTOS = 5     # fragmentos que se pasan al modelo (Acierto@5 de la búsqueda: ~84-90 %)
TEMPERATURA = 0.2    # baja: queremos que se ciña al texto, no creatividad
# Incluye los tokens de razonamiento: con el modo "pensar" Gemma 4 E4B gasta ~850 antes
# de responder, y con 1024 las respuestas salían cortadas.
MAX_TOKENS = 4096

SISTEMA = """\
Eres un asistente que resuelve dudas sobre la normativa de la Universidad de Las Palmas \
de Gran Canaria (ULPGC) y de su Escuela de Ingeniería Informática (EII).

Reglas:
- Responde solo con la información de los fragmentos de normativa que se te dan. No uses \
conocimientos propios ni inventes cifras, plazos o requisitos.
- Cita cada afirmación con el número del fragmento entre corchetes, por ejemplo [2]. \
Si una afirmación sale de varios fragmentos, cítalos todos: [1][3].
- Si los fragmentos no contienen la respuesta, dilo claramente ("No he encontrado esto \
en la normativa consultada") y no respondas de memoria.
- Si los fragmentos se contradicen o la respuesta depende de la situación (titulación, \
tipo de estudiante, convocatoria...), explica cada caso.
- La consulta tiene una fecha y los fragmentos son de la normativa que se aplica en esa \
fecha. Si un fragmento dice desde o hasta cuándo se aplica, menciónalo cuando importe.
- Responde en español, de forma breve y directa: primero la respuesta y después, si los \
hay, los matices importantes (excepciones, plazos, requisitos)."""

RE_CITA = re.compile(r"\[(\d+)\]")


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def describir_fragmento(f: dict) -> str:
    """'Reglamento X · Capítulo II > Artículo 4. Requisitos (pág. 3)'."""
    ruta = list(f["ruta"])
    if f["encabezado"] and (not ruta or ruta[-1] != f["encabezado"]):
        ruta.append(f["encabezado"])
    texto = " · ".join([f["titulo_doc"], " > ".join(ruta)] if ruta else [f["titulo_doc"]])
    if f["partes"] > 1:
        texto += f" (parte {f['parte']} de {f['partes']})"
    if f["paginas"]:
        p = f["paginas"]
        texto += f" (pág. {p[0]})" if len(p) == 1 else f" (págs. {p[0]}-{p[-1]})"
    desde, hasta = f.get("vigente_desde"), f.get("vigente_hasta")
    if desde or hasta:
        texto += " [se aplica" + (f" desde el {desde}" if desde else "") + \
                 (f" hasta el {hasta}" if hasta else "") + "]"
    return texto


def construir_mensajes(pregunta: str, resultados: list[Resultado],
                       fecha: str | date | None = None) -> list[dict]:
    contexto = "\n\n".join(f"[{n}] {describir_fragmento(r.fragmento)}\n{r.fragmento['texto'].strip()}"
                           for n, r in enumerate(resultados, 1))
    usuario = (f"Fragmentos de normativa:\n\n{contexto}\n\n"
               f"Fecha de la consulta: {fecha_iso(fecha)}\n\nPregunta: {pregunta}")
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]


# --------------------------------------------------------------------------- #
# Cliente del modelo de lenguaje (API compatible con OpenAI)
# --------------------------------------------------------------------------- #
class RespuestaCortada(RuntimeError):
    """El modelo llegó a max_tokens antes de terminar."""


class ClienteLLM:
    def __init__(self, url: str = URL_POR_DEFECTO, modelo: str | None = MODELO_LLM, timeout: int = 600,
                 preferencias: tuple[str, ...] = PREFERENCIAS_MODELO):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.modelo = modelo or self.elegir_modelo(preferencias)

    def modelos(self) -> list[str]:
        try:
            r = requests.get(f"{self.url}/models", timeout=5)
        except requests.ConnectionError:
            raise RuntimeError(
                f"No hay ningún servidor de modelos en {self.url}. Abre LM Studio y arranca el "
                "servidor (Developer -> Start Server, o `lms server start`).") from None
        r.raise_for_status()
        return [m["id"] for m in r.json()["data"]]

    def elegir_modelo(self, preferencias: tuple[str, ...] = PREFERENCIAS_MODELO) -> str:
        """El primer modelo del servidor cuyo nombre contenga la primera preferencia posible."""
        ids = [i for i in self.modelos() if "embed" not in i.lower()]
        for preferido in preferencias:
            for i in ids:
                if preferido in i.lower():
                    return i
        if not ids:
            raise RuntimeError(f"El servidor {self.url} no ofrece ningún modelo de chat")
        return ids[0]

    def generar(self, mensajes: list[dict], pensar: bool = True, temperatura: float = TEMPERATURA,
                max_tokens: int = MAX_TOKENS, extra: dict | None = None) -> Iterator[tuple[str, str]]:
        """Devuelve la salida a trozos según la genera el modelo, como pares (tipo, texto)
        con tipo 'razonamiento' o 'respuesta'.

        pensar=False desactiva el razonamiento previo (reasoning_effort="none" en LM Studio):
        ~3 veces más rápido. pensar=True deja lo que tenga configurado el servidor.
        extra: parámetros adicionales de la API (p. ej. response_format).
        """
        cuerpo = {"model": self.modelo, "messages": mensajes, "temperature": temperatura,
                  "max_tokens": max_tokens, "stream": True, **(extra or {})}
        if not pensar:
            cuerpo["reasoning_effort"] = "none"
        with requests.post(f"{self.url}/chat/completions", json=cuerpo, stream=True,
                           timeout=self.timeout) as r:
            if not r.ok:
                try:
                    detalle = r.json()["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    detalle = r.text[:500]
                raise RuntimeError(f"Error {r.status_code} del servidor de modelos ({self.modelo}): {detalle}")
            # Sin decode_unicode: el stream no declara charset y requests lo leería como Latin-1
            for linea in r.iter_lines():
                linea = linea.decode("utf-8")
                if not linea.startswith("data:"):
                    continue
                datos = linea.removeprefix("data:").strip()
                if datos == "[DONE]":
                    break
                opcion = (json.loads(datos).get("choices") or [{}])[0]
                delta = opcion.get("delta", {})
                # LM Studio manda el razonamiento aparte, en reasoning_content
                if delta.get("reasoning_content"):
                    yield "razonamiento", delta["reasoning_content"]
                if delta.get("content"):
                    yield "respuesta", delta["content"]
                if opcion.get("finish_reason") == "length":
                    raise RespuestaCortada(f"La respuesta superó max_tokens={max_tokens} y salió cortada")


# --------------------------------------------------------------------------- #
# Respuesta
# --------------------------------------------------------------------------- #
@dataclass
class Respuesta:
    pregunta: str
    texto: str
    resultados: list[Resultado]
    razonamiento: str = ""
    mensajes: list[dict] = field(repr=False, default_factory=list)

    def citas(self) -> list[int]:
        """Números de fragmento citados en la respuesta, en orden y sin repetir."""
        vistos = []
        for m in RE_CITA.findall(self.texto):
            n = int(m)
            if 1 <= n <= len(self.resultados) and n not in vistos:
                vistos.append(n)
        return vistos

    def fuentes(self) -> list[Resultado]:
        return [self.resultados[n - 1] for n in self.citas()]


class Responder:
    def __init__(self, buscador: Buscador, llm: ClienteLLM, k: int = K_FRAGMENTOS, pensar: bool = True):
        self.buscador = buscador
        self.llm = llm
        self.k = k
        self.pensar = pensar

    @classmethod
    def cargar(cls, url: str = URL_POR_DEFECTO, modelo_llm: str | None = MODELO_LLM,
               k: int = K_FRAGMENTOS, pensar: bool = True) -> "Responder":
        llm = ClienteLLM(url, modelo_llm)  # primero: si no hay servidor, falla antes de cargar índices
        return cls(Buscador.cargar(), llm, k, pensar)

    def preparar(self, pregunta: str, fecha: str | date | None = None) -> tuple[list[Resultado], list[dict]]:
        """fecha: la de la solicitud (hoy si es None); decide qué normativa se consulta."""
        resultados = self.buscador.buscar(pregunta, k=self.k, fecha=fecha)
        return resultados, construir_mensajes(pregunta, resultados, fecha)

    def responder_a_trozos(self, pregunta: str, fecha: str | date | None = None) -> Iterator[str | Respuesta]:
        """Va devolviendo el texto de la respuesta según se genera y, al final, el objeto Respuesta."""
        resultados, mensajes = self.preparar(pregunta, fecha)
        salida = {"razonamiento": [], "respuesta": []}
        for tipo, trozo in self.llm.generar(mensajes, pensar=self.pensar):
            salida[tipo].append(trozo)
            if tipo == "respuesta":
                yield trozo
        yield Respuesta(pregunta, "".join(salida["respuesta"]).strip(), resultados,
                        "".join(salida["razonamiento"]).strip(), mensajes)

    def responder(self, pregunta: str, fecha: str | date | None = None) -> Respuesta:
        *_, respuesta = self.responder_a_trozos(pregunta, fecha)
        return respuesta
