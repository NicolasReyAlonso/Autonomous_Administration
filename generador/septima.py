"""Séptima convocatoria (art. 10 de las Normas de Progreso y Permanencia; Comisión de Permanencia).

Simplificación: la concesión es discrecional («estudio individualizado»); aquí toda petición
motivada de quien ha agotado seis convocatorias calificadas se concede.
"""

from __future__ import annotations

import random
from datetime import date

from generador.comun import (ADMIN_EDIFICIO, LEY39, RECURSO_TRAMITE, SEDE, Persona, caso, documento,
                             documento_resolucion, en_letra, en_letra_mayus, firma, habiles_entre, instancia, lista_y,
                             nota, persona, req, requerimiento, sumar_habiles, vista)
from generador.fecha_alternativa import CURSOS

TRAMITE, FICHA = "septima_convocatoria", "2897040"
CODIGOS = {a: str(40951 + i) for i, a in enumerate(
    ["Álgebra y Geometría", "Matemática Discreta", "Fundamentos de Programación I", "Fundamentos de Computadores",
     "Habilidades Profesionales para Ingenieros", "Matemáticas para la Computación", "Fundamentos Físicos de la Informática",
     "Fundamentos de Programación II", "Estructura de Computadores", "La Empresa y sus Procesos", "Métodos Estadísticos",
     "Algoritmos y Programación", "Tecnologías de Programación", "Periféricos e Interfaces", "Ingeniería del Software I",
     "Métodos Numéricos", "Estructura de Datos y Programación", "Base de Datos I", "Arquitectura de Computadores",
     "Fundamentos de los sistemas operativos", "Redes de computadores", "Administración de sistemas operativos",
     "Base datos II", "Fundamentos de los sistemas inteligentes", "Ingeniería del software II",
     "Administración de servicios en red", "Virtualización y procesamiento distribuido"])}
ASIGNATURAS = list(CODIGOS)
CURSO = {a: c for c, lista in CURSOS.items() for a in lista}
PYP = ("Normas de Progreso y Permanencia en las Titulaciones Oficiales de Grado y Máster de la ULPGC (aprobadas el "
       "17 de octubre de 2024, modificadas por el Pleno del Consejo Social el 2 de abril de 2025)")
PYP_CORTA = "Normas de Progreso y Permanencia en las Titulaciones Oficiales de Grado y Máster de la ULPGC"
D_PYP = "Normativa de Progreso y Permanencia en las titulaciones oficiales"
NORMA = {"normas": [f"{PYP}: arts. 10, 16 y 18 y disposición transitoria tercera"],
         "motivo": "Texto vigente desde la modificación de 2 de abril de 2025; el texto original de 2024 no se aplica."}
ORGANO = "Comisión de Permanencia de la ULPGC"
RECURSO = ("Alzada ante el Consejo Social, en el plazo de un mes desde el día siguiente a su comunicación (art. 18 de "
           "las Normas de Progreso y Permanencia; arts. 121 y 122 de la Ley 39/2015)")
COMPETENCIA = (f"En virtud de lo expuesto, esta Comisión, en uso de las competencias atribuidas por los artículos 10.3 y "
               f"16.a) de las {PYP_CORTA},")
PIE = ("Contra la presente resolución podrá interponerse recurso de alzada ante el Consejo Social de la Universidad de "
       "Las Palmas de Gran Canaria en el plazo de un mes a contar desde el día siguiente a su comunicación, de "
       f"conformidad con el artículo 18 de las {PYP_CORTA} y los artículos 121 y 122 de la {LEY39}, sin perjuicio de "
       "cualquier otro recurso que se estime procedente.")
CARGO = "EL/LA PRESIDENTE/A DE LA COMISIÓN DE PERMANENCIA DE LA UNIVERSIDAD DE LAS PALMAS DE GRAN CANARIA"
FUND_SEIS = (f"El artículo 10.1 de las {PYP_CORTA} dispone que el estudiantado dispondrá de seis convocatorias para "
             "superar cada asignatura y que, cuando en el acta el estudiante sea calificado como «no presentado», no se "
             "computará la convocatoria. Según la disposición transitoria tercera, en cada asignatura solo constan las "
             "convocatorias efectivamente calificadas.")
FUND_SEPTIMA = ("El artículo 10.3 permite al estudiante que haya agotado las seis convocatorias solicitar una séptima, que "
                "será autorizada por la Comisión de Permanencia de la ULPGC; la petición debe ser motivada y su concesión, "
                "objeto de estudio individualizado.")
