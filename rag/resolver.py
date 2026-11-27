"""Resolución de instancias: búsqueda con la fecha de presentación + Gemma 4 redacta la resolución.

Una instancia (data/instancias/<trámite>/<id>.json) trae lo que presenta el interesado
(`instancia`), lo que ya sabe la ULPGC (`expediente`) y los actos de instrucción (`informes`).
El modelo solo ve esas tres partes, la ficha del trámite en la sede
(data/plantillas/tramites.jsonl) y los fragmentos de normativa; nunca `gold` ni `notas_caso`.

Pasos:
  1. Búsqueda: varias consultas sacadas de la instancia (petición, requisitos, plazo, órgano
     y recurso, titulación), todas con fecha = fecha de presentación, combinadas por RRF.
     Se añaden siempre los artículos de la Ley 39/2015 sobre la solicitud, su subsanación y
     el recurso de alzada (ARTICULOS_FIJOS).
  2. Generación: el modelo devuelve un JSON con el esquema del `gold` (norma aplicable,
     requisitos, decisión, órgano, recurso y texto de la resolución, un párrafo por
     elemento), en ese orden, para que razone antes de decidir.

Uso:
    from rag.resolver import Resolver, cargar_caso
    r = Resolver.cargar()
    res = r.resolver(cargar_caso("data/instancias/compensatoria/comp-001.json"))
    print(res.salida["decision"])
    print("\\n".join(res.salida["resolucion"]))

El prompt ocupa unas 10.000-13.000 fichas (tokens) y la salida 2.000-4.000 más el razonamiento:
en LM Studio hay que cargar Gemma con un contexto de 24576 o más (con el de por defecto, 8192, no cabe).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

from rag.busqueda import RAIZ, RRF_K, Buscador, Resultado, fecha_iso
from rag.responder import MODELO_LLM, URL_POR_DEFECTO, ClienteLLM, describir_fragmento

TRAMITES = RAIZ / "data" / "plantillas" / "tramites.jsonl"
INSTANCIAS = RAIZ / "data" / "instancias"

K_POR_CONSULTA = 10  # resultados de cada consulta que entran en la fusión
# La selección es por documentos: para resolver hace falta la norma entera, no artículos
# sueltos (con fragmentos sueltos, el art. 4 del Reglamento 1/2026, el de los requisitos,
# quedaba por debajo del preámbulo). Los documentos se ordenan por sus mejores fragmentos;
# los cortos entran completos (sin preámbulo) y de los largos, sus mejores fragmentos.
PRESUPUESTO = 30_000          # caracteres de normativa en el prompt (~7.700 fichas)
DOCUMENTO_COMPLETO = 20_000   # hasta este tamaño un documento entra entero
MAX_DOCUMENTOS = 8
# De un documento largo: límites de fragmentos y de fragmentos con el mismo encabezado. El
# Listado de asignaturas no compensables repite «Artículo 5.c …» por titulación y la
# resolución de cambios de grupo, «ANEXO I» con listas de DNI: sin el segundo límite
# llenaban el contexto.
MAX_POR_DOCUMENTO = 6
MAX_POR_ENCABEZADO = 2
# Ley 39/2015: (artículo, parte). Se aplican a cualquier procedimiento y la búsqueda no
# siempre los trae: requisitos de la solicitud, subsanación y plazo del recurso de alzada.
ARTICULOS_FIJOS = (("66", 1), ("68", 1), ("122", 1))
SECCIONES_FICHA = ("Descripción", "Requisitos", "Plazo de presentación", "Documentación Obligatoria",
                   "Normativa aplicable")
MAX_SECCION_FICHA = 700   # caracteres por sección de la ficha
TEMPERATURA = 0.2
# Salida (~2.000-4.000 fichas) más el razonamiento previo si piensa (~1.000-3.000)
MAX_TOKENS = 8192
DECISIONES = ("estimar", "desestimar", "requerir_subsanacion", "inadmitir")
CAMPOS_ENTRADA = ("instancia", "expediente", "informes")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre")
RE_FECHA_LETRA = re.compile(r"(\d{1,2}) de (" + "|".join(MESES) + r") de (\d{4})")

SISTEMA = """\
Eres un técnico de la Administración de la Universidad de Las Palmas de Gran Canaria (ULPGC) \
que prepara la respuesta a las solicitudes (instancias) del estudiantado de la Escuela de \
Ingeniería Informática (EII). Recibes la ficha del trámite en la sede electrónica, fragmentos \
numerados de la normativa que se aplica en la fecha de presentación, la instancia, los datos que \
ya constan en el expediente del solicitante y los informes emitidos.

