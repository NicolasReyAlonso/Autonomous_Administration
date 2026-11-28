"""Cambio de turno o grupo (Directrices de la EII de 24-07-2023; Subdirección de Ordenación Académica).

Primer semestre 2026/2027: plazo del 11 de septiembre al 16 de octubre de 2026 (ficha de la
sede); resolución el 3 de noviembre con reclamación ante la Dirección del 4 al 11 de noviembre,
como en la Resolución de 4 de noviembre de 2024. Motivos de denegación de esa resolución:
1 sin motivación objetiva o sin acreditarla; 3 algún grupo de destino sin plazas (en bloque).
"""

from __future__ import annotations

import random
from datetime import date

from generador.comun import (SEDE, Persona, caso, documento, documento_resolucion, en_letra, firma, habiles_entre,
                             instancia, lista_y, persona, req, vista)
from generador.fecha_alternativa import CURSOS

TRAMITE, FICHA = "cambio_grupo", "2890472"
DIRECTRICES = ("Directrices para la resolución de las solicitudes de cambio de grupos docentes en las titulaciones de la "
               "Escuela de Ingeniería Informática (Junta de Escuela de 24 de julio de 2023)")
RES_2024 = ("Resolución de 4 de noviembre de 2024 del Subdirector de Ordenación Académica de la EII relativa a las "
            "solicitudes de cambio de grupo (motivos de denegación)")
D_DIR, D_RES = "Directrices para la resolución", "Resolución de 4 de noviembre de 2024"
NORMA = {"normas": [DIRECTRICES, RES_2024, "Plazo del trámite de la sede para el primer semestre 2026/2027: del 11 de "
                    "septiembre al 16 de octubre de 2026"],
         "motivo": "Las Directrices de 2023 siguen vigentes; el plazo es el publicado en la ficha de la sede."}
ORGANO = "Subdirección de Ordenación Académica de la Escuela de Ingeniería Informática"
RECURSO = ("Reclamación ante la Dirección del Centro por la Sede Electrónica (Instancia General), del 4 al 11 de "
           "noviembre de 2026 (plazo que abre la resolución, como en la de 4 de noviembre de 2024)")
FECHA_RES = date(2026, 11, 3)
PLAZO = (date(2026, 9, 11), date(2026, 10, 16))
FUND_DIRECTRICES = (
    "Las Directrices para la resolución de las solicitudes de cambio de grupos docentes en las titulaciones de la "
    "Escuela de Ingeniería Informática, aprobadas por la Junta de Escuela el 24 de julio de 2023, solo admiten a estudio "
    "las solicitudes que se encuentren en alguna de las situaciones que enumeran: necesidades específicas de apoyo "
    "educativo, mantener a la unidad familiar con hijos menores de seis años, tener contrato de trabajo oficial, ser "
    "deportista de alto nivel o alto rendimiento, cursar otros estudios oficiales, tener restricciones de horarios de "
    "transporte público y, para los cursos distintos del primero, el solapamiento de horarios por cursar asignaturas de "
    "cursos diferentes. Cada situación debe acreditarse con la documentación que se indica, y cualquier solicitud no "
    "contemplada o no justificada de forma conveniente será desestimada."
)
FUND_VACANTES = ("Según las mismas Directrices, las solicitudes se concederán siempre y cuando haya vacantes en los turnos "
                 "y grupos solicitados, y corresponde a la Subdirección de Ordenación Académica la aplicación y "
                 "priorización de los criterios.")
COMPETENCIA = ("En virtud de lo expuesto, esta Subdirección, responsable de la aplicación y priorización de los criterios "
               "establecidos en las citadas Directrices,")
PIE = ("Contra la presente resolución podrá presentarse reclamación ante la Dirección del Centro, a través de la Sede "
       "Electrónica de la ULPGC (Instancia General), desde el 4 hasta el 11 de noviembre de 2026.")
CARGO = "EL/LA SUBDIRECTOR/A DE ORDENACIÓN ACADÉMICA DE LA ESCUELA DE INGENIERÍA INFORMÁTICA"

