"""Evaluación compensatoria en la EII (Grado en Ingeniería Física y Matemática, Plan 40).

Dos regímenes según la fecha de presentación (Plazos de la EII 2026/2027):
  2018  del 2 al 16 dic 2026: Reglamento ULPGC de 2018 + Reglamento de la EII (Rev. 06) +
        Listado de no compensables (Rev. 04). Resuelve la Comisión de Compensación.
  2026  desde el 8 ene 2027: Reglamento 1/2026 + relación de no compensables de la Junta de
        Escuela de 13-07-26. Resuelve el Director.
Fuera de esas ventanas, inadmisión por extemporánea.

Las siglas de la relación de 2026 (Tabla resumen) se leen así: P1/P2 Programación I/II,
P Probabilidad, AL Álgebra Lineal, G1/G2 Geometría I/II, MMA1 Métodos matemáticos y sus
aplicaciones I, ESM Estado Sólido y Materiales, PI Proyectos de Ingeniería (interpretación).
"""

from __future__ import annotations

import random
from datetime import date

from generador.comun import (ADMIN_EDIFICIO, EII, LEY39, REGISTRO_GENERAL, RECURSO_TRAMITE, SEDE, Persona,
                             caso, documento, documento_resolucion, en_letra, en_letra_mayus, firma, habiles_entre,
                             instancia, lista_y, nota, persona, req, requerimiento, sumar_habiles, vista)

TRAMITE, FICHA = "evaluacion_compensatoria", "2890455"
GIFM = "Grado en Ingeniería Física y Matemática (Plan 40)"
GRADO = "Grado en Ingeniería Física y Matemática"
PROCEDIMIENTO = "Evaluación compensatoria de titulaciones de grado (Administración del Edificio de Informática y Matemáticas)"
CURSO_1 = ["Fundamentos de Física I", "Programación I", "Álgebra Lineal", "Fundamentos de Matemáticas I",
           "Fundamentos de Física II", "Física experimental y Computacional I", "Métodos Numéricos en Física",
           "Fundamentos de Matemáticas II", "Programación II", "Introducción a la Física Moderna"]
CURSO_2 = ["Geometría I", "Análisis Matemático I", "Mecánica analítica y relatividad",
           "Métodos matemáticos y sus aplicaciones I", "Termodinámica", "Análisis matemático II", "Probabilidad",
           "Fundamentos de electrónica", "Física experimental y computacional II", "Electromagnetismo y óptica física I",
           "Geometría II"]
ESM, PI = "Estado Sólido y Materiales", "Proyectos de Ingeniería"
CURSO = {**{a: 1 for a in CURSO_1}, **{a: 2 for a in CURSO_2}, ESM: 3, PI: 3}
NO_COMP_2026 = {"Programación I", "Programación II", "Probabilidad", "Álgebra Lineal", "Geometría I", "Geometría II",
                "Métodos matemáticos y sus aplicaciones I", ESM, PI}
SIGLA = {"Programación I": "P1", "Programación II": "P2", "Probabilidad": "P", "Álgebra Lineal": "AL",
         "Geometría I": "G1", "Geometría II": "G2", "Métodos matemáticos y sus aplicaciones I": "MMA1", ESM: "ESM",
         PI: "PI"}
COMPETENCIA_PAREJA = {"Programación I": "CE14", "Programación II": "CE14", "Probabilidad": "CE12",
                      "Estadística": "CE12", ESM: "CE17", PI: "CE17"}
PAREJA = {"Programación I": "Programación II", "Programación II": "Programación I", "Probabilidad": "Estadística",
          "Estadística": "Probabilidad", ESM: PI, PI: ESM}
COMPENSABLES_2026 = [a for a in CURSO_1 + CURSO_2 if a not in NO_COMP_2026]
MASTER = "Máster Universitario en Ingeniería Informática"
ASIG_MASTER = ["Sistemas Distribuidos Avanzados", "Ingeniería de Requisitos", "Seguridad en Redes",
               "Gestión de Proyectos de Software"]  # inventadas: el caso solo depende de la titulación

# Documentos (para las citas [n]): texto del título y artículo
D_EII = "Reglamento de evaluación compensatoria de la EII"
D_U18 = "DEROGADO Reglamento de Evaluación Compensatoria"
D_LIS = "Listado de Asignaturas NO Compensables"
D_PLA = "Plazos para la solicitud de la evaluación compensatoria"
D_R26 = "Reglamento 1/2026"
D_TAB = "Tabla resumen de la evaluación compensatoria"
D_LEY = "Ley 39/2015"

R2026 = "Reglamento 1/2026, de Evaluación Compensatoria de Asignaturas para las Titulaciones Oficiales de Grado de la ULPGC"
NORMAS_2018 = [
    "Reglamento de Evaluación Compensatoria para las Titulaciones Oficiales de Grado de la ULPGC (BOULPGC de 5 de diciembre de 2018)",
    "Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática (Rev. 06, BOULPGC de 27 de enero de 2023)",
    "Listado de Asignaturas No Compensables de la EII (Rev. 04, 5 de mayo de 2023)",
]
NORMAS_2026 = [
    f"{R2026} (BOULPGC de 3 de julio de 2026)",
    "Relación de asignaturas no compensables aprobada por la Junta de la Escuela de Ingeniería Informática el 13 de "
    "julio de 2026 (Tabla resumen de la evaluación compensatoria de la EII)",
    "Plazos de evaluación compensatoria de la EII, curso 2026/2027",
]
ORGANO = {"2018": "Comisión de Compensación de la Escuela de Ingeniería Informática",
          "2026": "Director de la Escuela de Ingeniería Informática"}
RECURSO = {
    "2018": "Alzada ante el Vicerrector con competencias en materia de estudiantes, Presidente de la Comisión de "
            "Compensación Central, en el plazo de un mes (art. 5 bis.1 del Reglamento de 2018; arts. 121 y 122 de la "
            "Ley 39/2015)",
    "2026": "Alzada ante el Rector o el Vicerrector en quien delegue, en el plazo de un mes (arts. 6.2 y 7.3 del "
            "Reglamento 1/2026; arts. 121 y 122 de la Ley 39/2015)",
}
FUND_NORMA = {
    "2018": f"El {R2026} (BOULPGC de 3 de julio de 2026), entra en vigor en la convocatoria ordinaria del curso "
            "2026/2027, según su disposición final. A las solicitudes vinculadas a la convocatoria especial les son de "
            "aplicación el Reglamento de Evaluación Compensatoria para las Titulaciones Oficiales de Grado de la ULPGC "
            "(BOULPGC de 5 de diciembre de 2018) y el Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería "
            "Informática (BOULPGC de 27 de enero de 2023).",
    "2026": f"El {R2026} (BOULPGC de 3 de julio de 2026), entra en vigor en la convocatoria ordinaria del curso "
            "2026/2027, según su disposición final, y deroga el Reglamento de Evaluación Compensatoria para las "
            "Titulaciones Oficiales de Grado de la ULPGC de 2018 y los reglamentos de Centros elaborados en aplicación "
            "de este (disposición derogatoria). La Escuela de Ingeniería Informática lo aplica a las solicitudes "
            "vinculadas a la convocatoria ordinaria, que pueden presentarse durante todo el curso académico a partir "
            "del 8 de enero de 2027 (artículo 7.1).",
}
COMPETENCIA = {
    "2018": "En virtud de lo expuesto, esta Comisión, en uso de las competencias atribuidas por el artículo 2 del "
            "Reglamento de Evaluación Compensatoria para las Titulaciones Oficiales de Grado de la ULPGC y por los "
            "artículos 2 y 8 del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática,",
    "2026": f"En virtud de lo expuesto, este Director, en uso de las competencias atribuidas por el artículo 6.1 del {R2026},",
}
PIE = {
    "2018": "Contra la presente resolución, que no agota la vía administrativa, podrá interponerse recurso de alzada "
            "ante el Vicerrector con competencias en materia de estudiantes, Presidente de la Comisión de Compensación "
            "Central, en el plazo de un mes contado a partir del día siguiente al de su notificación, de conformidad con "
            "el artículo 5 bis.1 del Reglamento de Evaluación Compensatoria para las Titulaciones Oficiales de Grado de "
            f"la ULPGC y los artículos 121 y 122 de la {LEY39}, sin perjuicio de cualquier otro recurso que se estime "
            "procedente.",
    "2026": "Contra la presente resolución, que no agota la vía administrativa, podrá interponerse recurso de alzada "
            "ante el Rector de la Universidad de Las Palmas de Gran Canaria o el Vicerrector en quien delegue, en el "
            "plazo de un mes contado a partir del día siguiente al de su notificación, de conformidad con los artículos "
            f"6.2 y 7.3 del {R2026}, y los artículos 121 y 122 de la {LEY39}, sin perjuicio de cualquier otro recurso "
            "que se estime procedente.",
}
CARGO = {"2018": "EL/LA PRESIDENTE/A DE LA COMISIÓN DE COMPENSACIÓN DE LA ESCUELA DE INGENIERÍA INFORMÁTICA",
         "2026": "EL DIRECTOR DE LA ESCUELA DE INGENIERÍA INFORMÁTICA"}
