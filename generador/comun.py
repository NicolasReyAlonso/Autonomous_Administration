"""Piezas comunes: personas ficticias, fechas y días hábiles, requisitos y textos compartidos."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

# --------------------------------------------------------------------------- #
# Personas ficticias
# --------------------------------------------------------------------------- #
# Sin los nombres de los casos de prueba (data/instancias/) para no mezclar entrenamiento y prueba
NOMBRES_F = ["Ana", "Carmen", "Elena", "Irene", "Sara", "Paula", "Raquel", "Beatriz", "Cristina", "Noelia",
             "Yaiza", "Ainhoa", "Tamara", "Natalia", "Rocío", "Alba", "Claudia", "Patricia", "Miriam", "Inés",
             "Judith", "Lorena", "Sofía", "Daniela", "Aitana", "Candelaria", "Guacimara", "Nayra"]
NOMBRES_M = ["Alejandro", "Miguel", "David", "Jorge", "Adrián", "Rubén", "Iván", "Héctor", "Óscar", "Raúl",
             "Samuel", "Víctor", "Diego", "Mario", "Hugo", "Álvaro", "Gonzalo", "Marcos", "Eduardo", "Tomás",
             "Aday", "Acoran", "Yeray", "Airam", "Jonay", "Cristian", "Joel", "Nicolás"]
APELLIDOS = ["García", "González", "Rodríguez", "Pérez", "Hernández", "Martín", "Sánchez", "Díaz", "Suárez",
             "Santana", "Cabrera", "Ramírez", "Morales", "Domínguez", "Herrera", "Medina", "Castro", "Ortega",
             "Navarro", "Vega", "Torres", "Ruiz", "Álvarez", "Delgado", "Falcón", "Trujillo", "Monzón",
             "Perdomo", "Padrón", "Batista", "Melián", "Guerra", "Marrero", "Brito", "Armas", "Sosa"]
LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


@dataclass
class Persona:
    nombre: str
    dni: str
    correo: str
    mujer: bool

    # Concordancias para los textos
    @property
    def don(self) -> str:
        return "doña" if self.mujer else "don"

    @property
    def don_abrev(self) -> str:
        return "D.ª" if self.mujer else "D."

    @property
    def la(self) -> str:  # «la interesada» / «el interesado»
        return "la" if self.mujer else "el"

    def a(self, masculino: str) -> str:
        """'matriculado' -> 'matriculada' si es mujer (palabras terminadas en -o)."""
        return masculino[:-1] + "a" if self.mujer and masculino.endswith("o") else masculino

    def solicitante(self) -> dict:
        return {"nombre": self.nombre, "dni": self.dni, "correo": self.correo, "telefono": "600000000",
                "notificacion": "Correo electrónico"}


def dni_ficticio(rng: random.Random) -> str:
    """DNI con letra válida y número de patrón evidentemente inventado (un bloque repetido)."""
    bloque = str(rng.randint(10, 99)) if rng.random() < 0.3 else str(rng.randint(1000, 9999))
    numero = int((bloque * 4)[:8])
    return f"{numero:08d}{LETRAS_DNI[numero % 23]}"


def persona(rng: random.Random, mujer: bool | None = None) -> Persona:
    mujer = rng.random() < 0.5 if mujer is None else mujer
    nombre = rng.choice(NOMBRES_F if mujer else NOMBRES_M)
    a1, a2 = rng.sample(APELLIDOS, 2)
    correo = f"{sin_tildes(nombre).lower()}.{sin_tildes(a1).lower()}{rng.randint(200, 999)}@alu.ulpgc.es"
    return Persona(f"{nombre} {a1} {a2}", dni_ficticio(rng), correo, mujer)


def sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").replace("ñ", "n")


# --------------------------------------------------------------------------- #
# Fechas
# --------------------------------------------------------------------------- #
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")
# Festivos nacionales, de Canarias y locales de Las Palmas de Gran Canaria del periodo que se
# genera. Las fechas se eligen en ventanas sin festivos; la lista es por si acaso.
FESTIVOS = {date.fromisoformat(d) for d in (
    "2026-09-08", "2026-10-12", "2026-11-02", "2026-12-07", "2026-12-08", "2026-12-25",
    "2027-01-01", "2027-01-06", "2027-02-09", "2027-03-25", "2027-03-26", "2027-05-31", "2027-06-24",
)}


def habil(d: date) -> bool:
    return d.weekday() < 5 and d not in FESTIVOS


def sumar_habiles(d: date, n: int) -> date:
    """n días hábiles después (n > 0) o antes (n < 0) de d."""
    paso = timedelta(days=1 if n > 0 else -1)
    while n:
        d += paso
        if habil(d):
            n += -1 if n > 0 else 1
    return d


def habiles_entre(a: date, b: date, rng: random.Random) -> date:
    """Un día hábil al azar entre a y b, ambos incluidos."""
    dias = [a + timedelta(days=i) for i in range((b - a).days + 1)]
    return rng.choice([d for d in dias if habil(d)])


def en_letra(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def en_letra_mayus(d: date | str) -> str:
    return en_letra(d).upper()


def nota(x: float) -> str:
    """3.5 -> '3,5'; 4.0 -> '4,0'."""
    return f"{x:.1f}".replace(".", ",")


def lista_y(cosas: list[str]) -> str:
    return cosas[0] if len(cosas) == 1 else ", ".join(cosas[:-1]) + " y " + cosas[-1]


# --------------------------------------------------------------------------- #
# Requisitos y casos
# --------------------------------------------------------------------------- #
def req(requisito: str, norma: str, cumple: bool, motivo: str, fuentes: list[tuple[str, str]] = ()) -> dict:
    """fuentes: (texto del título del documento, artículo) para rellenar las citas [n] al
    construir los ejemplos de entrenamiento; no forma parte del gold que se evalúa."""
    return {"requisito": requisito, "norma": norma, "cumple": cumple, "motivo": motivo,
            "fuentes": [{"documento": d, "articulo": a} for d, a in fuentes]}


def caso(id_: str, tramite: str, ficha: str | None, notas: str, instancia: dict, expediente: dict,
         informes: list, gold: dict, rama: str) -> dict:
    return {"id": id_, "tramite": tramite, "ficha_sia": ficha, "rama": rama, "notas_caso": notas,
            "instancia": instancia, "expediente": expediente, "informes": informes, "gold": gold}


def instancia(procedimiento: str, registro: str, fecha: date, p: Persona, destinatario: str, asunto: str,
              expone: str, solicita: str, documentacion: list[dict], firmada: bool = True) -> dict:
    return {"procedimiento": procedimiento, "registro": registro, "fecha_presentacion": fecha.isoformat(),
            "solicitante": p.solicitante(), "organo_destinatario": destinatario, "asunto": asunto,
            "expone": expone, "solicita": solicita, "documentacion": documentacion, "firmada": firmada}


def documento(nombre: str, contenido: str) -> dict:
    return {"nombre": nombre, "contenido": contenido}


# --------------------------------------------------------------------------- #
# Textos compartidos
# --------------------------------------------------------------------------- #
LEY39 = "Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común de las Administraciones Públicas"
SEDE = "Sede Electrónica de la ULPGC"
REGISTRO_GENERAL = "Registro General de la ULPGC"
EII = "Escuela de Ingeniería Informática"
ADMIN_EDIFICIO = "Administración del Edificio de Informática y Matemáticas"
LUGAR = "Las Palmas de Gran Canaria"


def presentada_por(registro: str) -> str:
    if registro == SEDE:
        return "a través de la Sede Electrónica de la Universidad de Las Palmas de Gran Canaria"
    return "en el Registro General de la Universidad de Las Palmas de Gran Canaria"


def vista(registro: str, p: Persona, fecha: date, objeto: str) -> str:
    return (f"Vista la instancia presentada {presentada_por(registro)} por {p.don} {p.nombre}, con DNI {p.dni}, "
            f"con fecha {en_letra(fecha)}, mediante la que solicita {objeto}, resultan los siguientes")


def firma(fecha: date, cargo: str, sello: bool = False) -> list[str]:
    return [f"{LUGAR}, a {en_letra(fecha)}.", cargo, "(firma y sello)" if sello else "(firma)", "[Nombre y apellidos]"]


RECURSO_TRAMITE = ("Ninguno: el requerimiento es un acto de trámite que no decide el fondo ni impide continuar el "
                   "procedimiento (art. 112.1 de la Ley 39/2015).")


def requerimiento(objeto_titulo: str, p: Persona, fecha_presentacion: date, registro: str, relativa: str,
                  defectos: list[str], fecha: date) -> list[str]:
    """Requerimiento de subsanación según el modelo del Manual (págs. 111-113), con la Ley 39/2015."""
    return [
        f"REQUERIMIENTO DE SUBSANACIÓN DE DEFECTOS EN LA SOLICITUD DE {objeto_titulo.upper()}",
        f"Esta Administración de Edificio, en relación con la solicitud presentada por usted con fecha "
        f"{en_letra(fecha_presentacion)} {presentada_por(registro)}, relativa a {relativa}, le requiere, de acuerdo "
        f"con lo previsto en el artículo 68.1 de la {LEY39} (BOE de 2 de octubre), para que en el plazo de diez días "
        "hábiles contados a partir del día siguiente al de la recepción de este requerimiento, proceda a subsanar los "
        "defectos existentes en su solicitud, debiendo para ello:",
        *(f"{n}) {d}" for n, d in enumerate(defectos, 1)),
        "De no producirse la subsanación en el plazo mencionado, se entenderá que ha desistido de su petición y se "
        "procederá a su archivo sin más trámite, previa resolución en tal sentido, dictada en los términos previstos en "
        "el artículo 21 de la Ley 39/2015.",
        "Lo que se le notifica en cumplimiento del artículo 40 de la mencionada Ley 39/2015.",
        *firma(fecha, "EL/LA ADMINISTRADOR/A DEL EDIFICIO DE INFORMÁTICA Y MATEMÁTICAS", sello=True),
        f"{p.don_abrev} {p.nombre.upper()}",
    ]


ORDINALES = ("Primero", "Segundo", "Tercero", "Cuarto", "Quinto", "Sexto", "Séptimo", "Octavo")


def numerar(parrafos: list[str]) -> list[str]:
    """Antepone «Primero.-», «Segundo.-»… a cada párrafo."""
    return [f"{ORDINALES[i]}.- {t}" for i, t in enumerate(parrafos)]


def documento_resolucion(titulo: str, vista_: str, hechos: list[str], fundamentos: list[str], competencia: str,
                         decision: str, pie: str, cierre: list[str], verbo: str = "RESUELVE:") -> list[str]:
    return [titulo, vista_, "HECHOS", *numerar(hechos), "FUNDAMENTOS DE DERECHO", *numerar(fundamentos),
            competencia, verbo, decision, pie, *cierre]
