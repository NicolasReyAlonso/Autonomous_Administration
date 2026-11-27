# Instancias con resolución de referencia

Cada fichero `<trámite>/<id>.json` es un expediente completo: lo que entra en la
Administración (la instancia), lo que la Administración ya sabe del solicitante y la
resolución que debería dictarse. Con ellos se evalúa el sistema y se generan los datos
de entrenamiento. **Todos los datos personales son ficticios** (el DNI 12345678Z es el
de ejemplo habitual).

## Campos

| Campo | Qué es |
|---|---|
| `id`, `tramite`, `ficha_sia` | Identificador, trámite y código SIA de su ficha en `data/plantillas/tramites.jsonl` |
| `notas_caso` | Qué pone a prueba el caso (no se le pasa al modelo) |
| `instancia` | Lo que presenta el interesado. Copia los campos de la Instancia General de la sede y del formulario en papel (`data/plantillas/aportados/instancia_general_ulpgc_2009.pdf`): solicitante, medio de notificación, procedimiento, órgano al que se dirige, asunto, fecha de presentación, `expone`, `solicita`, documentación aportada y si está firmada |
| `expediente` | Datos que ya tiene la ULPGC y que el interesado no tiene que aportar (art. 28.2 de la Ley 39/2015): titulación, créditos, asignaturas pendientes con sus convocatorias, matrícula, nota media, compensaciones previas |
| `informes` | Actos de instrucción, por ejemplo el informe del coordinador de la asignatura (art. 7 del Reglamento de compensación de la EII) |
| `gold.decision` | `estimar`, `desestimar`, `requerir_subsanacion` o `inadmitir` |
| `gold.norma_aplicable` | Normas que rigen el caso y **por qué esas** (la fecha de presentación decide) |
| `gold.organo`, `gold.recurso` | Quién resuelve y qué recurso cabe |
| `gold.requisitos` | Cada requisito comprobado: norma, si se cumple y por qué. Permite puntuar el razonamiento, no solo el fallo |
| `gold.resolucion` | Texto completo de la resolución, un párrafo por elemento |

## Estructura de la resolución

Sigue el *Manual de normalización de documentos administrativos* de la ULPGC (2000,
págs. 114-117), con las referencias legales de la Ley 30/1992 cambiadas a la Ley 39/2015:

1. **Título**: `RESOLUCIÓN DE <fecha> DE <órgano> POR LA QUE SE <objeto>`.
2. **Antecedentes**: «Vista la instancia presentada por … con fecha … mediante la que solicita …».
3. **Hechos**, numerados (Primero.-, Segundo.-…).
4. **Fundamentos de derecho**: primero la norma aplicable y después un fundamento por requisito, con el artículo.
5. **Competencia**: «esta Comisión/Dirección, en uso de las competencias atribuidas por …».
6. **RESUELVE:** y la decisión con sus efectos.
7. **Pie de recursos**: recurso, órgano, plazo (arts. 112, 121 y 122 de la Ley 39/2015).
8. Lugar y fecha, antefirma, firma y nombre.

Según la decisión:
- **Requerir subsanación** (art. 68.1): falta algo del art. 66 (identificación, petición
  concreta, firma…) o un documento preceptivo. Plazo de diez días hábiles, «con indicación
  de que, si así no lo hiciera, se le tendrá por desistido de su petición, previa resolución».
- **Inadmitir**: solicitud fuera de plazo, trámite que no corresponde (por ejemplo, una
  compensatoria de máster, art. 1) o petición manifiestamente carente de fundamento (art. 88.5).
- **Desestimar**: se estudia el fondo y falla algún requisito; se dice cuál y por qué.
- **Estimar**: se cumplen todos; se dicen los efectos (en la compensatoria, «5 Apto por Compensación»).

## Norma aplicable por fecha: evaluación compensatoria en la EII

El Reglamento 1/2026 entra en vigor «en la convocatoria ordinaria del curso académico
siguiente a su aprobación» (disposición final). La EII lo concreta en sus plazos del curso
2026/2027:

| Presentación | Norma | Requisitos clave | Resuelve | Recurso |
|---|---|---|---|---|
| 2-16 dic 2026 (convocatoria especial) | Reglamento ULPGC 2018 + Reglamento EII Rev. 06 | 85 % de los créditos compensables; al menos 2 convocatorias con nota de 2 o más (o media de 6,5 o más); 1.º y 2.º superados salvo una; máx. 6 % de la titulación | Comisión de Compensación de la EII | Alzada ante el Vicerrector de estudiantes (Comisión Central), 1 mes |
| Desde el 8 ene 2027 | Reglamento 1/2026 + Tabla resumen EII | 75 %; 3 convocatorias, un 3,00 en alguna, media de 6,00 o más; máx. 15 ECTS en grados de 240 | Director/a de la EII (1 mes) | Alzada ante el Rector, 1 mes |

Fuera de esas ventanas la solicitud se inadmite por extemporánea. Un mismo expediente
puede así resolverse distinto según la fecha: se generan pares de casos para probarlo.
Al resolver, la búsqueda se hace con la fecha de presentación
(`buscar(..., fecha=instancia["fecha_presentacion"])`), que deja fuera la norma que todavía
no se aplica o que ya no se aplica (fechas en `data/overrides.json`).

## Fecha alternativa de examen

No es un trámite de la sede. Se modela como petición del estudiante al profesorado,
según el art. 58 del Reglamento de Régimen Interno de la EII:
- hay derecho si dos pruebas finales coinciden en día y hora, con menos de cuatro horas
  entre el final de una y el comienzo de la otra, o si serían más de dos finales el mismo día;
- facilita la nueva fecha (al menos 24 h de diferencia) el profesorado de la asignatura del
  **curso superior**; si una es de convocatoria oficial y la otra no, el de esta última;
- se pide al menos cinco días hábiles antes de la prueba, y el estudiante aporta el
  certificado de asistencia a la otra prueba en dos días hábiles como máximo.

La «resolución» es la respuesta del profesor, con la misma estructura reducida: hechos,
norma, decisión y a quién reclamar. El aplazamiento por enfermedad u otra causa justificada
(art. 59) sí va ante el Director, en cinco días hábiles: es un caso cercano para más adelante.
