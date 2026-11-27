"""Descarga los formularios públicos de la EII/ULPGC y el Manual de normalización.

Sirven de modelo para las instancias (EXPONE/SOLICITA) y las resoluciones:
  data/plantillas/manual/               Manual de normalización de documentos de la ULPGC (2000)
  data/plantillas/eii/                  formularios de la web de la EII
  data/plantillas/ulpgc_normalizados/   impresos normalizados de la ULPGC (Teleformación, 2022)
  data/plantillas/aeim_2017/            impresos de la Administración del Edificio de Inf. y Mat.
  data/plantillas/manifiesto.jsonl      origen, página y huella de cada fichero

Respeta robots.txt y Crawl-delay por servidor, como scripts/descargar_normativa.py.
La sede electrónica (administracion.ulpgc.es) no se descarga: su robots.txt solo
permite la portada.

Uso: python scripts/descargar_plantillas.py
"""
import hashlib, json, sys, time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.robotparser import RobotFileParser

import requests

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "plantillas"

UA = "Mozilla/5.0 (compatible; normativa-ulpgc-rag/1.0; proyecto academico)"
DEFAULT_DELAY = 2.0

EII = "https://www.eii.ulpgc.es/sites/default/files"
TEL = "https://tel.ulpgc.es/sites/default/files/documentos/impresos"
AEIM = "https://www.ulpgc.es/sites/default/files/ArchivosULPGC/adm_eim/Impresos gestion academica"

# (carpeta, nombre, url, página donde aparece, nota)
FICHEROS = [
    ("manual", "manual_normalizacion_documentos_ulpgc_2000.pdf",
     "https://sudocument.ulpgc.es/access/files/original/c8d28ab40decf6d1d91fa40553292ab557f1291d.pdf",
     "https://sudocument.ulpgc.es", "Modelos oficiales: requerimiento de subsanación (p. 111), resolución (p. 114), solicitud normalizada (p. 118) y genérica (p. 123)"),
    ("eii", "solicitud_evaluacion_compensatoria_eii_2022.pdf",
     f"{EII}/2022-06/Solicitud%20Evaluaci%C3%B3n%20Compensatoria_0.pdf",
     "https://eii.ulpgc.es/es/escuela/formularios", "Formulario vigente en la web de la EII (2022: anterior al Reglamento 1/2026)"),
    ("eii", "solicitud_cambio_grupo_2024_2025_v06.pdf",
     f"{EII}/2025-02/Formulario%20de%20solicitud%20de%20cambio%20de%20grupo%202024-2025%20v06.pdf",
     "https://eii.ulpgc.es/es/escuela/formularios", "Cambio de grupo, curso 2024-2025"),
    ("eii", "justificante_asistencia_actividad_academica_eii_2024.pdf",
     f"{EII}/2024-06/NUEVO%20JUSTIFICANTE%20ASISTENCIA%20A%20ACTIVIDAD%20ACAD%C3%89MICA%20EII.pdf",
     "https://eii.ulpgc.es/es/escuela/formularios", "Documento acreditativo típico (p. ej. fecha alternativa por coincidencia de exámenes)"),
    ("eii", "solicitud_simultaneidad_menciones_gii.pdf",
     f"{EII}/2021-05/SOLICITUD%20DE%20SIMULTANEIDAD%20ENTRE%20MENCIONES%20DEL%20GII.pdf",
     "https://eii.ulpgc.es/es/escuela/formularios", "Simultaneidad entre menciones del GII"),
    ("ulpgc_normalizados", "solicitud_generica_22.pdf", f"{TEL}/solicitud_generica_22.pdf",
     "https://tel.ulpgc.es/organizacion/administracion/impresos-gestion-academica", "Instancia genérica según el Manual de normalización (versión 2022)"),
    ("ulpgc_normalizados", "solicitud_compensatoria_22.pdf", f"{TEL}/solicitud_compensatoria_22.pdf",
     "https://tel.ulpgc.es/organizacion/administracion/impresos-gestion-academica", "Evaluación compensatoria, modelo normalizado 2022"),
    ("ulpgc_normalizados", "solicitud_reconocimiento_creditos_22.pdf", f"{TEL}/solcitud_de_reconocimiento_22.pdf",
     "https://tel.ulpgc.es/organizacion/administracion/impresos-gestion-academica", "Reconocimiento de créditos (convalidaciones)"),
    ("ulpgc_normalizados", "recurso_de_reposicion_22.pdf", f"{TEL}/recurso_de_reposicion_22.pdf",
     "https://tel.ulpgc.es/organizacion/administracion/impresos-gestion-academica", "Recurso contra una resolución"),
    ("ulpgc_normalizados", "recurso_de_alzada_22.pdf", f"{TEL}/recurso_de_alzada_22.pdf",
     "https://tel.ulpgc.es/organizacion/administracion/impresos-gestion-academica", "Recurso contra una resolución"),
    ("aeim_2017", "solicitud_evaluacion_compensatoria_eii_aeim.pdf",
     f"{AEIM}/solicitud_evaluacion_compensatoria_eii.pdf",
     "https://www.ulpgc.es/adm_eim/impresos_g_academica", "Administración del Edificio de Informática y Matemáticas (página de 2017)"),
    ("aeim_2017", "solicitud_reconocimiento_creditos_en_el_gii.pdf",
     f"{AEIM}/solicitud_reconocimiento_creditos_en_el_gii.pdf",
     "https://www.ulpgc.es/adm_eim/impresos_g_academica", "Administración del Edificio de Informática y Matemáticas (página de 2017)"),
]


def main(destino: Path = DESTINO) -> None:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    robots: dict[str, RobotFileParser] = {}
    ultimo: dict[str, float] = {}
    manifiesto = []
    for carpeta, nombre, url, pagina, nota in FICHEROS:
        host = urlparse(url).netloc
        if host not in robots:
            rp = RobotFileParser()
            try:
                r = s.get(f"https://{host}/robots.txt", timeout=30)
                rp.parse(r.text.splitlines() if r.ok else [])
            except requests.RequestException:
                rp.parse([])
            robots[host] = rp
        rp = robots[host]
        if not rp.can_fetch(UA, url):
            print(f"ROBOTS NO  {url}")
            continue
        espera = float(rp.crawl_delay(UA) or DEFAULT_DELAY)
        falta = ultimo.get(host, 0) + espera - time.time()
        if falta > 0:
            time.sleep(falta)
        r = s.get(url, timeout=60)
        ultimo[host] = time.time()
        tipo = r.headers.get("content-type", "")
        if not r.ok or "html" in tipo:
            print(f"FALLO {r.status_code} {tipo}  {url}")
            continue
        f = destino / carpeta / nombre
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(r.content)
        manifiesto.append({"fichero": str(f.relative_to(destino)), "url": url, "pagina": pagina,
                           "nota": nota, "sha256": hashlib.sha256(r.content).hexdigest()[:16],
                           "bytes": len(r.content), "descargado": date.today().isoformat()})
        print(f"OK {len(r.content):>8}  {f.relative_to(destino)}")
    (destino / "manifiesto.jsonl").write_text(
        "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in manifiesto), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO)