HECHO_PLAZO = {
    "2018": "La solicitud se presentó dentro del plazo abierto para las solicitudes vinculadas a la convocatoria "
            "especial del curso 2026/2027, del 2 al 16 de diciembre de 2026.",
    "2026": "La solicitud se presentó en el plazo para las solicitudes vinculadas a la convocatoria ordinaria del curso "
            "2026/2027, abierto durante todo el curso académico a partir del 8 de enero de 2027.",
}
HECHO_REVISION = ("La Administración del Edificio de Informática y Matemáticas ha revisado el cumplimiento de los "
                  "requisitos, conforme al artículo 6.1 del Reglamento 1/2026.")
ESPECIAL = (date(2026, 12, 2), date(2026, 12, 16))
ORDINARIA_DESDE = date(2027, 1, 8)

# Ramas: (nombre, régimen, decisión, peso)
RAMAS = [
    ("estimar", "2018", "estimar", 4), ("estimar_excepcion_media", "2018", "estimar", 2),
    ("extemporanea", "2018", "inadmitir", 3), ("sin_firma", "2018", "requerir_subsanacion", 2),
    ("master", "2018", "inadmitir", 2), ("creditos", "2018", "desestimar", 2), ("matricula", "2018", "desestimar", 1),
    ("notas", "2018", "desestimar", 2), ("primeros_cursos", "2018", "desestimar", 2), ("pe_tfg", "2018", "desestimar", 1),
    ("pareja", "2018", "desestimar", 2), ("limite", "2018", "desestimar", 1),
    ("estimar", "2026", "estimar", 4), ("creditos", "2026", "desestimar", 2), ("matricula", "2026", "desestimar", 1),
    ("convocatorias", "2026", "desestimar", 2), ("tres", "2026", "desestimar", 2), ("media", "2026", "desestimar", 2),
    ("no_compensable", "2026", "desestimar", 3), ("pe_tfg", "2026", "desestimar", 1), ("limite", "2026", "desestimar", 1),
    ("sin_firma", "2026", "requerir_subsanacion", 1), ("master", "2026", "inadmitir", 1),
]


# --------------------------------------------------------------------------- #
# Datos del expediente
# --------------------------------------------------------------------------- #
CONVOCATORIAS = [(c, t) for c in ("2023/2024", "2024/2025", "2025/2026") for t in ("ordinaria", "extraordinaria")]


def convocatorias(rng: random.Random, notas: list[float]) -> list[dict]:
    inicio = rng.randint(0, len(CONVOCATORIAS) - len(notas))
    return [{"curso": c, "convocatoria": t, "nota": n} for (c, t), n in zip(CONVOCATORIAS[inicio:], notas)]


def notas_que_cumplen(rng: random.Random, n: int = 3) -> list[float]:
    """Al menos dos con 2 o más (2018) y alguna con 3 o más (2026)."""
    while True:
        ns = [round(rng.uniform(1.5, 4.8), 1) for _ in range(n)]
        if sum(x >= 2 for x in ns) >= 2 and max(ns) >= 3.0 and min(ns) >= 1.0:
            return ns


def expediente(asignatura: str, ects: int, otras: int, matriculada: bool, notas_: list[float], rng: random.Random,
               media: float, compensadas: list[str], pendiente_extra: str | None, superadas: list[dict],
               pe_tfg_pendientes: bool = True, titulacion: str = GIFM) -> dict:
    pendientes = [{"asignatura": asignatura, "curso": CURSO.get(asignatura, 4), "ects": ects,
                   "matriculada_2026_2027": matriculada, "convocatorias": convocatorias(rng, notas_)}]
    if pendiente_extra:
        pendientes.append({"asignatura": pendiente_extra, "curso": CURSO[pendiente_extra], "ects": 6,
                           "matriculada_2026_2027": True, "convocatorias": convocatorias(rng, notas_que_cumplen(rng, 2))})
    for a in ("Prácticas Externas", "Trabajo Fin de Grado"):
        if pe_tfg_pendientes and a != asignatura:
            pendientes.append({"asignatura": a, "curso": 4, "ects": 12, "matriculada_2026_2027": True, "convocatorias": []})
    if otras:
        n_otras = otras // 6
        pendientes.append({"asignatura": f"Otras asignaturas de 3.º y 4.º curso ({n_otras} asignatura{'s' if n_otras > 1 else ''})", "curso": 3,
                           "ects": otras, "matriculada_2026_2027": True, "convocatorias": []})
    pend = sum(x["ects"] for x in pendientes)
    no_comp_superadas = 0 if pe_tfg_pendientes else 24 - (12 if asignatura in ("Prácticas Externas", "Trabajo Fin de Grado") else 0)
    pendientes_1_2 = [x["asignatura"] for x in pendientes if x["curso"] in (1, 2)]
    return {
        "titulacion": titulacion,
        "centro": EII,
        "creditos_titulacion": 240,
        "creditos_superados": 240 - pend,
        "creditos_superados_compensables": 240 - pend - no_comp_superadas,
        "primer_y_segundo_curso": ("Todas las asignaturas superadas" if not pendientes_1_2
                                   else f"Superadas todas salvo {lista_y(pendientes_1_2)}"),
        "nota_media": media,
        "compensadas_anteriormente": [{"asignatura": a, "ects": 6, "curso_academico": "2025/2026"} for a in compensadas],
        "pendientes": pendientes,
        "superadas_relevantes": superadas,
    }


# --------------------------------------------------------------------------- #
# Generación
# --------------------------------------------------------------------------- #
def generar(rng: random.Random, n: int, prefijo: str = "gen-comp") -> list[dict]:
    pesos = [r[3] for r in RAMAS]
    return [construir(rng, f"{prefijo}-{i:04d}", *rng.choices(RAMAS, pesos)[0][:3]) for i in range(1, n + 1)]