# Situaciones previstas: (clave, texto en la instancia, documento, descripción en hechos/fundamentos)
SITUACIONES = [
    ("trabajo", "trabajo con contrato de lunes a viernes de {h} horas, por lo que no puedo asistir a las clases del turno de {turno}",
     ("Contrato de trabajo", "Contrato de trabajo con horario de lunes a viernes de {h} horas, del 1 de septiembre de 2026 al 31 de agosto de 2027."),
     "tener contrato de trabajo oficial", "su contrato de trabajo, que indica el horario laboral y las fechas de inicio y fin"),
    ("estudios", "curso también Enseñanzas Profesionales de Música en el Conservatorio Profesional, con clases que coinciden con mis grupos de {turno}",
     ("Justificante de matrícula y horario del Conservatorio Profesional de Música", "Matrícula en el curso 2026/2027, con clases de lunes a jueves de {h} horas."),
     "cursar otros estudios oficiales", "el justificante de matrícula y el horario del conservatorio"),
    ("idiomas", "estoy matriculad{o} en la Escuela Oficial de Idiomas y sus clases coinciden con mis grupos de {turno}",
     ("Justificante de matrícula y horario de la Escuela Oficial de Idiomas", "Matrícula en el nivel C1 de inglés en el curso 2026/2027, con clases de {h} horas."),
     "cursar otros estudios oficiales", "el justificante de matrícula y el horario de la Escuela Oficial de Idiomas"),
    ("hijos", "tengo a mi cargo un hijo menor de seis años y no puedo asistir a las clases del turno de {turno}",
     ("Libro de familia y certificado de escolarización", "Hijo nacido en 2022, escolarizado en horario de {h} horas."),
     "mantener a la unidad familiar en primera línea, con hijos menores de seis años", "el libro de familia y el certificado de escolarización"),
    ("deportista", "soy deportista de alto rendimiento y mis entrenamientos coinciden con el turno de {turno}",
     ("Certificado de la Federación Canaria", "Deportista de alto rendimiento con entrenamientos obligatorios de {h} horas."),
     "ser deportista de alto nivel o alto rendimiento", "el certificado de la federación con la justificación del horario de entrenamiento"),
    ("transporte", "vivo en un municipio desde el que el transporte público no me permite llegar a las clases del turno de {turno}",
     ("Certificado de empadronamiento y horario de guaguas", "Empadronamiento fuera del área metropolitana; la primera guagua llega al campus a las 10:15."),
     "tener restricciones de horarios de transporte público", "el certificado de empadronamiento y el horario oficial del transporte público"),
    ("solapamiento", "estoy matriculad{o} en asignaturas de cursos diferentes cuyos horarios se solapan en el turno de {turno}",
     ("Horario con los solapamientos marcados", "Horario con los solapamientos entre las asignaturas de los dos cursos."),
     "el solapamiento de horarios por cursar asignaturas de cursos diferentes", "el horario con los solapamientos"),
]
NO_PREVISTAS = [
    "por la tarde rindo menos y la mayoría de mis compañeros de clase están en el turno de mañana",
    "prefiero el turno de {turno_destino} porque me organizo mejor",
    "voy a una academia privada de inglés por las {turno_tarde}",
    "entreno en un club de baloncesto (no federado como alto rendimiento) y los entrenamientos coinciden con el turno de {turno}",
    "quiero estar en el mismo grupo que mi pareja",
]
RAMAS = [("estimar", "estimar", 4), ("no_prevista", "desestimar", 3), ("sin_plazas", "desestimar", 2),
         ("fuera_plazo", "inadmitir", 2), ("solapamiento_primero", "desestimar", 1)]


def generar(rng: random.Random, n: int, prefijo: str = "gen-cg") -> list[dict]:
    pesos = [r[2] for r in RAMAS]
    return [construir(rng, f"{prefijo}-{i:04d}", *rng.choices(RAMAS, pesos)[0][:2]) for i in range(1, n + 1)]


