#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -euo pipefail

cd "$(dirname "$0")"

source scripts/voraussetzungen.sh
if [[ ! -d ".venv" ]]; then
  "$MINI_LLM_PYTHON" -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import argon2, ddgs, fastapi, faster_whisper, httpx, lxml, multipart, pypdf, uvicorn, yt_dlp" 2>/dev/null; then
  python -m pip install -r requirements.txt
fi

if [[ -f ".env" ]]; then
  set -a
  source .env
  set +a
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