def construir(rng: random.Random, id_: str, rama: str, regimen: str, decision: str) -> dict:
    p = persona(rng)
    # ---- fechas
    if rama == "extemporanea":
        fecha = (habiles_entre(date(2026, 11, 17), date(2026, 12, 1), rng) if rng.random() < 0.4
                 else habiles_entre(date(2026, 12, 17), date(2027, 1, 7), rng))
        fecha_res = date(2026, 12, rng.choice((21, 22, 23)))
        if fecha >= fecha_res:
            fecha_res = sumar_habiles(fecha, 3)
    elif regimen == "2018":
        fecha = habiles_entre(*ESPECIAL, rng)
        fecha_res = date(2026, 12, rng.choice((21, 22, 23)))
    else:
        fecha = habiles_entre(ORDINARIA_DESDE, date(2027, 6, 18), rng)
        fecha_res = sumar_habiles(fecha, rng.randint(8, 18))
    if rama == "sin_firma":
        fecha_res = sumar_habiles(fecha, rng.randint(1, 3))

    # ---- asignatura pedida
    if rama == "pe_tfg":
        asignatura = rng.choice(["Prácticas Externas", "Trabajo Fin de Grado"])
    elif rama == "no_compensable":
        asignatura = rng.choice(sorted(NO_COMP_2026 - {PI}))
    elif rama == "pareja":
        asignatura = rng.choice(["Programación II", "Programación I", "Probabilidad", ESM])
    elif regimen == "2026":
        asignatura = rng.choice(COMPENSABLES_2026)
    else:
        asignatura = rng.choice(CURSO_1 + CURSO_2 + [ESM, ESM, ESM])
    if rama == "master":
        asignatura = rng.choice(ASIG_MASTER)
    ects = 12 if asignatura in ("Prácticas Externas", "Trabajo Fin de Grado") else 6

    # ---- datos del expediente según la rama (un solo requisito falla)
    notas_ = notas_que_cumplen(rng, rng.choice((3, 3, 4)))
    media = round(rng.uniform(6.1, 7.6), 1)
    otras = rng.choice((0, 0, 6, 12, 18))
    matriculada, compensadas, extra, superadas = True, [], None, []
    pe_tfg_pend = True
    if rama == "creditos":
        otras = rng.choice((36, 42, 48))
    elif rama == "matricula":
        matriculada = False
    elif rama == "notas":
        notas_ = [round(rng.uniform(0.5, 1.9), 1), round(rng.uniform(0.5, 1.9), 1), round(rng.uniform(2.0, 4.5), 1)]
        rng.shuffle(notas_)
        media = round(rng.uniform(5.6, 6.4), 1)
    elif rama == "estimar_excepcion_media":
        notas_ = [round(rng.uniform(0.5, 1.9), 1), round(rng.uniform(0.8, 1.9), 1), round(rng.uniform(2.0, 4.6), 1)]
        rng.shuffle(notas_)
        media = round(rng.uniform(6.6, 7.8), 1)
    elif rama == "convocatorias":
        notas_ = [round(rng.uniform(2.0, 2.9), 1), round(rng.uniform(3.0, 4.6), 1)]
    elif rama == "tres":
        notas_ = [round(rng.uniform(1.5, 2.9), 1) for _ in range(3)]
    elif rama == "media":
        media = round(rng.uniform(5.1, 5.9), 1)
    elif rama == "primeros_cursos":
        if CURSO.get(asignatura, 3) in (1, 2):
            asignatura = ESM  # para que la pendiente de 1.º/2.º sea otra, no incluida en la solicitud
        extra = rng.choice(CURSO_1 + CURSO_2)
    elif rama == "pareja":
        compensadas = [PAREJA[asignatura]]  # el bucle de abajo la añade a las superadas
    elif rama == "limite":
        posibles = [a for a in (COMPENSABLES_2026 if regimen == "2026" else CURSO_1 + CURSO_2)
                    if a != asignatura and a not in PAREJA]
        compensadas = rng.sample(posibles, 2)
    if rama in ("estimar", "estimar_excepcion_media") and rng.random() < 0.3:
        posibles = [a for a in (COMPENSABLES_2026 if regimen == "2026" else CURSO_1 + CURSO_2)
                    if a != asignatura and a not in PAREJA]
        compensadas = [rng.choice(posibles)]
    if regimen == "2018" and asignatura in PAREJA and rama != "pareja":
        superadas = [{"asignatura": PAREJA[asignatura], "nota": round(rng.uniform(5.0, 8.5), 1), "compensada": False}]
    if rama == "pe_tfg":
        otras = 0
    for a in compensadas:  # las compensadas cuentan como superadas
        superadas.append({"asignatura": a, "nota": 5, "compensada": True})
    titulacion = MASTER if rama == "master" else GIFM
    exp = expediente(asignatura, ects, otras, matriculada, notas_, rng, media, compensadas, extra, superadas,
                     pe_tfg_pend, titulacion)
    if rama == "master":
        exp.update(creditos_titulacion=90, creditos_superados=72)
        exp.pop("creditos_superados_compensables")
        exp["pendientes"] = [exp["pendientes"][0],
                             {"asignatura": "Trabajo Fin de Máster", "curso": 2, "ects": 12,
                              "matriculada_2026_2027": True, "convocatorias": []}]
        exp["primer_y_segundo_curso"] = "No procede (máster)"
        exp["superadas_relevantes"] = []

    # ---- instancia
    registro = REGISTRO_GENERAL if rama == "sin_firma" else SEDE
    estudios = MASTER if rama == "master" else GRADO
    expone = rng.choice([
        f"Que soy estudiante del {estudios} y estoy {p.a('matriculado')} en el curso 2026/2027 en la asignatura "
        f"{asignatura}, que no he conseguido superar. Que cumplo los requisitos del Reglamento de Evaluación Compensatoria.",
        f"Que curso el {estudios} y que la asignatura {asignatura} es una de las que me quedan para terminar la "
        "titulación. Que reúno los requisitos para solicitar su evaluación compensatoria.",
        f"Que estoy {p.a('matriculado')} en {asignatura} del {estudios}, a la que me he presentado sin superarla, y que "
        "considero que cumplo las condiciones de la normativa de evaluación compensatoria.",
    ])
    solicita = f"Que se me conceda la evaluación compensatoria de la asignatura {asignatura} ({ects} ECTS)."
    docs = [documento("Solicitud de evaluación compensatoria (formulario de la EII)",
                      f"{p.don_abrev} {p.nombre}, con DNI {p.dni}, estudiante del {estudios}, solicita la compensación "
                      "de las asignaturas listadas en la tabla adjunta, declarando conocer la reglamentación vigente y "
                      f"cumplir los requisitos que en ella se exigen. Asignatura: {asignatura}.")]
    ins = instancia(PROCEDIMIENTO, registro, fecha, p, "Dirección de la Escuela de Ingeniería Informática",
                    "Solicitud de evaluación compensatoria", expone, solicita, docs, firmada=rama != "sin_firma")

    # ---- informe del coordinador (régimen de 2018, solo si se cumplen los requisitos)
    informes = []
    if regimen == "2018" and decision == "estimar":
        fecha_inf = habiles_entre(date(2026, 12, 17), sumar_habiles(fecha_res, -1), rng)
        informes = [{"tipo": "informe_coordinador", "fecha": fecha_inf.isoformat(), "asignatura": asignatura,
                     "sentido": "favorable", "texto": rng.choice([
                         f"{p.la.capitalize()} estudiante ha seguido la asignatura con regularidad y sus calificaciones muestran "
                         "que ha adquirido una parte sustancial de las competencias. Se informa favorablemente la compensación.",
                         "Visto el conjunto del expediente y la evolución de sus calificaciones, se considera que ha "
                         "alcanzado las competencias esenciales de la asignatura. Informe favorable.",
                     ])}]

    datos = dict(p=p, fecha=fecha, fecha_res=fecha_res, regimen=regimen, rama=rama, asignatura=asignatura, ects=ects,
                 exp=exp, registro=registro, informes=informes, notas_=notas_, media=media, compensadas=compensadas,
                 extra=extra, matriculada=matriculada)
    gold = gold_caso(decision, **datos)
    notas = f"Generado. Rama {rama} (régimen {regimen}): {decision}."
    return caso(id_, TRAMITE, FICHA, notas, ins, exp, informes, gold, f"{regimen}:{rama}")


