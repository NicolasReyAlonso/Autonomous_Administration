"""Gemma 4 en local con transformers (4 bits), con o sin adaptador LoRA: para entrenar y para evaluar.

En la RTX 5060 (8 GB) no cabe entero: los embeddings por capa (PLE, `embed_tokens_per_layer`,
262144 × 42 × 256 en E4B: 5,6 GB en bf16) se quedan en la CPU y solo su resultado pasa a la
GPU; el resto se cuantiza a 4 bits (NF4) con cómputo en bf16. Se carga solo el modelo de texto
(Gemma4ForCausalLM), sin las torres de visión y audio.

Uso:
    from rag.local import ClienteLocal
    llm = ClienteLocal("google/gemma-4-E4B-it", adaptador="outputs/adapters/resolver-e4b")
    # misma interfaz que rag.responder.ClienteLLM: Resolver(buscador, llm)
"""

from __future__ import annotations

import gc
import json
import time
from collections.abc import Iterator
from pathlib import Path

import torch

MODELO_POR_DEFECTO = "google/gemma-4-E4B-it"


def _peso_ple(ruta_modelo: str) -> torch.Tensor:
    """Lee del safetensors el peso de los embeddings por capa (en la CPU)."""
    from huggingface_hub import snapshot_download
    from safetensors import safe_open
    carpeta = Path(snapshot_download(ruta_modelo)) if not Path(ruta_modelo).exists() else Path(ruta_modelo)
    for fichero in sorted(carpeta.glob("*.safetensors")):
        with safe_open(fichero, framework="pt", device="cpu") as f:
            for k in f.keys():
                if k.endswith("embed_tokens_per_layer.weight"):
                    return f.get_tensor(k)
    raise RuntimeError(f"No encuentro embed_tokens_per_layer en {carpeta}")


TROZO_MLP = 2048  # fichas por trozo en el MLP al entrenar
BLOQUE_ATENCION = 512  # consultas por bloque en la atención de ventana deslizante


def atencion_local(sdpa_original):
    """Envuelve la atención SDPA de transformers para secuencias largas sin caché (entrenamiento y
    prefill con lote de 1 y sin relleno), con el mismo resultado:

    - capas de ventana deslizante (35 de 42 en E4B, ventana de 512): atención por bloques de
      BLOQUE_ATENCION consultas, cada uno solo con sus claves de la ventana. SDPA con la máscara
      calcula la matriz completa (L × L) y la enmascara: con ~14.000 fichas era la mitad del tiempo;
    - capas globales: causal sin máscara explícita, que usa el kernel flash.
    En cualquier otro caso (decodificación con caché, lotes, relleno) llama a la original.
    """
    import torch.nn.functional as F

    def sdpa(module, query, key, value, attention_mask, dropout=0.0, scaling=None, sliding_window=None, **kwargs):
        L = query.shape[2]
        if (L != key.shape[2] or L < 2 * BLOQUE_ATENCION or query.shape[0] != 1 or dropout
                or kwargs.get("softcap") is not None):
            return sdpa_original(module, query, key, value, attention_mask, dropout=dropout, scaling=scaling,
                                 sliding_window=sliding_window, **kwargs)
        grupos = query.shape[1] // key.shape[1]
        if grupos > 1:
            key, value = key.repeat_interleave(grupos, dim=1), value.repeat_interleave(grupos, dim=1)
        if not sliding_window:
            salida = F.scaled_dot_product_attention(query, key, value, is_causal=True, scale=scaling)
        else:
            partes = []
            for s in range(0, L, BLOQUE_ATENCION):
                e, ks = min(s + BLOQUE_ATENCION, L), max(0, s - sliding_window + 1)
                qi = torch.arange(s, e, device=query.device)[:, None]
                kj = torch.arange(ks, e, device=query.device)[None, :]
                mascara = (kj <= qi) & (kj > qi - sliding_window)  # como sliding_window_overlay de transformers
                partes.append(F.scaled_dot_product_attention(query[:, :, s:e], key[:, :, ks:e], value[:, :, ks:e],
                                                             attn_mask=mascara, scale=scaling))
            salida = torch.cat(partes, dim=2)
        return salida.transpose(1, 2).contiguous(), None

    sdpa._local = True
    return sdpa


