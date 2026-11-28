#!/usr/bin/env python3
"""Entrena un adaptador LoRA de Gemma 4 (QLoRA, 4 bits) para resolver instancias.

Datos: data/sinteticas/entrenamiento.jsonl y validacion.jsonl (scripts/preparar_entrenamiento.py):
el prompt del resolutor (~12.600 fichas) y, como respuesta, el gold en JSON (~1.600 fichas).

Memoria (RTX 5060, 8 GB), ver rag/local.py para la carga:
  - la pérdida se calcula solo sobre la respuesta, por trozos y con recálculo: los logits de las
    ~14.000 posiciones (262.144 de vocabulario) no caben;
  - recálculo de activaciones por capa (gradient checkpointing) y las entradas de cada capa,
    guardadas en la RAM (save_on_cpu);
  - solo el LoRA (fp32) es entrenable; el modelo base queda congelado en 4 bits / bf16.

Uso (desde la raíz del proyecto, con el venv activado y LM Studio sin modelos cargados):
    python scripts/entrenar_lora.py --prueba                 # 2 pasos: memoria y tiempo por ejemplo
    python scripts/entrenar_lora.py                          # 1 época (~576 ejemplos)
    python scripts/entrenar_lora.py --modelo google/gemma-4-E2B-it --salida outputs/adapters/resolver-e2b

Salida: outputs/adapters/<nombre>/ (adaptador PEFT, registro.jsonl con la pérdida de cada paso).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel
from torch.utils.checkpoint import checkpoint

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.busqueda import RAIZ  # noqa: E402
from rag.local import MODELO_POR_DEFECTO, cargar_gemma  # noqa: E402

DATOS = RAIZ / "data" / "sinteticas"


def tokenizar(tok, mensajes: list[dict]) -> tuple[list[int], int]:
    """Fichas del ejemplo completo y cuántas son de la respuesta (las últimas)."""
    prompt = tok.apply_chat_template(mensajes[:-1], add_generation_prompt=True, tokenize=True, return_dict=False,
                                     enable_thinking=False)
    completo = tok.apply_chat_template(mensajes, tokenize=True, return_dict=False, enable_thinking=False)
    if completo[:len(prompt)] != prompt:
        raise ValueError("El prompt con add_generation_prompt no es prefijo del ejemplo completo")
    return completo, len(completo) - len(prompt)


def perdida(model, ids: torch.Tensor, n_resp: int, trozo: int) -> torch.Tensor:
    """Entropía cruzada media sobre las fichas de la respuesta, sin materializar todos los logits."""
    causal = model.get_base_model()          # Gemma4ForCausalLM (con las capas LoRA dentro)
    h = causal.model(input_ids=ids, use_cache=False).last_hidden_state
    h = h[:, -(n_resp + 1):-1, :]            # la posición t predice la ficha t + 1
    objetivo = ids[:, -n_resp:]
    cap = causal.config.final_logit_softcapping

    def trozo_ce(hh, yy):
        logits = causal.lm_head(hh).float()
        if cap:
            logits = torch.tanh(logits / cap) * cap
        return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), yy.reshape(-1), reduction="sum")

    total = h.new_zeros((), dtype=torch.float32)
    for i in range(0, n_resp, trozo):
        total = total + checkpoint(trozo_ce, h[:, i:i + trozo], objetivo[:, i:i + trozo], use_reentrant=False)
    return total / n_resp


def paso(model, ids, n_resp, trozo, entrenar: bool) -> float:
    ids = torch.tensor([ids], device=0)
    # autocast: el LoRA guarda sus pesos en fp32 (para el optimizador) pero calcula en bf16; si no,
    # su rama pasa a fp32 la capa intermedia del MLP (14.000 × 10.240) y no cabe
    with sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.FLASH_ATTENTION]), \
            torch.autocast("cuda", dtype=torch.bfloat16):
        if entrenar:
            with torch.autograd.graph.save_on_cpu(pin_memory=True):
                loss = perdida(model, ids, n_resp, trozo)
        else:
            with torch.no_grad():
                loss = perdida(model, ids, n_resp, trozo)
        if entrenar:  # dentro de sdpa_kernel: el recálculo de cada capa vuelve a llamar a la atención
            loss.backward()
    return float(loss)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    ap.add_argument("--entrenamiento", type=Path, default=DATOS / "entrenamiento.jsonl")
    ap.add_argument("--validacion", type=Path, default=DATOS / "validacion.jsonl")
    ap.add_argument("--salida", type=Path, default=RAIZ / "outputs" / "adapters" / "resolver-e4b")
    ap.add_argument("--epocas", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--acumulacion", type=int, default=8, help="ejemplos por paso del optimizador")
    ap.add_argument("--rango", type=int, default=16)
    ap.add_argument("--alfa", type=int, default=32)
    ap.add_argument("--trozo", type=int, default=128,
                    help="fichas por trozo al calcular la pérdida (cada trozo: trozo × 262.144 logits en fp32)")
    ap.add_argument("--max-ejemplos", type=int, help="usar solo los primeros N ejemplos de entrenamiento")
    ap.add_argument("--n-validacion", type=int, default=16, help="ejemplos de validación que se evalúan")
    ap.add_argument("--validar-cada", type=int, default=24, help="pasos del optimizador entre validaciones")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--prueba", action="store_true", help="2 ejemplos: mide memoria y tiempo y termina")
    args = ap.parse_args()

    random.seed(args.semilla)
    torch.manual_seed(args.semilla)
    t0 = time.time()
    model, tok = cargar_gemma(args.modelo, para_entrenar=True, rango=args.rango, alfa=args.alfa)
    for n, p in model.named_parameters():
        if p.requires_grad:
            p.data = p.data.float()
    entrenables = [p for p in model.parameters() if p.requires_grad]
    print(f"Modelo {args.modelo} cargado en {time.time() - t0:.0f} s · LoRA r={args.rango}: "
          f"{sum(p.numel() for p in entrenables) / 1e6:.1f} M parámetros entrenables · "
          f"GPU {torch.cuda.memory_allocated() / 2**30:.2f} GiB", flush=True)
    model.train()

    leer = lambda r: [json.loads(l) for l in r.read_text(encoding="utf-8").splitlines() if l.strip()]  # noqa: E731
    entrenamiento = leer(args.entrenamiento)[: args.max_ejemplos]
    validacion = leer(args.validacion)
    random.shuffle(entrenamiento)
    validacion = random.sample(validacion, min(args.n_validacion, len(validacion)))
    tokenizados = [tokenizar(tok, e["messages"]) for e in entrenamiento]
    val_tok = [tokenizar(tok, e["messages"]) for e in validacion]

    if args.prueba:
        for i in range(2):
            torch.cuda.reset_peak_memory_stats()
            t = time.time()
            loss = paso(model, *tokenizados[i], args.trozo, entrenar=True)
            torch.cuda.synchronize()
            print(f"  ejemplo {i}: {len(tokenizados[i][0])} fichas ({tokenizados[i][1]} de respuesta) · pérdida {loss:.3f} · "
                  f"{time.time() - t:.1f} s · pico GPU {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB", flush=True)
        return

    n_pasos = math.ceil(len(tokenizados) * args.epocas / args.acumulacion)
    calentamiento = max(1, n_pasos // 20)
    opt = torch.optim.AdamW(entrenables, lr=args.lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min(1.0, (s + 1) / calentamiento) * 0.5 * (1 + math.cos(math.pi * min(1.0, s / n_pasos))))
    args.salida.mkdir(parents=True, exist_ok=True)
    registro = (args.salida / "registro.jsonl").open("a", encoding="utf-8")
    print(f"{len(tokenizados)} ejemplos · {args.epocas} épocas · {n_pasos} pasos de {args.acumulacion} ejemplos", flush=True)

    def validar() -> float:
        model.eval()
        valor = sum(paso(model, *v, args.trozo, entrenar=False) for v in val_tok) / len(val_tok)
        model.train()
        return valor

    orden = [i % len(tokenizados) for i in range(math.ceil(len(tokenizados) * args.epocas))]
    t, acumuladas = time.time(), []
    for k, i in enumerate(orden, 1):
        acumuladas.append(paso(model, *tokenizados[i], args.trozo, entrenar=True))
        if k % args.acumulacion == 0 or k == len(orden):
            for p in entrenables:
                if p.grad is not None:
                    p.grad /= len(acumuladas)
            torch.nn.utils.clip_grad_norm_(entrenables, 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            s = math.ceil(k / args.acumulacion)
            fila = {"paso": s, "ejemplos": k, "perdida": round(sum(acumuladas) / len(acumuladas), 4),
                    "lr": sched.get_last_lr()[0], "segundos": round(time.time() - t, 1),
                    "gpu_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)}
            if s % args.validar_cada == 0 or k == len(orden):
                fila["validacion"] = round(validar(), 4)
                model.save_pretrained(args.salida)
            registro.write(json.dumps(fila) + "\n")
            registro.flush()
            resto = (time.time() - t) / k * (len(orden) - k)
            print(f"  paso {s:3}/{n_pasos} · pérdida {fila['perdida']:.3f}"
                  + (f" · validación {fila['validacion']:.3f}" if "validacion" in fila else "")
                  + f" · {fila['segundos'] / 60:.0f} min · faltan ~{resto / 60:.0f} min", flush=True)
            acumuladas = []
    model.save_pretrained(args.salida)
    print(f"Adaptador en {args.salida}")


if __name__ == "__main__":
    main()