# --------------------------------------------------------------------------- #
# Gold
# --------------------------------------------------------------------------- #
def gold_caso(decision: str, *, p: Persona, fecha: date, fecha_res: date, regimen: str, rama: str, asignatura: str,
              ects: int, exp: dict, registro: str, informes: list, notas_: list[float], media: float,
              compensadas: list[str], extra: str | None, matriculada: bool) -> dict:
    la = p.la  # «la» / «el» (interesada/o)
    inter = p.a("interesado")
    objeto = f"la evaluación compensatoria de la asignatura {asignatura} ({ects} ECTS) del {GRADO if rama != 'master' else MASTER}"

    if rama == "extemporanea":
        return gold_extemporanea(p, fecha, fecha_res, asignatura, objeto, registro)
    if rama == "master":
        return gold_master(p, fecha, fecha_res, regimen, asignatura, objeto)
    if rama == "sin_firma":
        return gold_sin_firma(p, fecha, fecha_res, regimen, asignatura)

    reqs, frases = requisitos_fondo(p, regimen, rama, asignatura, ects, exp, notas_, media, compensadas, extra,
                                    matriculada, fecha)
    if regimen == "2018" and decision == "estimar":
        reqs.append(req("Informe del coordinador", "Arts. 7 y 8 del Reglamento de la EII", True,
                        "Cumple los requisitos y el informe es favorable, por lo que la Comisión concede la compensación.",
                        [(D_EII, "7"), (D_EII, "8")]))
    norma = ({"normas": NORMAS_2018, "motivo": f"La solicitud se presenta el {en_letra(fecha)}, en la ventana de la "
              "convocatoria especial (del 2 al 16 de diciembre de 2026). El Reglamento 1/2026 entra en vigor en la "
              "convocatoria ordinaria del curso 2026/2027 (disposición final), así que todavía no se aplica."}
             if regimen == "2018" else
             {"normas": NORMAS_2026, "motivo": f"La solicitud se presenta el {en_letra(fecha)}, en el plazo de la "
              "convocatoria ordinaria, abierto durante todo el curso desde el 8 de enero de 2027. El Reglamento 1/2026 "
              "entra en vigor en la convocatoria ordinaria del curso 2026/2027 (disposición final) y deroga el reglamento "
              "de 2018 y los de los Centros (disposición derogatoria): la EII lo aplica a las solicitudes presentadas "
              "desde el 8 de enero de 2027."})

    # Hechos
    hechos = [HECHO_PLAZO[regimen]]
    if regimen == "2018":
        hechos.append(f"Según su expediente académico, {la} {inter} ha superado {exp['creditos_superados_compensables']} "
                      f"de los 216 créditos susceptibles de compensación de la titulación, "
                      + (f"tiene superadas todas las asignaturas de primer y segundo curso" if exp["primer_y_segundo_curso"].startswith("Todas")
                         else f"tiene pendientes de primer y segundo curso {exp['primer_y_segundo_curso'].removeprefix('Superadas todas salvo ')}")
                      + (f" y está {p.a('matriculado')} en la asignatura en el curso 2026/2027." if matriculada
                         else f", y no está {p.a('matriculado')} en la asignatura en el curso 2026/2027."))
    else:
        hechos.append(f"Según su expediente académico, {la} {inter} ha superado {exp['creditos_superados']} de los 240 "
                      "créditos de la titulación y " + (f"está {p.a('matriculado')}" if matriculada
                                                         else f"no está {p.a('matriculado')}")
                      + " en la asignatura en el curso 2026/2027.")
    conv = exp["pendientes"][0]["convocatorias"]
    txt_conv = lista_y([f"{nota(c['nota'])} ({c['convocatoria']} de {c['curso']})" for c in conv])
    comp_prev = ("No tiene asignaturas compensadas con anterioridad." if not compensadas else
                 f"Tiene compensada{'s' if len(compensadas) > 1 else ''} con anterioridad "
                 f"{lista_y(compensadas)} ({6 * len(compensadas)} ECTS).")
    hechos.append(f"{la.capitalize()} {inter} se ha presentado a {len(conv)} convocatorias de la asignatura, con "
                  f"calificaciones de {txt_conv}. La nota media de su expediente es de {nota(media)} puntos. {comp_prev}")
    if informes:
        hechos.append(f"Con fecha {en_letra(informes[0]['fecha'])} el coordinador de la asignatura emitió informe "
                      "favorable a la compensación.")
    if regimen == "2026":
        hechos.append(HECHO_REVISION)

    # Fundamentos: la norma; los requisitos que se cumplen, agrupados; el que falla, aparte; la conclusión
    fundamentos = [FUND_NORMA[regimen]]
    cumplidos = []
    for cumple, frase in frases:
        if cumple:
            cumplidos.append(frase)
        else:
            if cumplidos:
                fundamentos.append(" ".join(cumplidos))
                cumplidos = []
            fundamentos.append(frase)
    if cumplidos:
        fundamentos.append(" ".join(cumplidos))
    falla = [q for q in reqs if not q["cumple"]]
    if decision == "estimar":
        fundamentos.append(
            ("La solicitud cumple los requisitos del Reglamento y el informe del coordinador de la asignatura es "
             "favorable, por lo que procede conceder la compensación, de acuerdo con el artículo 8 del Reglamento del Centro."
             if regimen == "2018" else
             "Se reúnen los requisitos del Reglamento, por lo que procede conceder la compensación. Corresponde "
             "resolverla al Director del Centro, previa revisión del cumplimiento de los requisitos por la administración "
             "del edificio (artículo 6.1)."))
        if rama == "estimar_excepcion_media":
            fundamentos[-1] = (f"Examinada la solicitud de forma excepcional, la trayectoria de {la} {inter}, con una nota "
                               f"media de {nota(media)} puntos, y el informe favorable del coordinador de la asignatura "
                               "justifican conceder la compensación, de acuerdo con el artículo 8 del Reglamento del Centro.")
        resuelve = (f"Conceder a {p.don} {p.nombre} la evaluación compensatoria de la asignatura {asignatura} ({ects} ECTS) "
                    f"del {GRADO}. " + (
                        "En su expediente figurará la postilla «5 Apto por Compensación» y la asignatura aparecerá en los "
                        "certificados que se emitan con la leyenda «COMPENSADA» (artículo 10 del Reglamento del Centro). "
                        f"{la.capitalize()} {inter} podrá renunciar a la compensación si supera la asignatura por el "
                        "procedimiento habitual antes de que esta resolución sea firme (artículo 11)."
                        if regimen == "2018" else
                        "En su expediente figurará la asignatura como «Compensada -5», con la fecha de esta resolución, y "
                        "se puntuará con 5,00 puntos a efectos de nota media; en los certificados académicos aparecerá con "
                        f"la leyenda «COMPENSADA» (artículo 8 del Reglamento 1/2026). {la.capitalize()} {inter} podrá "
                        "renunciar a la compensación si supera la asignatura antes de que esta resolución sea firme "
                        "(artículo 8.3)."))
    else:
        fundamentos.append(
            ("Al no reunir todos los requisitos del Reglamento, la solicitud no puede ser objeto de estudio, no procede "
             "requerir el informe del coordinador de la asignatura (artículo 7) y la Comisión debe denegar la "
             "compensación (artículo 8), con indicación del requisito incumplido (artículo 9)."
             if regimen == "2018" else
             "Según el artículo 7.2 del Reglamento, las resoluciones desfavorables contendrán los motivos de la "
             "denegación e indicarán que contra ellas cabe interponer recurso de alzada."))
        resuelve = (f"Denegar a {p.don} {p.nombre} la evaluación compensatoria de la asignatura {asignatura} ({ects} ECTS) "
                    f"del {GRADO}, {MOTIVO_DENEGACION[rama](regimen, asignatura)}.")
    titulo = (f"RESOLUCIÓN DE {en_letra_mayus(fecha_res)} "
              + ("DE LA COMISIÓN DE COMPENSACIÓN" if regimen == "2018" else "DEL DIRECTOR")
              + f" DE LA ESCUELA DE INGENIERÍA INFORMÁTICA POR LA QUE SE RESUELVE LA SOLICITUD DE EVALUACIÓN "
              f"COMPENSATORIA DE {p.don.upper()} {p.nombre.upper()}")
    texto = documento_resolucion(titulo, vista(registro, p, fecha, objeto), hechos, fundamentos, COMPETENCIA[regimen],
                                 resuelve, PIE[regimen], firma(fecha_res, CARGO[regimen]))
    return {"decision": decision, "norma_aplicable": norma, "organo": ORGANO[regimen], "recurso": RECURSO[regimen],
            "requisitos": reqs, "resolucion": texto}


