# Diseño de una sistema de administración publica basada en Gemma 4 y aprendizaje

## Puesta en marcha en una máquina nueva

Requisitos: Python 3.12 y git. En el PC, una GPU NVIDIA con su driver instalado
(`nvidia-smi` debe funcionar). El proyecto se usa en un Mac con Apple Silicon y en
un PC Linux con GTX 10xx; ver las notas de `requirements.txt` para otras gráficas.

```bash
# 1. Código
git clone https://github.com/NicolasReyAlonso/Autonomous_Administration.git
cd Autonomous_Administration

# 2. Entorno (en Ubuntu, si falla: sudo apt install python3.12-venv)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Comprobar la GPU
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))"
```

### 4. Datos (no están en git)

Los PDF descargados, los fragmentos y los índices están en `.gitignore`. Dos opciones:

- **Copiarlos** desde otra máquina: descomprimir `normativa_datos.zip` en la raíz del
  proyecto (`unzip normativa_datos.zip`), que crea `data/raw`, `data/processed` y `data/index`.
- **Regenerarlos** (la descarga de la ULPGC tarda ~30 min porque su `robots.txt` pide
  10 s entre peticiones):

```bash
python scripts/descargar_normativa.py   # PDF de la ULPGC y la EII -> data/raw, data/manifests
python scripts/procesar_normativa.py    # texto y fragmentos      -> data/processed
python scripts/indexar_normativa.py     # BM25 + embeddings       -> data/index
```

### 5. Comprobar que todo funciona

```bash
python scripts/evaluar_busqueda.py --modelos Qwen/Qwen3-Embedding-0.6B
```

La fila `híbrido` debería dar un Acierto@5 de ~87 % con las 31 preguntas de
`data/eval/preguntas.jsonl`. Los modelos de Hugging Face se descargan la primera vez
(`~/.cache/huggingface`).

## Estructura

| Ruta | Qué es |
|---|---|
| `scripts/descargar_normativa.py` | Descarga la normativa de la ULPGC y la EII (respeta `robots.txt`) |
| `scripts/procesar_normativa.py` | Extrae el texto de los PDF y lo divide por artículos |
| `scripts/indexar_normativa.py` | Construye los índices BM25 y de embeddings |
| `scripts/evaluar_busqueda.py` | Mide la búsqueda con el banco de preguntas |
| `rag/busqueda.py` | Buscador híbrido (`Buscador.cargar()` + `.buscar(pregunta)`) |
| `data/manifests/` | Metadatos de cada documento descargado |
| `data/overrides.json` | Correcciones manuales de vigencia (normas derogadas que la web no marca) |
| `data/eval/preguntas.jsonl` | Banco de preguntas con su artículo correcto |
