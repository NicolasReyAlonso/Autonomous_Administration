#!/bin/zsh
source .venv/bin/activate
echo $(mlx_lm.generate --model mlx-community/gemma-4-e2b-it-4bit --max-tokens 2000 \
  --chat-template-config '{"enable_thinking": true}' \
  --prompt "Hola gemma")