MOTIVO_DENEGACION = {
    "creditos": lambda r, a: ("por no haber superado el 85 % de los créditos de la titulación susceptibles de compensación "
                              "(artículo 4.a del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática)"
                              if r == "2018" else
                              "por no haber superado el 75 % de los créditos de la titulación (artículo 4.1 del Reglamento 1/2026)"),
    "matricula": lambda r, a: ("por no constar su matrícula en la asignatura en el curso en que solicita la compensación "
                               + ("(artículo 4.b del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática)"
                                  if r == "2018" else "(artículo 4.2 del Reglamento 1/2026)")),
    "notas": lambda r, a: ("por no haber obtenido una calificación igual o superior a 2 puntos en al menos dos convocatorias "
                           "de la asignatura (artículo 4.c del Reglamento de Evaluación Compensatoria de la Escuela de "
                           "Ingeniería Informática) ni tener una nota media de expediente de 6,5 puntos o más (artículo 4.d)"),
    "primeros_cursos": lambda r, a: ("por no tener superadas todas las asignaturas de los dos primeros cursos, salvo la "
                                     "incluida en la solicitud (artículo 4.e del Reglamento de Evaluación Compensatoria "
                                     "de la Escuela de Ingeniería Informática)"),
    "pe_tfg": lambda r, a: (f"por no proceder la compensación de {'las Prácticas Externas' if a == 'Prácticas Externas' else 'el Trabajo Fin de Grado'} "
                            + ("(artículo 5 del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática)"
                               if r == "2018" else "(artículo 3.3 del Reglamento 1/2026)")),
    "pareja": lambda r, a: (f"por formar pareja no compensable con la asignatura {PAREJA[a]}, que le fue compensada con "
                            "anterioridad (artículo 5.c del Reglamento de Evaluación Compensatoria de la Escuela de "
                            "Ingeniería Informática y Listado de Asignaturas No Compensables de la Escuela)"),
    "limite": lambda r, a: ("por superar la compensación solicitada, junto con la ya concedida, el límite del 6 % de los "
                            "créditos de la titulación (artículo 3 del Reglamento de Evaluación Compensatoria de la Escuela "
                            "de Ingeniería Informática)" if r == "2018" else
                            "por superar la compensación solicitada, junto con la ya concedida, el límite de 15 ECTS de las "
                            "titulaciones de 240 créditos (artículo 3.2 del Reglamento 1/2026)"),
    "convocatorias": lambda r, a: "por no haberse presentado al menos a tres convocatorias de la asignatura (artículo 4.3 del Reglamento 1/2026)",
    "tres": lambda r, a: ("por no haber obtenido al menos una calificación de 3,00 en alguna convocatoria de la asignatura "
                          "(artículo 4.3 del Reglamento 1/2026)"),
    "media": lambda r, a: "por no disponer de una nota media de expediente igual o superior a 6,00 (artículo 4.3 del Reglamento 1/2026)",
    "no_compensable": lambda r, a: ("por ser una asignatura no compensable en esta titulación (artículo 3.4 del Reglamento "
                                    "1/2026 y relación de asignaturas no compensables aprobada por la Junta de Escuela el 13 "
                                    "de julio de 2026)"),
}