Cómo resolver:
1. Norma aplicable: la decide la fecha de presentación. Si un fragmento dice desde o hasta \
cuándo se aplica una norma, o qué norma rige las solicitudes de un periodo, respétalo. Di qué \
normas aplicas y por qué.
2. Comprueba en este orden y detente en lo primero que impida continuar:
   a) Plazo de presentación. Fuera de plazo -> inadmitir.
   b) Ámbito: si la norma no prevé el trámite para el solicitante (por ejemplo, excluye su \
tipo de titulación) -> inadmitir.
   c) Forma: si falta algo que exige el artículo 66 de la Ley 39/2015 (firma, hechos y razones, \
petición concreta) o un documento o motivación preceptivos -> requerir_subsanacion.
   d) Fondo: cada requisito de la norma, con los datos del expediente y los informes. Si falla \
alguno -> desestimar. Si se cumplen todos -> estimar.
3. Si lo que alega el interesado no coincide con el expediente, manda el expediente.
4. En cada requisito indica la norma y el artículo, y los números de los fragmentos [n] en los \
que te basas. No inventes requisitos, cifras, plazos, órganos ni recursos que no estén en los \
fragmentos o en la ficha.
5. Haz las cuentas con cuidado (créditos, porcentajes, convocatorias, días hábiles: no cuentan \
sábados, domingos ni festivos).
6. Resuelve el órgano al que la norma aplicable atribuye la competencia, que puede no ser el \
destinatario que escribió el interesado en la instancia. El recurso y su plazo también son los \
de la norma aplicable.

Decisiones: estimar (se concede lo pedido); desestimar (se estudia el fondo y se deniega); \
requerir_subsanacion (se pide al interesado que complete la solicitud antes de resolver); \
inadmitir (no se entra en el fondo).

El documento va en "resolucion", un párrafo o línea por elemento, según el Manual de \
normalización de documentos administrativos de la ULPGC, con las referencias a la Ley 39/2015:
- Resolución: título en mayúsculas «RESOLUCIÓN DE <fecha> DE(L) <ÓRGANO> POR LA QUE SE …»; \
«Vista la instancia presentada <medio> por <don/doña> <nombre>, con DNI <dni>, con fecha <fecha>, \
mediante la que solicita …, resultan los siguientes»; «HECHOS»; hechos numerados «Primero.- …», \
«Segundo.- …»; «FUNDAMENTOS DE DERECHO»; fundamentos numerados del mismo modo, primero la norma \
aplicable y después uno por requisito con su artículo; competencia «En virtud de lo expuesto, \
esta/este <órgano>, en uso de las competencias atribuidas por …,»; «RESUELVE:»; la decisión con \
sus efectos; pie de recursos (recurso, órgano, plazo y artículos), o, si la normativa prevé otra \
vía, esa; «Las Palmas de Gran Canaria, a <fecha>.»; antefirma con el cargo en mayúsculas; \
«(firma)»; «[Nombre y apellidos]».
- Requerimiento de subsanación (lo firma la unidad que tramita; no es una resolución ni lleva \
recursos): título «REQUERIMIENTO DE SUBSANACIÓN DE DEFECTOS EN LA SOLICITUD DE …»; «Esta \
<unidad>, en relación con la solicitud presentada por usted con fecha … en …, relativa a …, le \
requiere, de acuerdo con lo previsto en el artículo 68.1 de la Ley 39/2015, de 1 de octubre, \
del Procedimiento Administrativo Común de las Administraciones Públicas (BOE de 2 de octubre), \
para que en el plazo de diez días hábiles contados a partir del día siguiente al de la \
recepción de este requerimiento, proceda a subsanar los defectos existentes en su solicitud, \
debiendo para ello:»; los defectos numerados «1) …»; «De no producirse la subsanación en el \
plazo mencionado, se entenderá que ha desistido de su petición y se procederá a su archivo sin \
más trámite, previa resolución en tal sentido.»; «Lo que se le notifica en cumplimiento del \
artículo 40 de la mencionada Ley 39/2015.»; lugar y fecha; antefirma; «(firma y sello)»; \
«[Nombre y apellidos]»; el destinatario en mayúsculas («D.ª …» o «D. …»).
- Si quien responde es el profesorado de una asignatura y no un órgano: título «RESPUESTA DE \
<fecha> DEL PROFESORADO DE LA ASIGNATURA …», la decisión tras «ACUERDA:» y, en lugar de \
recursos, a quién puede dirigirse el estudiante si no está conforme, según la normativa.