def construir(rng: random.Random, id_: str, rama: str, decision: str) -> dict:
    p = persona(rng)
    curso = 1 if rama == "solapamiento_primero" else rng.choice((1, 2, 2, 3, 3, 4))
    actual = rng.choice(("mañana", "tarde"))
    destino = "tarde" if actual == "mañana" else "mañana"
    asignaturas = rng.sample(CURSOS[curso], rng.randint(1, 3))
    plazas = [rng.randint(1, 8) for _ in asignaturas]
    if rama == "sin_plazas":
        plazas[rng.randrange(len(plazas))] = 0
    fecha = (habiles_entre(date(2026, 10, 19), date(2026, 10, 30), rng) if rama == "fuera_plazo"
             else habiles_entre(*PLAZO, rng))

    if rama == "solapamiento_primero":
        sit = next(s for s in SITUACIONES if s[0] == "solapamiento")
    else:
        sit = rng.choice([s for s in SITUACIONES if s[0] != "solapamiento" or curso > 1])
    h = "8:00 a 14:00" if actual == "mañana" else "15:00 a 21:00"
    fmt = dict(h=h, turno=actual, turno_destino=destino, turno_tarde="tardes", o="a" if p.mujer else "o")
    if rama == "no_prevista":
        motivo = rng.choice(NO_PREVISTAS).format(**fmt)
        docs = []
    else:
        motivo = sit[1].format(**fmt)
        docs = [documento(*[x.format(**fmt) for x in sit[2]])]
    docs = [documento("Formulario de solicitud de cambio de grupo de la EII",
                      f"Cambio del grupo de {actual} al grupo de {destino} en {lista_y(asignaturas)}."),
            documento("Horario marcando las asignaturas afectadas",
                      f"Horario del {curso}.º curso del GII con las asignaturas marcadas en el turno de {actual}."), *docs]
    expone = (f"Que soy estudiante de {curso}.º curso del Grado en Ingeniería Informática y que {motivo}.")
    solicita = f"Que se me cambie del grupo de {actual} al de {destino} en {lista_y(asignaturas)}."
    ins = instancia("Cambio de turno o grupo (Administración del Edificio de Informática y Matemáticas)", SEDE, fecha, p,
                    "Subdirección de Ordenación Académica de la Escuela de Ingeniería Informática",
                    "Solicitud de cambio de turno o grupo", expone, solicita, docs)
    exp = {"titulacion": "Grado en Ingeniería Informática (Plan 41)", "centro": "Escuela de Ingeniería Informática",
           "curso": curso,
           "cambios_solicitados": [{"asignatura": a, "grupo_actual": actual, "grupo_solicitado": destino,
                                    "plazas_libres_destino": n} for a, n in zip(asignaturas, plazas)]}
    gold = gold_caso(p, rama, decision, fecha, curso, actual, destino, asignaturas, plazas, sit, motivo)
    return caso(id_, TRAMITE, FICHA, f"Generado. Rama {rama}: {decision}.", ins, exp, [], gold, rama)