def requisitos_fondo(p: Persona, regimen: str, rama: str, asignatura: str, ects: int, exp: dict, notas_: list[float],
                     media: float, compensadas: list[str], extra: str | None, matriculada: bool, fecha: date):
    """Requisitos del gold y frases de los fundamentos (cumple, texto), en el orden del reglamento."""
    la, inter = p.la, p.a("interesado")
    conv = exp["pendientes"][0]["convocatorias"]
    reqs, frases = [], []
    previos = 6 * len(compensadas)
    if regimen == "2018":
        reqs.append(req("Plazo de presentación", "Plazos de evaluación compensatoria de la EII 2026-2027; art. 6 del Reglamento de la EII",
                        True, f"Presentada el {en_letra(fecha)}, dentro del plazo del 2 al 16 de diciembre de 2026.",
                        [(D_PLA, ""), (D_EII, "6")]))
        reqs.append(req("Titulación de grado", "Art. 1 del Reglamento de la EII", True,
                        "Es un grado oficial, no un máster, título propio ni curso de adaptación.", [(D_EII, "1")]))
        sc = exp["creditos_superados_compensables"]
        ok = sc >= 184
        reqs.append(req("85 % de los créditos compensables", "Art. 4.a del Reglamento de la EII; Listado de Asignaturas No Compensables",
                        ok, f"La titulación tiene 216 créditos compensables y se exigen 184; ha superado {sc}.",
                        [(D_EII, "4"), (D_LIS, "")]))
        frases.append((ok, "El artículo 4.a del Reglamento del Centro exige haber superado el 85 % de los créditos de la "
                           "titulación susceptibles de compensación. En el Grado en Ingeniería Física y Matemática estos "
                           "créditos son 216, por lo que se exigen 184, según el Listado de Asignaturas No Compensables de "
                           f"la Escuela. {la.capitalize()} {inter} ha superado {sc}, por lo que "
                           + ("cumple el requisito." if ok else "no cumple el requisito.")))
        reqs.append(req("Matrícula en la asignatura", "Art. 4.b del Reglamento de la EII", matriculada,
                        f"{p.a('Matriculado')} en {asignatura} en el curso 2026/2027."
                        if matriculada else f"No consta matrícula en {asignatura} en el curso 2026/2027.", [(D_EII, "4")]))
        frases.append((matriculada, f"{la.capitalize()} {inter} está {p.a('matriculado')} en la asignatura y curso de los "
                                    "que solicita la compensación (artículo 4.b)." if matriculada else
                       f"El artículo 4.b del Reglamento del Centro exige estar matriculado en la asignatura y curso de los "
                       f"que se solicita la compensación. {la.capitalize()} {inter} no está {p.a('matriculado')} en "
                       f"{asignatura} en el curso 2026/2027, por lo que no cumple el requisito."))
        dos = sum(c["nota"] >= 2 for c in conv)
        ok = dos >= 2 or media >= 6.5
        lista = lista_y([nota(c["nota"]) for c in conv])
        reqs.append(req("Nota de 2 o más en al menos dos convocatorias, o nota media de 6,5 o más",
                        "Arts. 4.c y 4.d del Reglamento de la EII", ok,
                        (f"{len(conv)} convocatorias con {lista}." if dos >= 2 else
                         f"Solo {dos} convocatoria{'s' if dos != 1 else ''} con nota de 2 o más ({lista}), "
                         + (f"pero la nota media es de {nota(media)}: procede examinar la solicitud por la excepción del art. 4.d."
                            if ok else f"y la nota media de {nota(media)} no llega al 6,5 que permite examinarla por excepción."))
                        , [(D_EII, "4")]))
        if dos >= 2:
            frases.append((True, f"Ha obtenido una calificación igual o superior a 2 puntos en {dos} convocatorias (artículo 4.c)."))
        elif ok:
            frases.append((True, f"{la.capitalize()} {inter} solo ha obtenido una calificación igual o superior a 2 puntos en "
                                 f"{dos} de las {len(conv)} convocatorias, por lo que no alcanza la nota mínima del artículo "
                                 f"4.c. No obstante, su nota media de expediente es de {nota(media)} puntos, superior a los "
                                 "6,5 que exige el artículo 4.d, por lo que procede examinar la solicitud de manera "
                                 "excepcional y motivada."))
        else:
            frases.append((False, "El artículo 4.c del Reglamento del Centro exige haber obtenido una calificación igual o "
                                  "superior a 2 puntos en al menos dos convocatorias de la asignatura, y el artículo 4.d "
                                  "permite examinarla de forma excepcional si la nota media del expediente es igual o "
                                  f"superior a 6,5 puntos. {la.capitalize()} {inter} solo la ha obtenido en {dos} de las "
                                  f"{len(conv)} convocatorias ({lista}) y su nota media es de {nota(media)}, por lo que no "
                                  "cumple el requisito ni procede la excepción."))
        pend12 = exp["primer_y_segundo_curso"]
        ok = extra is None
        reqs.append(req("Primer y segundo curso superados", "Art. 4.e del Reglamento de la EII", ok,
                        ("Tiene superadas todas las asignaturas de primer y segundo curso." if pend12.startswith("Todas") else
                         f"Solo le queda {asignatura} de primer y segundo curso, y está incluida en la solicitud (excepción del art. 4.e)."
                         ) if ok else f"Tiene pendiente {extra}, de {CURSO[extra]}.º curso, que no está incluida en la solicitud.",
                        [(D_EII, "4")]))
        if ok:
            frases.append((True, "Tiene superadas todas las asignaturas de los dos primeros cursos (artículo 4.e)."
                           if pend12.startswith("Todas") else
                           f"La única asignatura que le queda de los dos primeros cursos es {asignatura}, incluida en la "
                           "solicitud, por lo que se cumple la excepción del artículo 4.e."))
        else:
            frases.append((False, "El artículo 4.e del Reglamento del Centro exige haber superado todas las asignaturas de "
                                  "los dos primeros cursos o tener pendiente solo una, si se incluye en la solicitud. "
                                  f"{la.capitalize()} {inter} tiene pendiente {extra}, de {CURSO[extra]}.º curso, que no "
                                  "incluye en la solicitud, por lo que no cumple el requisito."))
        # Asignatura compensable (art. 5 y Listado, con parejas)
        if asignatura in ("Prácticas Externas", "Trabajo Fin de Grado"):
            reqs.append(req("Asignatura compensable", "Art. 5 del Reglamento de la EII; Listado de Asignaturas No Compensables",
                            False, f"{asignatura} no es compensable (art. 5.a y 5.b).", [(D_EII, "5"), (D_LIS, "")]))
            frases.append((False, f"El artículo 5 del Reglamento del Centro excluye de la compensación las Prácticas "
                                  f"Externas y el Trabajo Fin de Título, por lo que no procede compensar {asignatura}."))
        elif rama == "pareja":
            par = PAREJA[asignatura]
            reqs.append(req("Asignatura compensable", "Art. 5.c del Reglamento de la EII; Listado de Asignaturas No Compensables",
                            False, f"{asignatura} forma pareja no compensable con {par} (competencia "
                                   f"{COMPETENCIA_PAREJA[asignatura]}), que ya le fue compensada.", [(D_EII, "5"), (D_LIS, "")]))
            frases.append((False, "El artículo 5.c del Reglamento del Centro excluye de la compensación las asignaturas que "
                                  "establezca la Comisión de Asesoramiento Docente de cada titulación atendiendo a las "
                                  "competencias del título. El Listado de Asignaturas No Compensables de la Escuela (Rev. 04, "
                                  f"de 5 de mayo de 2023) establece que, en el Grado en Ingeniería Física y Matemática, "
                                  f"{asignatura} y {par} no pueden ser compensadas por un mismo estudiante (competencia "
                                  f"{COMPETENCIA_PAREJA[asignatura]}). {la.capitalize()} {inter} tiene compensada {par}, por "
                                  f"lo que no procede compensar {asignatura}."))
        else:
            par = PAREJA.get(asignatura)
            extra_par = (f" La asignatura con la que forma pareja no compensable, {par}, está superada sin compensación."
                         if par else "")
            reqs.append(req("Asignatura compensable", "Art. 5 del Reglamento de la EII; Listado de Asignaturas No Compensables",
                            True, "En este grado solo son no compensables las Prácticas Externas y el TFG, además de las "
                                  "parejas del Listado." + extra_par, [(D_EII, "5"), (D_LIS, "")]))
            frases.append((True, "La asignatura no está excluida de la compensación por el artículo 5 del Reglamento del "
                                 "Centro ni por el Listado de Asignaturas No Compensables." + extra_par))
        ok = previos + ects <= 14.4
        reqs.append(req("Límite del 6 % de la titulación", "Art. 3 del Reglamento de la EII", ok,
                        f"El 6 % de 240 son 14,4 créditos; solicita {ects}"
                        + (f" y tiene {previos} ya compensados: {previos + ects}." if previos else " y no tiene otras asignaturas compensadas."),
                        [(D_EII, "3")]))
        frases.append((ok, f"Los {ects} créditos solicitados" + (f", junto con los {previos} ya compensados," if previos else "")
                           + (" no superan el límite del 6 % de los créditos de la titulación (artículo 3)." if ok else
                              f" suman {previos + ects} y superan el límite del 6 % de los créditos de la titulación, "
                              "14,4 créditos, que fija el artículo 3 del Reglamento del Centro.")))
        return reqs, frases

    # ---- régimen 2026
    reqs.append(req("Plazo de presentación", "Plazos de evaluación compensatoria de la EII 2026-2027; art. 7.1 del Reglamento 1/2026",
                    True, f"Presentada el {en_letra(fecha)}, en el plazo abierto todo el curso desde el 8 de enero de 2027.",
                    [(D_PLA, ""), (D_R26, "7")]))
    reqs.append(req("Titulación de grado", "Art. 1 del Reglamento 1/2026", True,
                    "Es un grado oficial; no es estudiantado de movilidad entrante, de homologación, de máster ni de título propio.",
                    [(D_R26, "1")]))
    sup = exp["creditos_superados"]
    ok = sup >= 180
    reqs.append(req("75 % de los créditos de la titulación", "Art. 4.1 del Reglamento 1/2026; Tabla resumen de la EII", ok,
                    f"Ha superado {sup} de 240 créditos; se exigen 180.", [(D_R26, "4"), (D_TAB, "")]))
    frases.append((ok, f"{la.capitalize()} {inter} ha superado {sup} créditos, "
                       + ("más del 75 % de los 240 de la titulación (180), como exige el artículo 4.1 del Reglamento." if ok else
                          "menos del 75 % de los 240 de la titulación (180) que exige el artículo 4.1 del Reglamento, por lo "
                          "que no cumple el requisito.")))
    reqs.append(req("Matrícula en la asignatura", "Art. 4.2 del Reglamento 1/2026", matriculada,
                    "Tiene matrícula en la asignatura en el curso 2026/2027." if matriculada else
                    "No consta matrícula en la asignatura en el curso 2026/2027.", [(D_R26, "4")]))
    frases.append((matriculada, f"Está {p.a('matriculado')} en la asignatura y curso de los que solicita la compensación "
                                "(artículo 4.2)." if matriculada else
                   f"El artículo 4.2 exige estar matriculado en la asignatura y curso de los que se solicita la "
                   f"compensación, y {la} {inter} no lo está en el curso 2026/2027."))
    n_conv = len(conv)
    tres = [c["nota"] for c in conv if c["nota"] >= 3]
    ok_n, ok_3, ok_m = n_conv >= 3, bool(tres), media >= 6.0
    lista = lista_y([nota(c["nota"]) for c in conv])
    reqs.append(req("Presentado al menos a tres convocatorias", "Art. 4.3 del Reglamento 1/2026", ok_n,
                    f"{'' if ok_n else 'Solo '}{n_conv} convocatorias: {lista}.",
                    [(D_R26, "4")]))
    reqs.append(req("Al menos un 3,00 en alguna convocatoria", "Art. 4.3 del Reglamento 1/2026", ok_3,
                    f"{lista_y([nota(x) for x in tres])}." if ok_3 else f"Ninguna convocatoria llega a 3,00 ({lista}).",
                    [(D_R26, "4")]))
    reqs.append(req("Nota media de 6,00 o más", "Art. 4.3 del Reglamento 1/2026", ok_m, f"Nota media de {nota(media)}.",
                    [(D_R26, "4")]))
    if ok_n and ok_3 and ok_m:
        frases.append((True, f"Cumple las tres condiciones del artículo 4.3: se ha presentado a {n_conv} convocatorias de la "
                             f"asignatura, ha obtenido al menos un 3,00 en {'alguna' if len(tres) == 1 else f'{len(tres)} de ellas'} "
                             f"({lista_y([nota(x) for x in tres])}) y su nota media de expediente es de {nota(media)} "
                             "puntos, igual o superior a 6,00."))
    else:
        fallo = ("solo se ha presentado a " + ("dos convocatorias" if n_conv == 2 else f"{n_conv} convocatorias")
                 if not ok_n else
                 f"no ha obtenido un 3,00 en ninguna de sus {n_conv} convocatorias ({lista})" if not ok_3 else
                 f"su nota media de expediente es de {nota(media)} puntos")
        frases.append((False, "El artículo 4.3 exige cumplir todas las condiciones siguientes: haberse presentado al menos "
                              "a tres convocatorias de la asignatura, en ordinaria o extraordinaria; haber obtenido al "
                              "menos un 3,00 en alguna; y tener una nota media de expediente igual o superior a 6,00. "
                              f"{la.capitalize()} {inter} {fallo}, por lo que no cumple este requisito."))
    if asignatura in ("Prácticas Externas", "Trabajo Fin de Grado"):
        reqs.append(req("Asignatura compensable", "Arts. 2 y 3.3-3.4 del Reglamento 1/2026; relación de la Junta de Escuela de 13-07-26",
                        False, f"No cabe la compensación de {asignatura} (art. 3.3).", [(D_R26, "3")]))
        frases.append((False, "El artículo 3.3 del Reglamento dispone que no cabrá, en ningún caso, la compensación de las "
                              f"asignaturas de prácticas académicas externas ni del trabajo de fin de grado, por lo que no "
                              f"procede compensar {asignatura}."))
    elif asignatura in NO_COMP_2026:
        reqs.append(req("Asignatura compensable", "Arts. 2 y 3.3-3.4 del Reglamento 1/2026; relación de la Junta de Escuela de 13-07-26",
                        False, f"La relación aprobada por la Junta de Escuela el 13-07-26 incluye {asignatura} "
                               f"({SIGLA[asignatura]}) entre las no compensables del GIFM-40.", [(D_R26, "3"), (D_TAB, "")]))
        frases.append((False, "El artículo 3.4 del Reglamento dispone que no cabrá, en ningún caso, la compensación de las "
                              "asignaturas no compensables establecidas por el Centro, al que corresponde fijarlas según el "
                              "artículo 2.1. La relación aprobada por la Junta de la Escuela de Ingeniería Informática el 13 "
                              f"de julio de 2026 incluye {asignatura} entre las asignaturas no compensables del Grado en "
                              "Ingeniería Física y Matemática (Plan 40)."))
    else:
        reqs.append(req("Asignatura compensable", "Arts. 2 y 3.3-3.4 del Reglamento 1/2026; relación de la Junta de Escuela de 13-07-26",
                        True, f"{asignatura} no es PE ni TFG y no está en la relación de no compensables del GIFM-40 "
                              "aprobada el 13-07-26.", [(D_R26, "3"), (D_TAB, "")]))
        frases.append((True, f"{asignatura} no es una asignatura de prácticas académicas externas ni de trabajo de fin de "
                             "grado (artículo 3.3) ni figura en la relación de asignaturas no compensables del Grado en "
                             "Ingeniería Física y Matemática aprobada por la Junta de Escuela el 13 de julio de 2026 "
                             "(artículo 3.4)."))
    ok = previos + ects <= 15
    reqs.append(req("Límite de 15 ECTS en grados de 240 créditos", "Art. 3.2 del Reglamento 1/2026", ok,
                    f"Solicita {ects} ECTS" + (f" y tiene {previos} ya compensados: {previos + ects}." if previos
                                               else " y no tiene otras asignaturas compensadas."), [(D_R26, "3")]))
    frases.append((ok, f"Los {ects} créditos solicitados" + (f", junto con los {previos} ya compensados," if previos else "")
                       + (" no superan el límite de 15 ECTS de las titulaciones de 240 créditos (artículo 3.2)." if ok else
                          f" suman {previos + ects} y superan el límite de 15 ECTS de las titulaciones de 240 créditos que "
                          "fija el artículo 3.2 del Reglamento.")))
    return reqs, frases


