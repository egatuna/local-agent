#!/usr/bin/env bash
# One-time setup for the local agent on Apple Silicon (8 GB-friendly).
set -euo pipefail

echo "==> Installing Ollama (via Homebrew)…"
if ! command -v ollama >/dev/null 2>&1; then
  brew install ollama
else
  echo "    ollama already installed: $(ollama --version)"
fi

echo "==> Starting the Ollama server (background, memory-optimized)…"
# Flash attention + q8_0 KV cache: halves context-window memory, ~no quality
# loss — the single biggest lever on 8 GB unified memory.
# To make these stick for manually-started servers, add to ~/.zshenv:
#   export OLLAMA_FLASH_ATTENTION=1
#   export OLLAMA_KV_CACHE_TYPE=q8_0
pgrep -x ollama >/dev/null 2>&1 || \
  (OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 ollama serve >/tmp/ollama.log 2>&1 &)
sleep 2

echo "==> Pulling models sized for 8 GB unified memory…"
ollama pull qwen3.5:2b-q4_K_M   # ~1.9 GB — speed tier: auto-picked with --escalate (42+ tok/s)
ollama pull qwen3.5:4b          # ~3.4 GB — mid tier: best small agentic model (2026-03)
# Optional extras:
# ollama pull qwen2.5-coder:7b  # ~4.7 GB — older code specialist; swaps on 8 GB
# ollama pull llama3.2:3b       # ~2 GB  — light general fallback

echo "==> Python deps…"
python3 -m pip install --quiet --upgrade -r requirements.txt

echo "==> Done. Try:  python3 local_agent.py \"write and test a fizzbuzz\""
