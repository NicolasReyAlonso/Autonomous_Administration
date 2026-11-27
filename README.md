# Diseño de una sistema de administración publica basada en Gemma 4 y aprendizaje

## Puesta en marcha en una máquina nueva

Requisitos: Python 3.12 y git. En el PC, una GPU NVIDIA RTX con driver >= 580
(`nvidia-smi` debe mostrar `CUDA Version: 13.x`). El proyecto se usa en un Mac con
Apple Silicon y en un PC Linux con RTX; ver las notas de `requirements.txt` si el
driver es más antiguo o la gráfica es otra.

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

La fila `híbrido` debería dar un Acierto@5 de 84-87 % (26-27 de las 31 preguntas de
`data/eval/preguntas.jsonl`; varía una pregunta según la máquina). Los modelos de
Hugging Face se descargan la primera vez (`~/.cache/huggingface`).

### 6. Hacer preguntas (búsqueda + Gemma 4)

La respuesta la redacta Gemma 4 E4B servido por [LM Studio](https://lmstudio.ai):

1. En LM Studio, descargar `gemma-4-E4B-it` (en el PC, el GGUF `Q4_K_M`, ~5 GB: cabe en
   los 8 GB de la RTX 5060 junto con el modelo de embeddings; en el Mac, la versión MLX).
2. Arrancar el servidor: pestaña *Developer* → *Start Server* (o `lms server start`).
   El modelo se carga solo con la primera pregunta.

```bash
python scripts/preguntar.py "¿Cuántos créditos se pueden compensar en un grado de 240 créditos?"
python scripts/preguntar.py                 # modo interactivo
python scripts/preguntar.py --sin-pensar    # sin razonamiento previo: ~9 s por respuesta en vez de ~25 s
```

Vale cualquier servidor con API compatible con OpenAI (`mlx_lm.server`, `llama-server`...):
se elige con `--url` y `--modelo` o con las variables `RAG_LLM_URL` y `RAG_LLM_MODELO`.

### 7. Evaluar las respuestas

```bash
python scripts/evaluar_respuestas.py                # las 31 preguntas, ~25 min
python scripts/evaluar_respuestas.py --sin-pensar   # sin razonamiento previo
```

Gemma 4 E4B responde todas las preguntas y después Gemma 4 12B (si está descargado en LM
Studio; si no, el propio E4B) hace de juez: compara cada respuesta con el texto de los
artículos correctos y la marca como correcta, parcial, incorrecta o sin respuesta. Respuestas,
razonamientos y veredictos quedan en `outputs/evaluaciones/` (`--resumen FICHERO` vuelve a
mostrar el resumen; `--rejuzgar FICHERO` repite solo el juicio).

## Estructura

| Ruta | Qué es |
|---|---|
| `scripts/descargar_normativa.py` | Descarga la normativa de la ULPGC y la EII (respeta `robots.txt`) |
| `scripts/descargar_plantillas.py` | Descarga los formularios de instancia y el Manual de normalización (modelos de resolución) a `data/plantillas/` |
| `scripts/procesar_normativa.py` | Extrae el texto de los PDF y lo divide por artículos |
| `scripts/indexar_normativa.py` | Construye los índices BM25 y de embeddings |
| `scripts/evaluar_busqueda.py` | Mide la búsqueda con el banco de preguntas |
| `scripts/preguntar.py` | Responde preguntas desde la terminal, citando los artículos |
| `scripts/evaluar_respuestas.py` | Mide las respuestas del RAG con el banco de preguntas (Gemma 12B de juez) |
| `rag/busqueda.py` | Buscador híbrido (`Buscador.cargar()` + `.buscar(pregunta)`) |
| `rag/responder.py` | RAG completo: busca los artículos y Gemma 4 redacta la respuesta con citas |
| `data/manifests/` | Metadatos de cada documento descargado |
| `data/overrides.json` | Correcciones manuales de vigencia (normas derogadas que la web no marca) |
| `data/eval/preguntas.jsonl` | Banco de preguntas con su artículo correcto |