def gold_extemporanea(p: Persona, fecha: date, fecha_res: date, asignatura: str, objeto: str, registro: str) -> dict:
    antes = fecha < ESPECIAL[0]
    nueva = ("del 2 al 16 de diciembre de 2026, para las solicitudes vinculadas a la convocatoria especial, o a partir del "
             "8 de enero de 2027, con el Reglamento 1/2026" if antes else "a partir del 8 de enero de 2027, que se "
             "resolverá conforme al Reglamento 1/2026")
    motivo = (f"Presentada el {en_letra(fecha)}, antes de que se abriera el plazo del 2 al 16 de diciembre de 2026 para las "
              "solicitudes vinculadas a la convocatoria especial." if antes else
              f"Presentada el {en_letra(fecha)}, después del plazo del 2 al 16 de diciembre para las solicitudes vinculadas "
              "a la convocatoria especial y antes del 8 de enero de 2027, cuando se abre el de la convocatoria ordinaria.")
    texto = documento_resolucion(
        f"RESOLUCIÓN DE {en_letra_mayus(fecha_res)} DE LA COMISIÓN DE COMPENSACIÓN DE LA ESCUELA DE INGENIERÍA INFORMÁTICA "
        f"POR LA QUE SE INADMITE LA SOLICITUD DE EVALUACIÓN COMPENSATORIA DE {p.don.upper()} {p.nombre.upper()}",
        vista(registro, p, fecha, objeto),
        ["La Administración del Edificio de Informática y Matemáticas publicó el 16 de noviembre de 2026 los plazos de "
         "evaluación compensatoria del curso 2026/2027: del 2 al 16 de diciembre de 2026 para las solicitudes vinculadas "
         "a la convocatoria especial y, a partir del 8 de enero de 2027, durante todo el curso académico para las "
         "vinculadas a la convocatoria ordinaria.",
         f"La solicitud de {p.la} {p.a('interesado')} se presentó el {en_letra(fecha)}."],
        ["El artículo 6 del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática (BOULPGC de 27 "
         "de enero de 2023) dispone que el procedimiento comienza con la apertura de un plazo de 10 días hábiles para la "
         "presentación de solicitudes, a partir del día siguiente a la firmeza de las actas de cada convocatoria. Para la "
         "convocatoria especial del curso 2026/2027 ese plazo transcurrió del 2 al 16 de diciembre de 2026.",
         f"El {R2026} (BOULPGC de 3 de julio de 2026), que mantiene abierto el plazo durante todo el curso académico "
         "(artículo 7.1), entra en vigor en la convocatoria ordinaria del curso 2026/2027 (disposición final), y la "
         "Escuela lo aplica a las solicitudes presentadas a partir del 8 de enero de 2027.",
         "La solicitud se presentó fuera de plazo, por lo que no procede estudiar los requisitos ni el fondo de la petición."],
        COMPETENCIA["2018"],
        f"Inadmitir por extemporánea la solicitud de evaluación compensatoria de la asignatura {asignatura} presentada por "
        f"{p.don} {p.nombre} el {en_letra(fecha)}. {p.la.capitalize()} {p.a('interesado')} podrá presentar una nueva "
        f"solicitud {nueva}.",
        PIE["2018"], firma(fecha_res, CARGO["2018"]))
    return {"decision": "inadmitir",
            "norma_aplicable": {"normas": ["Plazos de evaluación compensatoria de la EII, curso 2026/2027", *NORMAS_2018[:2]],
                                "motivo": f"El {en_letra(fecha)} no hay ningún plazo abierto: el de la convocatoria especial "
                                          "es del 2 al 16 de diciembre de 2026 y el de la ordinaria, ya con el Reglamento "
                                          "1/2026, se abre el 8 de enero de 2027. Hasta esa fecha el órgano competente es "
                                          "la Comisión de Compensación del régimen de 2018."},
            "organo": ORGANO["2018"], "recurso": RECURSO["2018"],
            "requisitos": [req("Plazo de presentación", "Plazos de evaluación compensatoria de la EII 2026-2027; art. 6 del Reglamento de la EII",
                               False, motivo, [(D_PLA, ""), (D_EII, "6")])],
            "resolucion": texto}