CURSOS_CONV = [(c, t) for c in ("2022/2023", "2023/2024", "2024/2025", "2025/2026") for t in ("ordinaria", "extraordinaria")]
CUANTAS = {1: "una convocatoria", 2: "dos convocatorias", 3: "tres convocatorias"}
RAMAS = [("estimar", "estimar", 4), ("estimar_sin_documentos", "estimar", 1), ("sin_motivar", "requerir_subsanacion", 3),
         ("no_presentados", "desestimar", 3), ("cinco", "desestimar", 2)]
MOTIVOS = [  # (texto en la instancia, documento, frase del fundamento)
    ("del {a} al {b} estuve hospitalizad{o}, días antes del examen de la última convocatoria, al que me presenté igualmente",
     ("Informe de alta hospitalaria", "Ingreso hospitalario del {a} al {b}."),
     "la última convocatoria se vio afectada por una hospitalización"),
    ("he trabajado a jornada completa durante los dos últimos cursos para costear mis estudios",
     ("Contrato de trabajo", "Contrato a jornada completa, de lunes a viernes de 8:00 a 15:00 horas, desde el 1 de septiembre de 2024."),
     "ha compatibilizado los estudios con un trabajo a jornada completa"),
    ("durante el último curso he tenido que cuidar de un familiar dependiente",
     ("Resolución de reconocimiento de la situación de dependencia de un familiar de primer grado", "Grado II de dependencia, reconocido en 2025."),
     "ha tenido a su cargo el cuidado de un familiar dependiente"),
    ("en los últimos meses he estado en tratamiento médico por una enfermedad que me impidió preparar la asignatura",
     ("Informe médico", "Tratamiento médico entre marzo y julio de 2026."),
     "su rendimiento se vio afectado por una enfermedad"),
]


def generar(rng: random.Random, n: int, prefijo: str = "gen-sep") -> list[dict]:
    pesos = [r[2] for r in RAMAS]
    return [construir(rng, f"{prefijo}-{i:04d}", *rng.choices(RAMAS, pesos)[0][:2]) for i in range(1, n + 1)]


