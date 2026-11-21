"""Búsqueda sobre los fragmentos de normativa: BM25, embeddings y combinación híbrida.

Índices (los genera scripts/indexar_normativa.py):
  data/index/bm25/                      BM25 con raíces en español
  data/index/denso/<modelo>/            embeddings normalizados (float16) + metadatos

Uso:
    from rag.busqueda import Buscador
    b = Buscador.cargar()  # modelo por defecto: MODELO_POR_DEFECTO
    for r in b.buscar("¿cuántas convocatorias tengo?", k=5):
        print(r.puntuacion, r.fragmento["titulo_doc"], r.fragmento["encabezado"])
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
CHUNKS = RAIZ / "data" / "processed" / "chunks.jsonl"
INDICE = RAIZ / "data" / "index"

# Cómo pide cada modelo que se formateen consultas y documentos. Los modelos sin
# entrada usan los prompts "query"/"document" de su propia configuración (si los tienen).
PREFIJOS = {
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}
LONGITUD_MAXIMA = 512  # tokens; los fragmentos se cortaron a ~450
RRF_K = 60             # constante de Reciprocal Rank Fusion

# Configuración elegida con scripts/evaluar_busqueda.py (30 preguntas, nov. 2026):
# Qwen3 + BM25 con peso 0,3 + citas -> Acierto@5 90 %, MRR@10 0,738
# (bge-m3 en la misma configuración: Acierto@5 87 %, MRR 0,675).
MODELO_POR_DEFECTO = "Qwen/Qwen3-Embedding-0.6B"
PESO_BM25 = 0.3        # BM25 es bastante peor que los embeddings: pesa menos en la fusión
# "artículo 58", "art. 12": se añade un ranking con solo los fragmentos de ese artículo
RE_CITA_ARTICULO = re.compile(r"\bart(?:[íi]culo|\.)?\s*(\d+)", re.I)

# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
STOPWORDS_ES = set("""
a al algo algun alguna algunas alguno algunos ante antes aquel aquella aquellas aquellos aqui asi aun
cada como con contra cual cuales cualquier cuando de del desde donde dos e el ella ellas ello ellos en
entre era eran es esa esas ese eso esos esta estas este esto estos fue fueron ha han hasta hay la las le
les lo los mas me mi mis mucho muy ni no nos o otra otras otro otros para pero poco por porque que quien
quienes se sea sean segun ser si sin sobre son su sus tal tambien tan tanto te tiene tienen todo todos
tras tu tus u un una unas uno unos y ya yo puedo puede pueden tengo tienes hacer hago debo
""".split())

_stemmer = None


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def tokenizar(texto: str) -> list[str]:
    """Minúsculas, sin tildes, sin palabras vacías y reducido a raíces (Snowball)."""
    global _stemmer
    if _stemmer is None:
        import Stemmer
        _stemmer = Stemmer.Stemmer("spanish")
    palabras = re.findall(r"[a-zñ0-9]+", sin_tildes(texto.lower()))
    return _stemmer.stemWords([p for p in palabras if p not in STOPWORDS_ES])


def texto_para_indexar(c: dict) -> str:
    """Fragmento con su contexto: documento, ruta y encabezado (si es una parte > 1)."""
    partes = [c["titulo_doc"]]
    if c["ruta"]:
        partes.append(" > ".join(c["ruta"]))
    if c["parte"] > 1:
        partes.append(c["encabezado"])
    partes.append(c["texto"])
    return "\n".join(partes)


def cargar_fragmentos(ruta: Path = CHUNKS) -> list[dict]:
    with ruta.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def huella(fragmentos: list[dict]) -> str:
    """Identifica el conjunto de fragmentos, para detectar índices desactualizados."""
    h = hashlib.sha256()
    for c in fragmentos:
        h.update(c["id"].encode())
        h.update(hashlib.sha256(c["texto"].encode()).digest())
    return h.hexdigest()[:16]


def carpeta_modelo(modelo: str) -> Path:
    return INDICE / "denso" / modelo.replace("/", "__")


def dispositivo() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def usar_fp16(dev: str) -> bool:
    """fp16 solo donde es rápido: Apple (MPS) y NVIDIA con tensor cores (Volta, 7.0+).
    En Pascal (GTX 10xx) el fp16 calcula a 1/64 de la velocidad de fp32."""
    import torch
    if dev == "mps":
        return True
    return dev == "cuda" and torch.cuda.get_device_capability()[0] >= 7


def cargar_modelo(modelo: str):
    import torch
    from sentence_transformers import SentenceTransformer
    dev = dispositivo()
    kwargs = {"model_kwargs": {"dtype": torch.float16}} if usar_fp16(dev) else {}
    m = SentenceTransformer(modelo, device=dev, **kwargs)
    m.max_seq_length = min(m.max_seq_length or LONGITUD_MAXIMA, LONGITUD_MAXIMA)
    return m


def codificar(m, modelo: str, textos: list[str], es_consulta: bool, **kw) -> np.ndarray:
    kw = {"normalize_embeddings": True, "convert_to_numpy": True, **kw}
    if modelo in PREFIJOS:
        prefijo = PREFIJOS[modelo][0 if es_consulta else 1]
        return m.encode([prefijo + t for t in textos], **kw)
    if es_consulta:
        return m.encode_query(textos, **kw)
    return m.encode_document(textos, **kw)


# --------------------------------------------------------------------------- #
# Construcción de índices
# --------------------------------------------------------------------------- #
def construir_bm25(fragmentos: list[dict]) -> Path:
    import bm25s
    carpeta = INDICE / "bm25"
    carpeta.mkdir(parents=True, exist_ok=True)
    bm25 = bm25s.BM25()
    bm25.index([tokenizar(texto_para_indexar(c)) for c in fragmentos], show_progress=False)
    bm25.save(str(carpeta))
    (carpeta / "meta.json").write_text(json.dumps({"huella": huella(fragmentos),
                                                   "n": len(fragmentos)}), encoding="utf-8")
    return carpeta


def construir_denso(fragmentos: list[dict], modelo: str, lote: int = 16) -> Path:
    m = cargar_modelo(modelo)
    emb = codificar(m, modelo, [texto_para_indexar(c) for c in fragmentos], es_consulta=False,
                    batch_size=lote, show_progress_bar=True)
    if not np.isfinite(emb).all():
        raise ValueError(f"{modelo}: embeddings con NaN/inf (prueba en float32)")
    carpeta = carpeta_modelo(modelo)
    carpeta.mkdir(parents=True, exist_ok=True)
    np.save(carpeta / "embeddings.npy", emb.astype(np.float16))
    (carpeta / "meta.json").write_text(json.dumps({
        "modelo": modelo, "dim": int(emb.shape[1]), "n": len(fragmentos),
        "huella": huella(fragmentos), "dispositivo": dispositivo()}), encoding="utf-8")
    return carpeta


# --------------------------------------------------------------------------- #
# Búsqueda
# --------------------------------------------------------------------------- #
@dataclass
class Resultado:
    fragmento: dict
    puntuacion: float
    posicion_bm25: int | None = None
    posicion_densa: int | None = None


class Buscador:
    def __init__(self, fragmentos: list[dict], bm25=None, embeddings=None, modelo: str | None = None):
        self.fragmentos = fragmentos
        self.bm25 = bm25
        self.embeddings = embeddings
        self.modelo_nombre = modelo
        self._modelo = None
        self.vigentes = np.array([c["vigente"] for c in fragmentos])
        self.numeros = np.array([c["numero"] for c in fragmentos])

    @classmethod
    def cargar(cls, modelo: str | None = MODELO_POR_DEFECTO) -> "Buscador":
        """modelo=None carga solo BM25 (sin embeddings)."""
        import bm25s
        fragmentos = cargar_fragmentos()
        h = huella(fragmentos)
        carpeta = INDICE / "bm25"
        if json.loads((carpeta / "meta.json").read_text())["huella"] != h:
            raise RuntimeError("El índice BM25 no corresponde a chunks.jsonl: ejecuta scripts/indexar_normativa.py")
        bm25 = bm25s.BM25.load(str(carpeta))
        emb = None
        if modelo:
            cm = carpeta_modelo(modelo)
            if json.loads((cm / "meta.json").read_text())["huella"] != h:
                raise RuntimeError(f"El índice de {modelo} está desactualizado: vuelve a indexar")
            emb = np.load(cm / "embeddings.npy").astype(np.float32)
        return cls(fragmentos, bm25, emb, modelo)

    def _mascara(self, solo_vigentes: bool) -> np.ndarray:
        return self.vigentes if solo_vigentes else np.ones(len(self.fragmentos), bool)

    def puntuar_bm25(self, consulta: str) -> np.ndarray:
        tokens = tokenizar(consulta)
        if not tokens:
            return np.zeros(len(self.fragmentos))
        return np.asarray(self.bm25.get_scores(tokens), dtype=np.float32)

    def puntuar_denso(self, consulta: str) -> np.ndarray:
        if self._modelo is None:
            self._modelo = cargar_modelo(self.modelo_nombre)
        q = codificar(self._modelo, self.modelo_nombre, [consulta], es_consulta=True)[0]
        return self.embeddings @ q.astype(np.float32)

    @staticmethod
    def _ranking(puntuaciones: np.ndarray, mascara: np.ndarray, k: int) -> list[int]:
        p = np.where(mascara, puntuaciones, -np.inf)
        orden = np.argsort(-p)[:k]
        return [int(i) for i in orden if np.isfinite(p[i])]

    def buscar(self, consulta: str, k: int = 10, modo: str = "hibrido",
               solo_vigentes: bool = True, profundidad: int = 100,
               peso_bm25: float = PESO_BM25) -> list[Resultado]:
        """modo: 'bm25', 'denso' o 'hibrido'.

        El modo híbrido combina con Reciprocal Rank Fusion ponderada:
          puntuación = peso_bm25/(K + pos_bm25) + 1/(K + pos_densa) [+ 1/(K + pos_cita)]
        donde pos_cita es la posición (por BM25) entre los fragmentos del artículo
        citado en la consulta, si cita uno ("artículo 58 del reglamento...").
        """
        mascara = self._mascara(solo_vigentes)
        if modo == "bm25":
            p = self.puntuar_bm25(consulta)
            return [Resultado(self.fragmentos[i], float(p[i]), posicion_bm25=n)
                    for n, i in enumerate(self._ranking(p, mascara, k), 1)]
        if modo == "denso":
            p = self.puntuar_denso(consulta)
            return [Resultado(self.fragmentos[i], float(p[i]), posicion_densa=n)
                    for n, i in enumerate(self._ranking(p, mascara, k), 1)]
        if modo != "hibrido":
            raise ValueError(modo)
        p_bm25 = self.puntuar_bm25(consulta)
        rb = self._ranking(p_bm25, mascara, profundidad)
        rd = self._ranking(self.puntuar_denso(consulta), mascara, profundidad)
        listas = [(rb, peso_bm25), (rd, 1.0)]
        cita = RE_CITA_ARTICULO.search(consulta)
        if cita:
            listas.append((self._ranking(p_bm25, mascara & (self.numeros == cita.group(1)), 20), 1.0))
        rrf: dict[int, float] = {}
        for lista, peso in listas:
            for n, i in enumerate(lista, 1):
                rrf[i] = rrf.get(i, 0.0) + peso / (RRF_K + n)
        pos_b = {i: n for n, i in enumerate(rb, 1)}
        pos_d = {i: n for n, i in enumerate(rd, 1)}
        mejores = sorted(rrf, key=rrf.get, reverse=True)[:k]
        return [Resultado(self.fragmentos[i], rrf[i], pos_b.get(i), pos_d.get(i)) for i in mejores]