def ahorrar_memoria(model) -> None:
    """Ajustes para entrenar con ~14.000 fichas en 8 GB (todos dejan el resultado igual):

    - SDPA sin enable_gqa: con él, la atención con máscara (ventana deslizante) caía en el kernel
      «math», que materializa la matriz de atención (+4,5 GB con 6.000 fichas); repitiendo K y V
      antes se usa el eficiente (+0,26 GB). Ver también el sdpa_kernel de scripts/entrenar_lora.py.
    - MLP por trozos de TROZO_MLP fichas, con recálculo por trozo: sus intermedios
      (4 × fichas × 10.240) son lo que más ocupa al recalcular cada capa.
    - Sin gradiente hacia los embeddings por capa (no tienen nada que entrenar).
    """
    import transformers.integrations.sdpa_attention as sdpa
    from torch.utils.checkpoint import checkpoint
    from transformers.models.gemma4 import modeling_gemma4 as mg

    sdpa.use_gqa_in_sdpa = lambda *args, **kwargs: False
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    if not getattr(ALL_ATTENTION_FUNCTIONS["sdpa"], "_local", False):
        ALL_ATTENTION_FUNCTIONS["sdpa"] = atencion_local(ALL_ATTENTION_FUNCTIONS["sdpa"])
    original = mg.Gemma4TextMLP.forward
    if not getattr(original, "_por_trozos", False):
        def mlp_por_trozos(self, x):
            if x.shape[1] <= TROZO_MLP:
                return original(self, x)
            if torch.is_grad_enabled():
                partes = [checkpoint(original, self, x[:, i:i + TROZO_MLP], use_reentrant=False)
                          for i in range(0, x.shape[1], TROZO_MLP)]
            else:
                partes = [original(self, x[:, i:i + TROZO_MLP]) for i in range(0, x.shape[1], TROZO_MLP)]
            return torch.cat(partes, dim=1)
        mlp_por_trozos._por_trozos = True
        mg.Gemma4TextMLP.forward = mlp_por_trozos
    texto = model.get_base_model().model if hasattr(model, "get_base_model") else model.model
    proyectar = texto.project_per_layer_inputs
    texto.project_per_layer_inputs = lambda *a, **k: proyectar(*a, **k).detach()