def construir(rng: random.Random, id_: str, rama: str, decision: str) -> dict:
    p = persona(rng)
    asignatura = rng.choice(ASIGNATURAS)
    codigo = CODIGOS[asignatura]
    fecha = habiles_entre(date(2026, 9, 1), date(2026, 10, 30), rng)
    fecha_res = sumar_habiles(fecha, rng.randint(1, 3) if rama == "sin_motivar" else rng.randint(12, 25))

    # Convocatorias: seis (las últimas de los cursos 2022/2023-2025/2026); con «no presentado» o solo cinco
    convs = CURSOS_CONV[2:] if rng.random() < 0.6 else CURSOS_CONV[1:7]
    if rama == "cinco":
        convs = convs[1:]
    notas_ = sorted(round(rng.uniform(0.8, 4.8), 1) for _ in convs)
    if rng.random() < 0.4:
        rng.shuffle(notas_)
    resultados: list = list(notas_)
    if rama == "no_presentados":
        for i in rng.sample(range(len(resultados)), rng.choice((1, 2, 2, 3))):
            resultados[i] = "No presentado"
    lista_conv = [{"curso": c, "convocatoria": t, "nota": r} for (c, t), r in zip(convs, resultados)]
    calificadas = [r for r in resultados if r != "No presentado"]

    superados = rng.choice((150, 168, 186, 198, 210, 216))
    pendientes = [{"asignatura": asignatura, "codigo": codigo, "curso": CURSO[asignatura], "ects": 6, "convocatorias": lista_conv}]
    if superados >= 210:
        pendientes += [{"asignatura": "Prácticas Externas", "curso": 4, "ects": 12, "convocatorias": []},
                       {"asignatura": "Trabajo Fin de Grado", "curso": 4, "ects": 12, "convocatorias": []}][: (240 - superados - 6) // 12]
    exp = {"titulacion": "Grado en Ingeniería Informática (Plan 41)", "centro": "Escuela de Ingeniería Informática",
           "dedicacion": rng.choice(["Tiempo completo", "Tiempo completo", "Tiempo parcial"]), "creditos_titulacion": 240,
           "creditos_superados": superados, "nota_media": round(rng.uniform(5.6, 7.4), 1), "pendientes": pendientes}

    motivo = rng.choice(MOTIVOS)
    hosp_a = date(2026, rng.choice((6, 7)), rng.randint(1, 20))
    hosp_b = hosp_a.replace(day=hosp_a.day + rng.randint(2, 5))
    fmt = dict(a=en_letra(hosp_a), b=en_letra(hosp_b), o="a" if p.mujer else "o")
    ultimas = len(pendientes) == 1 or all(x["asignatura"] in ("Prácticas Externas", "Trabajo Fin de Grado") for x in pendientes[1:])
    agotadas = "las seis convocatorias" if rama != "cinco" else "las convocatorias"
    if rama == "sin_motivar":
        expone = rng.choice([f"Que he agotado {agotadas} de la asignatura {asignatura}.",
                             f"Que no he superado la asignatura {asignatura} en las seis convocatorias de que disponía."])
        docs = []
    else:
        expone = (f"Que he agotado {agotadas} de la asignatura {asignatura} sin superarla. Que "
                  + motivo[0].format(**fmt) + "."
                  + (f" Que solo me quedan pendientes esta asignatura{' y las Prácticas Externas y el Trabajo Fin de Grado' if len(pendientes) > 1 else ''}."
                     if ultimas else ""))
        docs = [] if rama == "estimar_sin_documentos" else [documento(motivo[1][0], motivo[1][1].format(**fmt))]
    ins = instancia("Solicitud de séptima convocatoria (Administración del Edificio de Informática y Matemáticas)", SEDE,
                    fecha, p, "Comisión de Permanencia de la ULPGC", "Solicitud de séptima convocatoria", expone,
                    f"Que se me autorice una séptima convocatoria de la asignatura {asignatura} en el curso 2026/2027.", docs)

    gold = gold_caso(p, rama, decision, fecha, fecha_res, asignatura, codigo, lista_conv, calificadas, exp, motivo,
                     docs, ultimas)
    notas = f"Generado. Rama {rama}: {decision}. La concesión es discrecional: toda petición motivada se concede."
    return caso(id_, TRAMITE, FICHA, notas, ins, exp, [], gold, rama)


def resultado(r) -> str:
    return "no presentado" if r == "No presentado" else nota(r)


def gold_caso(p: Persona, rama, decision, fecha, fecha_res, asignatura, codigo, lista_conv, calificadas, exp, motivo,
              docs, ultimas) -> dict:
    inter, la = p.a("interesado"), p.la
    n_calif = len(calificadas)
    r_seis = req("Seis convocatorias agotadas", "Arts. 10.1 y 10.3 y disposición transitoria tercera de las Normas de "
                 "Progreso y Permanencia", n_calif >= 6,
                 "Seis convocatorias calificadas, ninguna como no presentado." if n_calif >= 6 else
                 (f"De las {len(lista_conv)} convocatorias, {len(lista_conv) - n_calif} figuran como no presentado: solo "
                  f"computan {n_calif}." if n_calif < len(lista_conv) else f"Solo ha consumido {n_calif} convocatorias."),
                 [(D_PYP, "10"), (D_PYP, "")])
    if rama == "sin_motivar":
        texto = requerimiento(f"séptima convocatoria de la asignatura {asignatura} del Grado en Ingeniería Informática",
                              p, fecha, SEDE,
                              f"la autorización de una séptima convocatoria de la asignatura {asignatura} ({codigo}) del "
                              "Grado en Ingeniería Informática",
                              [f"Motivar su petición, exponiendo las razones en que la funda, como exigen el artículo 10.3 "
                               f"de las {PYP_CORTA} y el artículo 66.1.c) de la Ley 39/2015.",
                               "Aportar, en su caso, la documentación que justifique dicha motivación."], fecha_res)
        return {"decision": decision,
                "norma_aplicable": {"normas": [f"{PYP}: art. 10.3", f"{LEY39} (arts. 66 y 68)"], "motivo": NORMA["motivo"]},
                "organo": f"{ADMIN_EDIFICIO}, que tramita el procedimiento en la sede", "recurso": RECURSO_TRAMITE,
                "requisitos": [r_seis, req("Petición motivada", "Art. 10.3 de las Normas de Progreso y Permanencia; art. "
                                           "66.1.c de la Ley 39/2015", False,
                                           "La solicitud no expone ninguna razón ni aporta documentación.",
                                           [(D_PYP, "10"), ("Ley 39/2015", "66"), ("Ley 39/2015", "68")])],
                "resolucion": texto}

    por_curso = {}
    for c in lista_conv:
        por_curso.setdefault(c["curso"], []).append(resultado(c["nota"]))
    trayectoria = "; ".join(f"{' y '.join(v)} en el curso {k}" for k, v in por_curso.items())
    hechos = [f"Según su expediente académico, en las {len(lista_conv)} convocatorias de la asignatura {la} {inter} "
              f"obtuvo los siguientes resultados: {trayectoria}.",
              f"Ha superado {exp['creditos_superados']} de los 240 créditos de la titulación"
              + (" y solo le queda pendiente esta asignatura" + (", además de las Prácticas Externas y el Trabajo Fin de Grado" if len(exp['pendientes']) > 1 else "")
                 if ultimas else "") + ".",
              f"{la.capitalize()} {inter} motiva su petición en que {motivo[2]}"
              + (f", y lo acredita con {docs[0]['nombre'][0].lower() + docs[0]['nombre'][1:]}." if docs
                 else ", aunque no aporta documentación.")]
    fundamentos = [FUND_SEIS, FUND_SEPTIMA]
    if decision == "estimar":
        fundamentos.append(f"{la.capitalize()} {inter} ha agotado seis convocatorias calificadas y su petición está "
                           "motivada. Estudiado su caso, " + motivo[2]
                           + (", y la asignatura es la última que le queda para finalizar la titulación salvo, en su caso, "
                              "las Prácticas Externas y el Trabajo Fin de Grado" if ultimas else "")
                           + ", por lo que procede autorizar la séptima convocatoria.")
        resuelve = (f"Autorizar a {p.don} {p.nombre} una séptima convocatoria de la asignatura {asignatura} ({codigo}) del "
                    "Grado en Ingeniería Informática, de la que podrá hacer uso en el curso académico 2026/2027. Conforme al "
                    f"artículo 10.1, podrá solicitar ser {p.a('evaluado')} por el tribunal nombrado para la asignatura por "
                    "la Escuela de Ingeniería Informática.")
        reqs = [r_seis,
                req("Petición motivada", "Art. 10.3 de las Normas de Progreso y Permanencia", True,
                    f"Motiva la petición: {motivo[2]}" + ("." if docs else " (sin aportar documentación, que solo es exigible si la hay)."),
                    [(D_PYP, "10")]),
                req("Estudio individualizado", "Art. 10.3 de las Normas de Progreso y Permanencia", True,
                    "La circunstancia alegada y su trayectoria justifican la concesión.", [(D_PYP, "10")])]
    else:
        quedan = 6 - n_calif
        fundamentos.append(
            (f"{len(lista_conv) - n_calif} de las convocatorias de {la} {inter} figuran como no presentado y no se computan, "
             f"por lo que solo ha consumido {n_calif} de las seis de que dispone." if n_calif < len(lista_conv) else
             f"{la.capitalize()} {inter} solo ha consumido {n_calif} de las seis convocatorias de que dispone.")
            + " Al no haber agotado las seis convocatorias, no concurre el presupuesto del artículo 10.3 y no procede "
              "autorizar una séptima.")
        fundamentos.append("A partir de la quinta convocatoria, el estudiante puede solicitar ser evaluado por un tribunal "
                           "conforme al reglamento que regula la evaluación del aprendizaje (artículo 10.1).")
        resuelve = (f"Denegar a {p.don} {p.nombre} la séptima convocatoria de la asignatura {asignatura} ({codigo}), por no "
                    f"haber agotado las seis convocatorias previstas en el artículo 10.1 de las {PYP_CORTA}. "
                    f"{la.capitalize()} {inter} dispone todavía de {CUANTAS[quedan]} "
                    "para superar la asignatura.")
        reqs = [r_seis]
    texto = documento_resolucion(
        f"RESOLUCIÓN DE {en_letra_mayus(fecha_res)} DE LA COMISIÓN DE PERMANENCIA DE LA UNIVERSIDAD DE LAS PALMAS DE GRAN "
        f"CANARIA POR LA QUE SE RESUELVE LA SOLICITUD DE SÉPTIMA CONVOCATORIA DE {p.don.upper()} {p.nombre.upper()}",
        vista(SEDE, p, fecha, f"una séptima convocatoria de la asignatura {asignatura} ({codigo}) del Grado en Ingeniería "
                              "Informática (Plan 41)"),
        hechos, fundamentos, COMPETENCIA, resuelve, PIE, firma(fecha_res, CARGO))
    return {"decision": decision, "norma_aplicable": NORMA, "organo": ORGANO, "recurso": RECURSO, "requisitos": reqs,
            "resolucion": texto}