def gold_master(p: Persona, fecha: date, fecha_res: date, regimen: str, asignatura: str, objeto: str) -> dict:
    inter = p.a("interesado")
    if regimen == "2018":
        fund = ["El artículo 1 del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática limita "
                "su objeto a las titulaciones oficiales de Grado y dispone que la evaluación compensatoria no es de "
                "aplicación en los títulos de Máster. En el mismo sentido, el artículo 1.2 del Reglamento de Evaluación "
                "Compensatoria para las Titulaciones Oficiales de Grado de la ULPGC excluye los másteres, y también lo hace "
                "el artículo 1.2 del Reglamento 1/2026, que se aplicará desde la convocatoria ordinaria del curso 2026/2027."]
        norma_ref = ("Art. 1 del Reglamento de la EII; art. 1.2 del Reglamento de la ULPGC de 2018", [(D_EII, "1"), (D_U18, "1")])
        motivo_norma = (f"Presentada el {en_letra(fecha)}, en el plazo de la convocatoria especial: rige el régimen de "
                        "2018. Ninguno de los dos reglamentos (ni el 1/2026) se aplica a los másteres.")
        normas = NORMAS_2018[:2]
    else:
        fund = [f"El artículo 1 del {R2026} limita su objeto a las titulaciones oficiales de Grado y su apartado 2 dispone "
                "que la evaluación compensatoria no se aplica al estudiantado de másteres oficiales."]
        norma_ref = ("Art. 1 del Reglamento 1/2026", [(D_R26, "1")])
        motivo_norma = (f"Presentada el {en_letra(fecha)}, en el plazo de la convocatoria ordinaria: rige el Reglamento "
                        "1/2026, que excluye a los másteres.")
        normas = NORMAS_2026[:1]
    fund.append("La petición se refiere a un procedimiento que la normativa no prevé para la titulación que cursa "
                f"{p.la} {inter}, por lo que procede su inadmisión sin entrar en el estudio de los requisitos "
                f"(artículo 88.5 de la {LEY39}).")
    texto = documento_resolucion(
        f"RESOLUCIÓN DE {en_letra_mayus(fecha_res)} "
        + ("DE LA COMISIÓN DE COMPENSACIÓN" if regimen == "2018" else "DEL DIRECTOR")
        + f" DE LA ESCUELA DE INGENIERÍA INFORMÁTICA POR LA QUE SE INADMITE LA SOLICITUD DE EVALUACIÓN COMPENSATORIA DE "
          f"{p.don.upper()} {p.nombre.upper()}",
        vista(SEDE, p, fecha, objeto),
        [HECHO_PLAZO[regimen],
         f"{p.la.capitalize()} {inter} está {p.a('matriculado')} en el Máster Universitario en Ingeniería Informática, "
         "titulación oficial de máster que se imparte en la Escuela de Ingeniería Informática."],
        [FUND_NORMA[regimen], *fund], COMPETENCIA[regimen],
        f"Inadmitir la solicitud de evaluación compensatoria de la asignatura {asignatura} presentada por {p.don} "
        f"{p.nombre}, por no ser de aplicación la evaluación compensatoria en los títulos de Máster ("
        + ("artículo 1 del Reglamento de Evaluación Compensatoria de la Escuela de Ingeniería Informática)."
           if regimen == "2018" else "artículo 1.2 del Reglamento 1/2026)."),
        PIE[regimen], firma(fecha_res, CARGO[regimen]))
    plazo = (req("Plazo de presentación", "Plazos de evaluación compensatoria de la EII 2026-2027", True,
                 f"Presentada el {en_letra(fecha)}, "
                 + ("dentro del plazo del 2 al 16 de diciembre de 2026." if regimen == "2018"
                    else "en el plazo abierto todo el curso desde el 8 de enero de 2027."), [(D_PLA, "")]))
    return {"decision": "inadmitir", "norma_aplicable": {"normas": normas, "motivo": motivo_norma},
            "organo": ORGANO[regimen], "recurso": RECURSO[regimen],
            "requisitos": [plazo, req("Titulación de grado", norma_ref[0], False,
                                      "Es un máster oficial: la evaluación compensatoria no se aplica a los títulos de Máster.",
                                      norma_ref[1])],
            "resolucion": texto}


def gold_sin_firma(p: Persona, fecha: date, fecha_res: date, regimen: str, asignatura: str) -> dict:
    texto = requerimiento(
        f"evaluación compensatoria de la asignatura {asignatura} del {GRADO}", p, fecha, REGISTRO_GENERAL,
        f"la evaluación compensatoria de la asignatura {asignatura} (6 ECTS) del {GRADO}",
        ["Firmar la instancia y el formulario de solicitud de evaluación compensatoria de la Escuela, que se presentaron "
         "sin firma (artículo 66.1.e de la Ley 39/2015)."], fecha_res)
    normas = [f"{LEY39} (arts. 66 y 68)", *(NORMAS_2018[:2] if regimen == "2018" else NORMAS_2026[:1])]
    return {"decision": "requerir_subsanacion",
            "norma_aplicable": {"normas": normas,
                                "motivo": f"Presentada el {en_letra(fecha)}, en plazo: rige el régimen de "
                                          f"{'2018' if regimen == '2018' else 'Reglamento 1/2026'}. Los requisitos de la "
                                          "solicitud y su subsanación son los de la Ley 39/2015, que se aplica a todo procedimiento."},
            "organo": f"{ADMIN_EDIFICIO}, que tramita el procedimiento",
            "recurso": RECURSO_TRAMITE,
            "requisitos": [
                req("Plazo de presentación", "Plazos de evaluación compensatoria de la EII 2026-2027", True,
                    f"Presentada el {en_letra(fecha)}, " + ("dentro del plazo del 2 al 16 de diciembre de 2026."
                                                            if regimen == "2018" else "en el plazo abierto desde el 8 de enero de 2027."),
                    [(D_PLA, "")]),
                req("Firma de la solicitud", "Art. 66.1.e de la Ley 39/2015", False,
                    "La instancia y el formulario de la EII se presentaron en papel sin firmar, y no consta otro medio que "
                    "acredite la autenticidad de la voluntad del solicitante.", [(D_LEY, "66"), (D_LEY, "68")]),
            ],
            "resolucion": texto}