def cargar_gemma(modelo: str = MODELO_POR_DEFECTO, adaptador: str | Path | None = None,
                 para_entrenar: bool = False, rango: int = 16, alfa: int = 32, dropout: float = 0.0):
    """Devuelve (modelo, tokenizador). Con para_entrenar, el modelo lleva un LoRA nuevo entrenable."""
    from transformers import AutoConfig, AutoTokenizer, BitsAndBytesConfig
    from transformers.models.gemma4.modeling_gemma4 import Gemma4ForCausalLM

    tok = AutoTokenizer.from_pretrained(modelo)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16,
                             llm_int8_skip_modules=["lm_head", "embed_tokens", "embed_tokens_per_layer"])
    # La tabla de los PLE no pasa por from_pretrained: su clave se renombra a una que el modelo no
    # tiene (se ignora, como las de visión y audio) y, con un vocabulario mínimo en la
    # configuración, el módulo nace diminuto; la tabla real se lee del safetensors a la CPU. (Con
    # device_map «cpu», accelerate la subía a la GPU: 5,25 GB.)
    cfg = AutoConfig.from_pretrained(modelo).get_text_config()
    cfg.vocab_size_per_layer_input = 8
    # El checkpoint es el multimodal (model.language_model.*): se renombran las claves del texto
    claves = {r"^model\.language_model\.embed_tokens_per_layer": "ple_en_cpu.embed_tokens_per_layer",
              r"^model\.language_model\.": "model."}
    model = Gemma4ForCausalLM.from_pretrained(modelo, config=cfg, quantization_config=bnb, dtype=torch.bfloat16,
                                              device_map={"": 0}, attn_implementation="sdpa", key_mapping=claves)
    texto = model.model
    viejo = texto.embed_tokens_per_layer
    peso = _peso_ple(modelo).to(torch.bfloat16)
    nuevo = torch.nn.Embedding(peso.shape[0], peso.shape[1], _weight=peso, device="cpu")
    nuevo.weight.requires_grad_(False)
    escala = getattr(viejo, "embed_scale", None)
    escala = float(escala) if escala is not None else texto.hidden_size_per_layer_input ** 0.5
    texto.embed_tokens_per_layer = nuevo
    n_capas, dim = texto.config.num_hidden_layers, texto.hidden_size_per_layer_input

    def ple_en_cpu(input_ids, inputs_embeds=None):
        with torch.no_grad():
            salida = nuevo(input_ids.to("cpu")) * escala
        return salida.reshape(*input_ids.shape, n_capas, dim).to(input_ids.device)

    texto.get_per_layer_inputs = ple_en_cpu
    gc.collect()

    from peft import LoraConfig, PeftModel, get_peft_model
    destinos = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    if para_entrenar:
        # Sin prepare_model_for_kbit_training: pasaría a fp32 todo lo no cuantizado, también el
        # embedding (671 M parámetros, +2,5 GB). Base congelada; recálculo por capas con reentrada
        # (sus entradas se guardan como tensores y save_on_cpu las lleva a la RAM).
        for p in model.parameters():
            p.requires_grad_(False)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": True})
        model.enable_input_require_grads()
        # Sin dropout por defecto: cada capa LoRA guardaría una copia de su entrada
        model = get_peft_model(model, LoraConfig(r=rango, lora_alpha=alfa, lora_dropout=dropout, bias="none",
                                                 task_type="CAUSAL_LM", target_modules=destinos))
        ahorrar_memoria(model)
    elif adaptador:
        model = PeftModel.from_pretrained(model, str(adaptador))
        model.eval()
        ahorrar_memoria(model)
    else:
        model.eval()
        ahorrar_memoria(model)
    return model, tok


class ClienteLocal:
    """Misma interfaz que rag.responder.ClienteLLM (generar a trozos), con transformers en local.

    No aplica el esquema JSON (response_format): el modelo entrenado lo aprende; leer_salida
    tolera texto alrededor del JSON. Genera sin razonamiento previo (pensar=False).
    """

    def __init__(self, modelo: str = MODELO_POR_DEFECTO, adaptador: str | Path | None = None):
        self.modelo = f"{modelo}+{Path(adaptador).name}" if adaptador else modelo
        self.url = "local"
        self.model, self.tok = cargar_gemma(modelo, adaptador)

    def generar(self, mensajes: list[dict], pensar: bool = False, temperatura: float = 0.0,
                max_tokens: int = 4096, extra: dict | None = None) -> Iterator[tuple[str, str]]:
        ids = self.tok.apply_chat_template(mensajes, add_generation_prompt=True, return_tensors="pt",
                                           return_dict=True, enable_thinking=False)["input_ids"].to(0)
        from torch.nn.attention import SDPBackend, sdpa_kernel
        t = time.time()
        with torch.no_grad(), sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION, SDPBackend.MATH]):
            salida = self.model.generate(input_ids=ids, max_new_tokens=max_tokens, do_sample=temperatura > 0,
                                         temperature=temperatura or None, top_p=None, top_k=None)
        nuevos = salida[0, ids.shape[1]:]
        self.ultima = {"fichas_prompt": int(ids.shape[1]), "fichas_salida": int(nuevos.shape[0]),
                       "segundos": round(time.time() - t, 1)}
        yield "respuesta", self.tok.decode(nuevos, skip_special_tokens=True)