def gold_caso(p: Persona, rama, decision, fecha, curso, actual, destino, asignaturas, plazas, sit, motivo) -> dict:
    inter, la = p.a("interesado"), p.la
    objeto = (f"el cambio del grupo de {actual} al de {destino} en {'la asignatura' if len(asignaturas) == 1 else 'las asignaturas'} "
              f"{lista_y(asignaturas)} del Grado en Ingeniería Informática")
    titulo = ("RESOLUCIÓN DE 3 DE NOVIEMBRE DE 2026 DE LA SUBDIRECCIÓN DE ORDENACIÓN ACADÉMICA DE LA ESCUELA DE INGENIERÍA "
              f"INFORMÁTICA RELATIVA A LA SOLICITUD DE CAMBIO DE GRUPO DE {p.don.upper()} {p.nombre.upper()}")
    hecho_plazo = ("La Escuela de Ingeniería Informática abrió el plazo de solicitudes de cambio de turno o grupo del primer "
                   "semestre del curso 2026/2027 del 11 de septiembre al 16 de octubre de 2026, a través de la Sede "
                   "Electrónica." + ("" if rama == "fuera_plazo" else f" La solicitud se presentó el {en_letra(fecha)}."))
    r_plazo = req("Plazo de presentación", f"{DIRECTRICES}; ficha del trámite en la sede", rama != "fuera_plazo",
                  (f"Presentada el {en_letra(fecha)}, dentro del plazo del 11 de septiembre al 16 de octubre." if rama != "fuera_plazo"
                   else f"Presentada el {en_letra(fecha)}; el plazo terminó el 16 de octubre."), [(D_DIR, "")])
    r_claro = req("Cambio especificado con claridad", RES_2024, True, "Indica asignaturas, grupo actual y grupo de destino.",
                  [(D_RES, "")])
    if rama == "fuera_plazo":
        texto = documento_resolucion(
            titulo, vista(SEDE, p, fecha, objeto),
            [hecho_plazo, f"La solicitud de {la} {inter} se presentó el {en_letra(fecha)}."],
            ["Las Directrices para la resolución de las solicitudes de cambio de grupos docentes en las titulaciones de la "
             "Escuela de Ingeniería Informática, aprobadas por la Junta de Escuela el 24 de julio de 2023, establecen que "
             "las solicitudes deberán realizarse utilizando los procedimientos y plazos explícita y públicamente "
             "establecidos y comunicados por la Escuela a comienzos de cada semestre.",
             "La solicitud se presentó fuera del plazo establecido para el primer semestre, que terminó el 16 de octubre "
             "de 2026, por lo que no procede estudiar el fondo de la petición."],
            COMPETENCIA, f"Inadmitir por extemporánea la solicitud de cambio de grupo presentada por {p.don} {p.nombre} el "
                         f"{en_letra(fecha)}.", PIE, firma(FECHA_RES, CARGO))
        return {"decision": decision, "norma_aplicable": NORMA, "organo": ORGANO, "recurso": RECURSO,
                "requisitos": [r_plazo], "resolucion": texto}

    plazas_txt = lista_y([f"{n} en {a}" if n else f"ninguna en {a}" for a, n in zip(asignaturas, plazas)])
    hechos = [hecho_plazo]
    if rama == "no_prevista":
        hechos.append(f"{la.capitalize()} {inter}, estudiante de {curso}.º curso, motiva su petición en que {motivo}. No "
                      "alega ni acredita ninguna otra circunstancia.")
        fundamentos = [FUND_DIRECTRICES,
                       f"Lo alegado por {la} {inter} no es una de las situaciones previstas en las Directrices, por lo que "
                       "no presenta una motivación objetiva que justifique el cambio. Por ello no procede valorar la "
                       "existencia de vacantes."]
        resuelve = (f"Denegar a {p.don} {p.nombre} el cambio de grupo solicitado en {lista_y(asignaturas)}, por no presentar "
                    "una motivación objetiva que lo justifique conforme a las Directrices para la resolución de las "
                    "solicitudes de cambio de grupos docentes de la Escuela de Ingeniería Informática.")
        reqs = [r_plazo, req("Situación contemplada", DIRECTRICES, False,
                             "Lo que alega no es ninguna de las situaciones previstas en las Directrices.", [(D_DIR, "")]), r_claro]
    elif rama == "solapamiento_primero":
        hechos.append(f"{la.capitalize()} {inter}, estudiante de primer curso, motiva su petición en el solapamiento de "
                      "horarios entre asignaturas de cursos diferentes.")
        fundamentos = [FUND_DIRECTRICES,
                       "El solapamiento de horarios por cursar asignaturas de cursos diferentes solo se contempla para los "
                       f"estudiantes de los cursos distintos del primero, y {la} {inter} es de primer curso, por lo que no "
                       "presenta una motivación objetiva que justifique el cambio conforme a las Directrices."]
        resuelve = (f"Denegar a {p.don} {p.nombre} el cambio de grupo solicitado en {lista_y(asignaturas)}, por no "
                    "encontrarse en ninguna de las situaciones previstas para los estudiantes de primer curso en las "
                    "Directrices para la resolución de las solicitudes de cambio de grupos docentes de la Escuela de "
                    "Ingeniería Informática.")
        reqs = [r_plazo, req("Situación contemplada", DIRECTRICES, False,
                             "El solapamiento entre cursos solo se contempla a partir de segundo curso.", [(D_DIR, "")]), r_claro]
    else:
        hechos.append(f"{la.capitalize()} {inter}, estudiante de {curso}.º curso, motiva su petición en que {motivo}, y lo "
                      f"acredita con {sit[4]}.")
        hechos.append(f"Los grupos de {destino} solicitados tienen las siguientes plazas libres: {plazas_txt}.")
        r_sit = req("Situación contemplada", DIRECTRICES, True, f"Situación prevista: {sit[3]}.", [(D_DIR, "")])
        r_acr = req("Situación acreditada", DIRECTRICES, True, f"Aporta {sit[4]}.", [(D_DIR, "")])
        if rama == "sin_plazas":
            llenos = [a for a, n in zip(asignaturas, plazas) if not n]
            fundamentos = [FUND_DIRECTRICES, FUND_VACANTES,
                           f"{la.capitalize()} {inter} se encuentra en una de las situaciones previstas, {sit[3]}, y la "
                           "acredita. Sin embargo, " + ("uno de los grupos de destino solicitados no tiene" if len(asignaturas) > 1
                                                        else "el grupo de destino solicitado no tiene")
                           + " capacidad para admitir más estudiantes" + (
                               " y, como las solicitudes se conceden o deniegan en bloque, según el criterio aplicado por "
                               "esta Subdirección en su Resolución de 4 de noviembre de 2024," if len(asignaturas) > 1 else ",")
                           + " procede denegar la solicitud."]
            resuelve = (f"Denegar a {p.don} {p.nombre} el cambio de grupo solicitado en {lista_y(asignaturas)}, por no haber "
                        f"plazas libres en el grupo de {destino} de {lista_y(llenos)}.")
            reqs = [r_plazo, r_sit, r_acr, r_claro,
                    req("Vacantes en todos los grupos de destino", f"{DIRECTRICES}; {RES_2024}", False,
                        f"El grupo de {destino} de {lista_y(llenos)} no tiene plazas"
                        + ("; las solicitudes se conceden o deniegan en bloque." if len(asignaturas) > 1 else "."),
                        [(D_DIR, ""), (D_RES, "")])]
        else:
            fundamentos = [FUND_DIRECTRICES, FUND_VACANTES,
                           f"{la.capitalize()} {inter} se encuentra en una de las situaciones previstas, {sit[3]}, y la "
                           f"acredita con {sit[4]}. Hay vacantes en "
                           + ("el grupo de destino" if len(asignaturas) == 1 else f"los {len(asignaturas)} grupos de destino")
                           + ", por lo que procede conceder el cambio."]
            resuelve = (f"Conceder a {p.don} {p.nombre} el cambio del grupo de {actual} al grupo de {destino} en "
                        f"{'la asignatura' if len(asignaturas) == 1 else 'las asignaturas'} {lista_y(asignaturas)} del "
                        "Grado en Ingeniería Informática, para el primer semestre del curso 2026/2027.")
            reqs = [r_plazo, r_sit, r_acr, r_claro,
                    req("Vacantes en todos los grupos de destino", f"{DIRECTRICES}; {RES_2024}", True,
                        f"Plazas libres en los grupos de {destino}: {plazas_txt}.", [(D_DIR, ""), (D_RES, "")])]
    texto = documento_resolucion(titulo, vista(SEDE, p, fecha, objeto), hechos, fundamentos, COMPETENCIA, resuelve, PIE,
                                 firma(FECHA_RES, CARGO))
    return {"decision": decision, "norma_aplicable": NORMA, "organo": ORGANO, "recurso": RECURSO, "requisitos": reqs,
            "resolucion": texto}