El campo "resolucion" es obligatorio y contiene el documento completo, de principio a fin: \
siempre termina con el lugar y la fecha, la antefirma, la firma y «[Nombre y apellidos]». Es un \
documento para el interesado: no pongas en él los números de fragmento [n] (estos van solo en \
"requisitos"); cita las normas por su nombre y artículo.

Escribe en español administrativo, claro y sin adornos. Las fechas, con el día y el año en \
cifras y el mes en letra («9 de diciembre de 2026»), también en los títulos («RESOLUCIÓN DE 22 DE \
DICIEMBRE DE 2026 …»). Usa el tratamiento (don/doña) y el género que se desprendan de la \
instancia."""

ESQUEMA = {"type": "json_schema", "json_schema": {"name": "resolucion", "strict": True, "schema": {
    "type": "object",
    "properties": {
        "norma_aplicable": {
            "type": "object",
            "properties": {"normas": {"type": "array", "items": {"type": "string"}}, "motivo": {"type": "string"}},
            "required": ["normas", "motivo"], "additionalProperties": False,
        },
        "requisitos": {"type": "array", "minItems": 1, "items": {
            "type": "object",
            "properties": {"requisito": {"type": "string"}, "norma": {"type": "string"},
                           "fragmentos": {"type": "array", "items": {"type": "integer"}},
                           "motivo": {"type": "string"}, "cumple": {"type": "boolean"}},
            "required": ["requisito", "norma", "fragmentos", "motivo", "cumple"], "additionalProperties": False,
        }},
        "decision": {"type": "string", "enum": list(DECISIONES)},
        "organo": {"type": "string"},
        "recurso": {"type": "string"},
        # Sin mínimo, Gemma 4 E4B la dejaba vacía. El requerimiento más corto tiene 10 líneas
        "resolucion": {"type": "array", "minItems": 8, "items": {"type": "string", "minLength": 3}},
    },
    "required": ["norma_aplicable", "requisitos", "decision", "organo", "recurso", "resolucion"],
    "additionalProperties": False,
}}}


# --------------------------------------------------------------------------- #
# Casos y fichas
# --------------------------------------------------------------------------- #
def cargar_caso(ruta: str | Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def rutas_casos(rutas: list[str | Path] | None = None) -> list[Path]:
    """Ficheros de instancia: los indicados (ficheros o carpetas) o todos los de data/instancias."""
    salida = []
    for r in [Path(x) for x in rutas] if rutas else [INSTANCIAS]:
        salida += sorted(r.rglob("*.json")) if r.is_dir() else [r]
    return salida


@cache
def fichas() -> dict[str, dict]:
    return {f["codigo_sia"]: f for f in map(json.loads, TRAMITES.read_text(encoding="utf-8").splitlines())}


def describir_ficha(codigo_sia: str | None) -> str:
    ficha = fichas().get(codigo_sia or "")
    if not ficha:
        return "(No es un trámite de la sede electrónica: no hay ficha.)"
    lineas = [f"{ficha['nombre']} (código SIA {ficha['codigo_sia']})", f"Presentación: {ficha['presentacion']}"]
    for s in SECCIONES_FICHA:
        if texto := ficha["secciones"].get(s):
            texto = re.sub(r"\s+", " ", texto).strip()
            if len(texto) > MAX_SECCION_FICHA:
                texto = texto[:MAX_SECCION_FICHA].rsplit(" ", 1)[0] + " […]"
            lineas.append(f"{s}: {texto}")
    return "\n".join(lineas)


def entrada(caso: dict) -> dict:
    """Lo que ve el modelo de un caso: nunca gold ni notas_caso."""
    return {k: caso[k] for k in CAMPOS_ENTRADA}


def fecha_en_letra(fecha: str | date) -> str:
    d = date.fromisoformat(fecha_iso(fecha))
    return f"{d.day} de {MESES[d.month - 1]} de {d.year} ({DIAS[d.weekday()]})"


def fecha_de_resolucion(caso: dict) -> str | None:
    """Fecha de la línea «Las Palmas de Gran Canaria, a …» del gold, si la hay (para evaluar)."""
    for linea in reversed(caso.get("gold", {}).get("resolucion", [])):
        if linea.startswith("Las Palmas de Gran Canaria") and (m := RE_FECHA_LETRA.search(linea)):
            return date(int(m.group(3)), MESES.index(m.group(2)) + 1, int(m.group(1))).isoformat()
    return None


# --------------------------------------------------------------------------- #
# Búsqueda
# --------------------------------------------------------------------------- #
def consultas(caso: dict) -> list[str]:
    """Consultas para la búsqueda, sacadas solo de la entrada del caso y de la ficha del trámite.

    La «Normativa aplicable» y los «Requisitos» de la ficha nombran la norma con sus palabras:
    sin ellos, en la séptima convocatoria salían las resoluciones de tribunales «de 5.ª, 6.ª y
    7.ª convocatoria» y no el art. 10 de las Normas de Progreso y Permanencia.
    """
    ins, exp = caso["instancia"], caso.get("expediente") or {}
    asunto = ins.get("asunto") or ins.get("procedimiento", "")
    solicita = ins.get("solicita", "")
    lista = [
        f"{asunto}. {solicita}",
        f"Requisitos para {solicita or asunto}",
        f"Ámbito de aplicación: a qué estudiantes y titulaciones se aplica: {asunto}",
        f"Plazo de presentación de la solicitud: {asunto}",
        f"Órgano competente para resolver y recurso contra la resolución: {asunto}",
        f"Reclamación o incidencia si el estudiante no está conforme: {asunto}",
        f"{solicita} {exp.get('titulacion', '')}",
        ins.get("expone", "")[:500],
    ]
    ficha = fichas().get(caso.get("ficha_sia") or "")
    if ficha:
        secciones = ficha["secciones"]
        lista.append(f"{secciones.get('Normativa aplicable', '')[:300]}. {secciones.get('Requisitos', '')[:300]}")
    return [re.sub(r"\s+", " ", c).strip(" .") for c in lista if c.strip(" .")]


def articulos_fijos(buscador: Buscador) -> list[Resultado]:
    por_clave = {(f["numero"], f["parte"]): f for f in buscador.fragmentos
                 if f["fuente"] == "boe" and f["tipo"] == "articulo"}
    return [Resultado(por_clave[k], 0.0) for k in ARTICULOS_FIJOS if k in por_clave]


def documentos(buscador: Buscador) -> dict[str, list[tuple[int, dict]]]:
    """Fragmentos de cada documento con su posición en el corpus, en orden (calculado una vez)."""
    if not hasattr(buscador, "_por_documento"):
        por_doc: dict[str, list[tuple[int, dict]]] = {}
        for i, f in enumerate(buscador.fragmentos):
            por_doc.setdefault(f["doc_id"], []).append((i, f))
        buscador._por_documento = por_doc
    return buscador._por_documento


def buscar_para_caso(buscador: Buscador, caso: dict, presupuesto: int = PRESUPUESTO,
                     fijos: bool = True) -> list[Resultado]:
    """Normativa para resolver el caso: fusión RRF de sus consultas (con la fecha de
    presentación), agrupada por documentos, dentro del presupuesto; más los artículos fijos."""
    fecha = caso["instancia"]["fecha_presentacion"]
    puntos: dict[str, float] = {}
    for consulta in consultas(caso):
        for n, r in enumerate(buscador.buscar(consulta, k=K_POR_CONSULTA, fecha=fecha), 1):
            puntos[r.fragmento["id"]] = puntos.get(r.fragmento["id"], 0.0) + 1 / (RRF_K + n)
    por_doc = documentos(buscador)
    candidatos: dict[str, list[tuple[float, int, dict]]] = {}
    for doc, frs in por_doc.items():
        tocados = [(puntos[f["id"]], i, f) for i, f in frs if f["id"] in puntos]
        if tocados:
            candidatos[doc] = sorted(tocados, key=lambda t: -t[0])
    # Un documento puntúa por la suma de sus tres mejores fragmentos
    orden = sorted(candidatos, key=lambda d: -sum(p for p, _, _ in candidatos[d][:3]))

    elegidos: list[tuple[int, dict, float]] = []
    usado = n_docs = 0
    for doc in orden:
        completo = [(i, f) for i, f in por_doc[doc] if f["tipo"] != "preambulo"]
        tam = sum(len(f["texto"]) for _, f in completo)
        if tam <= DOCUMENTO_COMPLETO and usado + tam <= presupuesto:
            nuevos = [(i, f, puntos.get(f["id"], 0.0)) for i, f in completo]
        else:
            nuevos, por_enc, tam = [], {}, 0
            for p, i, f in candidatos[doc]:
                if (len(nuevos) < MAX_POR_DOCUMENTO and por_enc.get(f["encabezado"], 0) < MAX_POR_ENCABEZADO
                        and usado + tam + len(f["texto"]) <= presupuesto):
                    nuevos.append((i, f, p))
                    por_enc[f["encabezado"]] = por_enc.get(f["encabezado"], 0) + 1
                    tam += len(f["texto"])
        if nuevos:
            elegidos += sorted(nuevos, key=lambda t: t[0])  # en el orden del documento
            usado += tam
            n_docs += 1
        if n_docs == MAX_DOCUMENTOS or usado >= 0.95 * presupuesto:
            break
    resultados = [Resultado(f, p) for _, f, p in elegidos]
    if fijos:
        vistos = {f["id"] for _, f, _ in elegidos}
        resultados += [r for r in articulos_fijos(buscador) if r.fragmento["id"] not in vistos]
    return resultados


# --------------------------------------------------------------------------- #
# Prompt y salida
# --------------------------------------------------------------------------- #
def construir_mensajes(caso: dict, resultados: list[Resultado], fecha_resolucion: str | date) -> list[dict]:
    contexto = "\n\n".join(f"[{n}] {describir_fragmento(r.fragmento)}\n{r.fragmento['texto'].strip()}"
                           for n, r in enumerate(resultados, 1))
    e = entrada(caso)
    json_ = lambda o: json.dumps(o, ensure_ascii=False, indent=1)  # noqa: E731
    usuario = (
        f"Fecha de presentación: {fecha_en_letra(e['instancia']['fecha_presentacion'])}\n"
        f"Fecha de la resolución: {fecha_en_letra(fecha_resolucion)}\n\n"
        f"FICHA DEL TRÁMITE EN LA SEDE ELECTRÓNICA\n{describir_ficha(caso.get('ficha_sia'))}\n\n"
        f"NORMATIVA (fragmentos aplicables en la fecha de presentación)\n\n{contexto}\n\n"
        f"INSTANCIA\n{json_(e['instancia'])}\n\n"
        f"EXPEDIENTE (datos que ya constan en la ULPGC)\n{json_(e['expediente'])}\n\n"
        f"INFORMES\n{json_(e['informes']) if e['informes'] else '(ninguno)'}\n\n"
        "Resuelve la instancia."
    )
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]


class SalidaInvalida(ValueError):
    """El modelo no devolvió un JSON con el esquema pedido."""


def leer_salida(texto: str) -> dict:
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`").removeprefix("json").strip()
    try:
        salida = json.loads(texto)
    except ValueError:
        a, b = texto.find("{"), texto.rfind("}")
        try:
            salida = json.loads(texto[a:b + 1]) if a >= 0 < b else None
        except ValueError:
            salida = None
    if not isinstance(salida, dict) or salida.get("decision") not in DECISIONES or "resolucion" not in salida:
        raise SalidaInvalida(f"La salida no es una resolución válida: {texto[:300]!r}")
    return salida


@dataclass
class Resolucion:
    caso_id: str
    salida: dict
    resultados: list[Resultado]
    razonamiento: str = ""
    segundos: float = 0.0
    mensajes: list[dict] = field(repr=False, default_factory=list)

    def fragmentos_citados(self) -> list[Resultado]:
        nums = sorted({n for r in self.salida.get("requisitos", []) for n in r.get("fragmentos", [])
                       if 1 <= n <= len(self.resultados)})
        return [self.resultados[n - 1] for n in nums]


class Resolver:
    def __init__(self, buscador: Buscador, llm: ClienteLLM, presupuesto: int = PRESUPUESTO, pensar: bool = True):
        self.buscador = buscador
        self.llm = llm
        self.presupuesto = presupuesto
        self.pensar = pensar

    @classmethod
    def cargar(cls, url: str = URL_POR_DEFECTO, modelo_llm: str | None = MODELO_LLM,
               presupuesto: int = PRESUPUESTO, pensar: bool = True) -> "Resolver":
        llm = ClienteLLM(url, modelo_llm)  # primero: si no hay servidor, falla antes de cargar índices
        return cls(Buscador.cargar(), llm, presupuesto, pensar)

    def preparar(self, caso: dict, fecha_resolucion: str | date | None = None) -> tuple[list[Resultado], list[dict]]:
        """fecha_resolucion: por defecto, hoy o la de presentación si es posterior."""
        if fecha_resolucion is None:
            fecha_resolucion = max(date.today().isoformat(), caso["instancia"]["fecha_presentacion"])
        resultados = buscar_para_caso(self.buscador, caso, self.presupuesto)
        return resultados, construir_mensajes(caso, resultados, fecha_resolucion)

    def resolver(self, caso: dict, fecha_resolucion: str | date | None = None) -> Resolucion:
        resultados, mensajes = self.preparar(caso, fecha_resolucion)
        t = time.time()
        partes = {"razonamiento": [], "respuesta": []}
        for tipo, trozo in self.llm.generar(mensajes, pensar=self.pensar, temperatura=TEMPERATURA,
                                            max_tokens=MAX_TOKENS, extra={"response_format": ESQUEMA}):
            partes[tipo].append(trozo)
        salida = leer_salida("".join(partes["respuesta"]))
        return Resolucion(caso.get("id", ""), salida, resultados, "".join(partes["razonamiento"]).strip(),
                          round(time.time() - t, 1), mensajes)
