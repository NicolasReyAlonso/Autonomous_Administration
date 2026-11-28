"""Generador de instancias sintéticas con su resolución de referencia (gold).

Cada módulo de trámite elige primero la rama de la decisión (qué requisito falla, si falla
alguno) y construye después unos datos coherentes con ella; el gold sale de las reglas de la
norma aplicable y el texto, de las mismas plantillas de redacción que los casos escritos a
mano de data/instancias/. Lo usa scripts/generar_instancias.py.
"""
