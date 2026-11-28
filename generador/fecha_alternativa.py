"""Fecha alternativa de examen por coincidencia de pruebas (art. 58 del Reglamento de Régimen
Interno de la EII; art. 24 del Reglamento de Evaluación de la ULPGC; Acuerdo de 15-12-2014).

Responde el profesorado: el de la asignatura del curso superior o, si una prueba es de
convocatoria oficial y la otra no, el de la que no lo es. Los calendarios son ficticios y el
curso de cada asignatura del GII (Plan 41) es una suposición (orden de los códigos).
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from generador.comun import (Persona, caso, en_letra, en_letra_mayus, firma, habiles_entre, instancia, persona, req,
                             sumar_habiles)

TRAMITE = "fecha_alternativa_examen"
GII = "Grado en Ingeniería Informática (Plan 41)"
CURSOS = {
    1: ["Álgebra y Geometría", "Matemática Discreta", "Fundamentos de Programación I", "Fundamentos de Computadores",
        "Habilidades Profesionales para Ingenieros",
        "Matemáticas para la Computación", "Fundamentos Físicos de la Informática", "Fundamentos de Programación II",
        "Estructura de Computadores", "La Empresa y sus Procesos"],
    2: ["Métodos Estadísticos", "Algoritmos y Programación", "Tecnologías de Programación", "Periféricos e Interfaces",
        "Ingeniería del Software I", "Métodos Numéricos", "Estructura de Datos y Programación", "Base de Datos I",
        "Arquitectura de Computadores", "Fundamentos de los sistemas operativos"],
    3: ["Redes de computadores", "Administración de sistemas operativos", "Base datos II",
        "Fundamentos de los sistemas inteligentes", "Ingeniería del software II", "Administración de servicios en red",
        "Virtualización y procesamiento distribuido", "Programación web y móvil", "Producción de software"],
    4: ["Informática gráfica", "Sistemas robóticos autónomos", "Visión por computador",
        "Programación de aplicaciones móviles nativas", "Computación en la nube", "Internet de las cosas",
        "Los sistemas de información en la organización"],
}
ORDINALES_CURSO = {1: "primer", 2: "segundo", 3: "tercer", 4: "cuarto"}
# Periodo oficial (ficticio salvo que la especial es en noviembre) y días en que puede caer el
# examen: elegidos para que los cinco días hábiles previos no crucen ningún festivo (6 de enero,
# 24 de junio), que el modelo no tiene por qué conocer.
CONVOCATORIAS = {
    "ordinaria": ((date(2027, 1, 11), date(2027, 2, 5)), (date(2027, 1, 18), date(2027, 2, 2))),
    "extraordinaria": ((date(2027, 6, 28), date(2027, 7, 16)), (date(2027, 7, 2), date(2027, 7, 13))),
    "especial": ((date(2026, 11, 16), date(2026, 11, 27)), (date(2026, 11, 17), date(2026, 11, 24))),
}

RRI = ("Reglamento de Régimen Interno de la Escuela de Ingeniería Informática (aprobado por el Consejo de Gobierno el "
       "5 de mayo de 2022), art. 58")
REVAL = "Reglamento de Evaluación de los Resultados de Aprendizaje y de las Competencias adquiridas por el Alumnado de la ULPGC, art. 24"
ACUERDO_2014 = ("Acuerdo de 15 de diciembre de 2014 del Director de la EII por el que se establece el plazo para presentar "
                "la solicitud de fecha alternativa de examen")
D_RRI, D_AC14, D_REV, D_INC = "Reglamento de Régimen Interno de la EII", "Acuerdo que define el plazo", "Reglamento de Evaluación de los Resultados", "Incidencias"
RECURSO = ("No es una resolución recurrible: la disconformidad se comunica al Director de la EII como incidencia "
           "académica, por la Sede Electrónica o el registro del Edificio (Acuerdo de 25 de octubre de 2013)")
FUND_ART58 = (
    "El artículo 58 del Reglamento de Régimen Interno de la Escuela de Ingeniería Informática reconoce al estudiante, "
    "cuando coinciden el día y la hora de pruebas finales de distintas asignaturas, con menos de cuatro horas entre la "
    "finalización de la primera y el comienzo de la siguiente, el derecho a que el profesorado de la asignatura del "
    "curso superior le facilite la realización de la prueba final de su asignatura en un día distinto con, al menos, 24 "
    "horas de diferencia. En el mismo sentido se pronuncia el artículo 24 del Reglamento de Evaluación de los "
    "Resultados de Aprendizaje y de las Competencias adquiridas por el Alumnado de la ULPGC."
)
FUND_NO_OFICIAL = (
    "El artículo 58 del Reglamento de Régimen Interno de la Escuela de Ingeniería Informática dispone que, si la "
    "coincidencia se produce entre una prueba que corresponda a una convocatoria oficial y una prueba de cualquier otro "
    "tipo, será el profesorado de esta última el que tendrá que facilitar una fecha alternativa en un día distinto con, "
    "al menos, 24 horas de diferencia."
)
FUND_ACTAS = ("Según el Acuerdo del Director de la Escuela de 15 de diciembre de 2014, la fecha alternativa debe estar "
              "comprendida dentro del periodo oficial de exámenes de la convocatoria correspondiente, sin afectar a los "
              "plazos de entrega y firma de actas.")
PIE = ("Si no está conforme con esta respuesta, podrá comunicarlo como incidencia académica al Director de la Escuela "
       "de Ingeniería Informática, mediante instancia presentada a través de la Sede Electrónica de la ULPGC o en el "
       "registro de la Administración del Edificio de Informática y Matemáticas, conforme al Acuerdo del Director de 25 "
       "de octubre de 2013.")
RAMAS = [("misma_hora", "estimar", 3), ("menos_4h", "estimar", 2), ("fuera_plazo", "inadmitir", 3),
         ("cuatro_horas_o_mas", "desestimar", 3), ("no_oficial", "estimar", 2)]


def hora(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def hora_texto(minutos: int) -> str:
    return f"{minutos // 60}:{minutos % 60:02d}"


def duracion(gap: int) -> str:
    h, m = divmod(gap, 60)
    texto = {1: "una hora", 2: "dos horas", 3: "tres horas", 4: "cuatro horas", 5: "cinco horas", 6: "seis horas"}.get(h, f"{h} horas")
    if h == 0:
        texto = "media hora" if m == 30 else f"{m} minutos"
    elif m == 30:
        texto += " y media"
    return texto


def generar(rng: random.Random, n: int, prefijo: str = "gen-fa") -> list[dict]:
    pesos = [r[2] for r in RAMAS]
    return [construir(rng, f"{prefijo}-{i:04d}", *rng.choices(RAMAS, pesos)[0][:2]) for i in range(1, n + 1)]


def construir(rng: random.Random, id_: str, rama: str, decision: str) -> dict:
    p = persona(rng)
    oficial_vs_continua = rama == "no_oficial"
    c_bajo, c_alto = sorted(rng.sample([1, 2, 3, 4], 2))
    a_bajo, a_alto = rng.choice(CURSOS[c_bajo]), rng.choice(CURSOS[c_alto])
    otra_curso = rng.choice([c_bajo, c_alto])
    otra = rng.choice([a for a in CURSOS[otra_curso] if a not in (a_bajo, a_alto)])

    nombre_conv = "especial" if oficial_vs_continua else rng.choice(["ordinaria", "ordinaria", "extraordinaria"])
    (inicio, fin), dias_examen = CONVOCATORIAS[nombre_conv]
    dia = habiles_entre(*dias_examen, rng)  # deja sitio para la fecha alternativa (+2 hábiles) en el periodo

    # Horarios (minutos desde las 0:00)
    misma = rama == "misma_hora" or (rama == "fuera_plazo" and rng.random() < 0.5)
    if misma or oficial_vs_continua:
        ini1 = rng.choice([9 * 60, 9 * 60, 10 * 60, 15 * 60 + 30, 16 * 60])
        fin1 = ini1 + rng.choice([120, 180])
        ini2, fin2 = (ini1, fin1) if misma else (ini1 + 30, ini1 + 150)
        gap = 0
    else:
        ini1 = rng.choice([8 * 60 + 30, 9 * 60])
        fin1 = ini1 + rng.choice([120, 150])
        gap = rng.choice([30, 60, 90, 120, 150, 180, 210]) if rama in ("menos_4h", "fuera_plazo") else rng.choice([240, 270, 300])
        ini2 = fin1 + gap
        fin2 = ini2 + rng.choice([120, 180])
    # El examen del curso bajo y el del alto, en un orden u otro
    primero_bajo = rng.random() < 0.5
    franja = {a_bajo: (ini1, fin1) if primero_bajo else (ini2, fin2), a_alto: (ini2, fin2) if primero_bajo else (ini1, fin1)}

    limite = sumar_habiles(dia, -5)
    if rama == "fuera_plazo":
        fecha = habiles_entre(sumar_habiles(limite, 1), sumar_habiles(dia, -1), rng)
        fecha_res = sumar_habiles(fecha, 1) if sumar_habiles(fecha, 1) < dia else fecha
    else:
        fecha = habiles_entre(sumar_habiles(limite, -6), limite, rng)
        fecha_res = sumar_habiles(limite, 1)
    alternativa = sumar_habiles(dia, 2)
    certificado = sumar_habiles(dia, 2)
    otra_dia = sumar_habiles(dia, rng.choice([-3, -2, 3, 4]))

    if oficial_vs_continua:
        # La oficial es la de la convocatoria especial; la continua, de otra asignatura (a menudo de un curso inferior)
        if rng.random() < 0.7:
            a_oficial, c_oficial, a_resp, c_resp = a_alto, c_alto, a_bajo, c_bajo
        else:
            a_oficial, c_oficial, a_resp, c_resp = a_bajo, c_bajo, a_alto, c_alto
        pruebas = [
            {"asignatura": a_oficial, "curso": c_oficial, "prueba": "Examen final, convocatoria especial", "oficial": True,
             "fecha": dia.isoformat(), "inicio": hora(ini1), "fin": hora(fin1)},
            {"asignatura": a_resp, "curso": c_resp, "prueba": "Prueba parcial de evaluación continua", "oficial": False,
             "fecha": dia.isoformat(), "inicio": hora(ini2), "fin": hora(fin2)},
        ]
        matricula = [{"asignatura": a_resp, "curso": c_resp},
                     {"asignatura": a_oficial, "curso": c_oficial, "convocatoria_especial": True},
                     {"asignatura": otra, "curso": otra_curso}]
    else:
        a_resp, c_resp = a_alto, c_alto
        pruebas = [{"asignatura": a, "curso": c, "prueba": f"Examen final, convocatoria {nombre_conv}", "oficial": True,
                    "fecha": dia.isoformat(), "inicio": hora(franja[a][0]), "fin": hora(franja[a][1])}
                   for a, c in ((a_bajo, c_bajo), (a_alto, c_alto))]
        pruebas.append({"asignatura": otra, "curso": otra_curso, "prueba": f"Examen final, convocatoria {nombre_conv}",
                        "oficial": True, "fecha": otra_dia.isoformat(), "inicio": "09:00", "fin": "12:00"})
        matricula = [{"asignatura": a_bajo, "curso": c_bajo}, {"asignatura": a_alto, "curso": c_alto},
                     {"asignatura": otra, "curso": otra_curso}]
    exp = {"titulacion": GII, "centro": "Escuela de Ingeniería Informática", "matricula_2026_2027": matricula,
           "calendario_pruebas": pruebas,
           "periodo_examenes": (f"Convocatoria {nombre_conv} 2026/2027: del {en_letra(inicio)} al {en_letra(fin)}")}

    # Instancia
    if oficial_vs_continua:
        expone = (f"Que me presento en la convocatoria especial a {a_oficial}, cuyo examen es el {en_letra(dia)} de "
                  f"{hora_texto(ini1)} a {hora_texto(fin1)}, y que a esa hora está fijada la prueba parcial de evaluación "
                  f"continua de {a_resp}, asignatura que también curso este año.")
        solicita = f"Que se me facilite otra fecha para la prueba parcial de {a_resp}."
        asunto = "Solicitud de fecha alternativa de prueba"
    else:
        expone = rng.choice([
            f"Que estoy {p.a('matriculado')} en {a_bajo} ({c_bajo}.º curso) y en {a_alto} ({c_alto}.º curso) del Grado en "
            f"Ingeniería Informática, y que los exámenes finales de la convocatoria {nombre_conv} de las dos asignaturas "
            f"están fijados el mismo día, el {en_letra(dia)}.",
            f"Que el {en_letra(dia)} tengo el examen de {a_bajo} y el de {a_alto}, y que me coinciden los dos exámenes.",
        ])
        solicita = f"Que se me facilite una fecha alternativa para el examen final de {a_resp}."
        asunto = "Solicitud de fecha alternativa de examen"
    ins = instancia("Solicitud de fecha alternativa de examen por coincidencia de pruebas (art. 58 del Reglamento de "
                    "Régimen Interno de la EII)", "Correo electrónico institucional al profesorado de la asignatura",
                    fecha, p, f"Profesorado de la asignatura {a_resp}", asunto, expone, solicita, [])

    gold = gold_caso(p, rama, decision, fecha, fecha_res, dia, limite, alternativa, certificado, a_bajo, c_bajo,
                     a_alto, c_alto, franja, gap, a_resp, c_resp, pruebas, nombre_conv)
    notas = f"Generado. Rama {rama}: {decision}. Calendario ficticio."
    return caso(id_, TRAMITE, None, notas, ins, exp, [], gold, rama)


def gold_caso(p: Persona, rama, decision, fecha, fecha_res, dia, limite, alternativa, certificado, a_bajo, c_bajo,
              a_alto, c_alto, franja, gap, a_resp, c_resp, pruebas, nombre_conv) -> dict:
    inter, la = p.a("interesado"), p.la
    titulo = (f"RESPUESTA DE {en_letra_mayus(fecha_res)} DEL PROFESORADO DE LA ASIGNATURA {a_resp.upper()} A LA SOLICITUD "
              f"DE FECHA ALTERNATIVA DE {'EXAMEN DE ' if rama != 'no_oficial' else ''}{p.don.upper()} {p.nombre.upper()}")
    objeto_prueba = ("la prueba parcial de evaluación continua de la asignatura " if rama == "no_oficial"
                     else "el examen final de la asignatura ") + a_resp
    vista_ = (f"Vista la solicitud presentada por correo electrónico institucional el {en_letra(fecha)} por {p.don} "
              f"{p.nombre}, con DNI {p.dni}, estudiante del Grado en Ingeniería Informática, mediante la que solicita una "
              f"fecha alternativa para {objeto_prueba}"
              + ("" if rama == "no_oficial" else f" de la convocatoria {nombre_conv}") + ", resultan los siguientes")
    competencia = (f"En virtud de lo expuesto, el profesorado de la asignatura {a_resp}, en aplicación del artículo 58 "
                   "del Reglamento de Régimen Interno de la Escuela de Ingeniería Informática,")
    norma = {"normas": [RRI, ACUERDO_2014] if rama == "no_oficial" else [RRI, REVAL, ACUERDO_2014],
             "motivo": "Normas vigentes sin cambios en el curso 2026/2027."}
    organo = (f"Profesorado de la asignatura {a_resp} (prueba no oficial)" if rama == "no_oficial"
              else f"Profesorado de la asignatura {a_resp} (asignatura del curso superior)")
    f_plazo = [(D_RRI, "58"), (D_AC14, "")]
    plazo_ok = rama != "fuera_plazo"
    r_plazo = req("Solicitud al menos cinco días hábiles antes", f"{RRI}; {ACUERDO_2014}", plazo_ok,
                  f"Presentada el {en_letra(fecha)}; el plazo terminaba el {en_letra(limite)}.", f_plazo)

    if rama == "no_oficial":
        (p1, p2) = pruebas
        hechos = [f"El {en_letra(dia)} se celebran el examen de la convocatoria especial de {p1['asignatura']}, de "
                  f"{ORDINALES_CURSO[p1['curso']]} curso, de {p1['inicio'].lstrip('0')} a {p1['fin'].lstrip('0')} horas, y la "
                  f"prueba parcial de evaluación continua de {a_resp}, de {ORDINALES_CURSO[c_resp]} curso, de "
                  f"{p2['inicio'].lstrip('0')} a {p2['fin'].lstrip('0')} horas.",
                  f"{la.capitalize()} {inter} está {p.a('matriculado')} en las dos asignaturas en el curso 2026/2027 y se "
                  f"presenta a {p1['asignatura']} en la convocatoria especial.",
                  f"La solicitud se presentó el {en_letra(fecha)}."]
        fundamentos = [FUND_NO_OFICIAL,
                       f"El examen de {p1['asignatura']} corresponde a la convocatoria especial, que es convocatoria "
                       f"oficial, y la prueba parcial de {a_resp} no lo es. Por tanto, corresponde a este profesorado "
                       "facilitar la fecha alternativa, con independencia del curso de cada asignatura.",
                       f"La solicitud debe presentarse al menos cinco días hábiles antes de la prueba (artículo 58), plazo "
                       f"que terminaba el {en_letra(limite)}. La solicitud se presentó dentro de plazo."]
        acuerda = (f"Fijar como fecha alternativa para la prueba parcial de evaluación continua de {a_resp} de {p.don} "
                   f"{p.nombre} el {en_letra(alternativa)}, a las {p2['inicio'].lstrip('0')} horas. {la.capitalize()} "
                   f"{inter} deberá aportar a este profesorado, en un plazo no superior a dos días hábiles desde su "
                   f"celebración, es decir, hasta el {en_letra(certificado)}, un certificado que acredite su comparecencia "
                   f"al examen de {p1['asignatura']} del {en_letra(dia)} (artículo 58 del Reglamento de Régimen Interno).")
        reqs = [req("Coincidencia de pruebas", RRI, True,
                    f"El {en_letra(dia)} el examen de la convocatoria especial ({p1['inicio']}-{p1['fin']}) se solapa con "
                    f"la prueba parcial ({p2['inicio']}-{p2['fin']}).", [(D_RRI, "58")]),
                req("Profesorado al que corresponde facilitar la fecha", RRI, True,
                    "Una de las pruebas es de convocatoria oficial y la otra no: corresponde al profesorado de la prueba de "
                    f"evaluación continua, {a_resp}" + (", aunque sea del curso inferior." if c_resp < p1["curso"] else "."),
                    [(D_RRI, "58")]),
                r_plazo]
    else:
        f_b, f_a = franja[a_bajo], franja[a_alto]
        txt = (f"los exámenes finales de {a_bajo}, de {ORDINALES_CURSO[c_bajo]} curso, y de {a_alto}, de "
               f"{ORDINALES_CURSO[c_alto]} curso, se celebran el {en_letra(dia)}, ")
        if gap == 0:
            txt += f"ambos de {hora_texto(f_a[0])} a {hora_texto(f_a[1])} horas."
        else:
            txt += (f"el de {a_bajo} de {hora_texto(f_b[0])} a {hora_texto(f_b[1])} horas y el de {a_alto} de "
                    f"{hora_texto(f_a[0])} a {hora_texto(f_a[1])} horas.")
        hechos = [f"Según el calendario oficial de exámenes de la convocatoria {nombre_conv} del curso 2026/2027, " + txt,
                  f"{la.capitalize()} {inter} está {p.a('matriculado')} en las dos asignaturas en el curso 2026/2027.",
                  f"La solicitud se presentó el {en_letra(fecha)}."]
        (primero, fin_primero), (segundo, ini_segundo) = (
            ((a_bajo, f_b[1]), (a_alto, f_a[0])) if f_b[0] <= f_a[0] else ((a_alto, f_a[1]), (a_bajo, f_b[0])))
        coincide = gap < 240
        desc_coinc = ("Los dos exámenes coinciden en día y hora" if gap == 0 else
                      f"Entre la finalización del examen de {primero} y el comienzo del de {segundo} median "
                      f"{duracion(gap)}, menos de cuatro horas")
        reqs = [req("Coincidencia de pruebas finales", RRI, coincide,
                    (f"Los dos exámenes son el {en_letra(dia)} de {hora_texto(f_a[0])} a {hora_texto(f_a[1])}: coinciden en día y hora."
                     if gap == 0 else
                     f"{primero} termina a las {hora_texto(fin_primero)} y {segundo} empieza a las {hora_texto(ini_segundo)}: "
                     f"median {duracion(gap)}" + (", menos de cuatro." if coincide else
                                                  " (se exigen menos de cuatro), y no tiene más de dos pruebas finales ese día.")),
                    [(D_RRI, "58"), (D_REV, "24")])]
        if coincide:
            reqs.append(req("Profesorado al que corresponde facilitar la fecha", RRI, True,
                            f"Las dos son pruebas finales oficiales; {a_alto} es la del curso superior ({c_alto}.º).",
                            [(D_RRI, "58")]))
        if rama != "fuera_plazo" or coincide:
            reqs.append(r_plazo)
        if rama == "fuera_plazo":
            fundamentos = [FUND_ART58,
                           "El mismo artículo exige, para poder ejercer este derecho, solicitar la fecha alternativa al "
                           "profesorado al menos cinco días hábiles antes de la celebración de la prueba final, y el "
                           "Acuerdo del Director de la Escuela de 15 de diciembre de 2014 fija ese mismo plazo límite. Para "
                           f"el examen del {en_letra(dia)} el plazo terminaba el {en_letra(limite)}.",
                           f"La solicitud se presentó el {en_letra(fecha)}, fuera de plazo, por lo que no procede estudiar "
                           "la coincidencia."]
            acuerda = (f"No admitir, por haberse presentado fuera de plazo, la solicitud de fecha alternativa para el examen "
                       f"final de {a_alto} de {p.don} {p.nombre}, que se mantiene para {la} {inter} el {en_letra(dia)} a "
                       f"las {hora_texto(f_a[0])} horas.")
        elif coincide:
            fundamentos = [FUND_ART58,
                           f"{desc_coinc}, y {a_alto} es la asignatura del curso superior, por lo que corresponde a su "
                           "profesorado facilitar la fecha alternativa.",
                           "La solicitud debe presentarse al menos cinco días hábiles antes de la prueba final (artículo 58 "
                           "del Reglamento de Régimen Interno y Acuerdo del Director de la Escuela de 15 de diciembre de "
                           f"2014), plazo que para el examen del {en_letra(dia)} terminaba el {en_letra(limite)}. La "
                           "solicitud se presentó dentro de plazo.",
                           FUND_ACTAS]
            acuerda = (f"Fijar como fecha alternativa para el examen final de {a_alto} de {p.don} {p.nombre} el "
                       f"{en_letra(alternativa)}, a las {hora_texto(f_a[0])} horas, dentro del periodo oficial de exámenes. "
                       f"{la.capitalize()} {inter} deberá aportar a este profesorado, en un plazo no superior a dos días "
                       f"hábiles desde su celebración, es decir, hasta el {en_letra(certificado)}, un certificado que "
                       f"acredite su comparecencia al examen de {a_bajo} del {en_letra(dia)} (artículo 58 del Reglamento de "
                       "Régimen Interno).")
        else:
            hechos[0] += f" {la.capitalize()} {inter} no tiene ninguna otra prueba final ese día."
            fundamentos = [FUND_ART58,
                           f"Entre la finalización del examen de {primero} y el comienzo del de {segundo} median "
                           f"{duracion(gap)}, por lo que no se da la coincidencia que exige el artículo 58.",
                           "El mismo artículo dispone que un estudiante no podrá verse obligado a realizar en un mismo día "
                           f"más de dos pruebas finales de distintas asignaturas. {la.capitalize()} {inter} solo tiene dos ese día."]
            acuerda = (f"Denegar la fecha alternativa solicitada por {p.don} {p.nombre} para el examen final de {a_alto}, "
                       f"por no coincidir con el de {a_bajo} en los términos del artículo 58 del Reglamento de Régimen "
                       f"Interno de la Escuela de Ingeniería Informática. El examen se mantiene el {en_letra(dia)} a las "
                       f"{hora_texto(f_a[0])} horas.")
    cierre = firma(fecha_res, f"EL/LA PROFESOR/A COORDINADOR/A DE LA ASIGNATURA {a_resp.upper()}")
    from generador.comun import documento_resolucion
    texto = documento_resolucion(titulo, vista_, hechos, fundamentos, competencia, acuerda, PIE, cierre, verbo="ACUERDA:")
    return {"decision": decision, "norma_aplicable": norma, "organo": organo, "recurso": RECURSO,
            "requisitos": reqs, "resolucion": texto}
