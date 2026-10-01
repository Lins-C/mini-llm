#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/configure-public.sh" --quiet

if [[ ! -d "$ROOT/.venv" ]]; then
  source "$ROOT/scripts/voraussetzungen.sh"
  "$MINI_LLM_PYTHON" -m venv "$ROOT/.venv"
fi

if ! "$ROOT/.venv/bin/python" -c "import argon2, ddgs, docx, fastapi, faster_whisper, httpx, lxml, multipart, openpyxl, psutil, pypdf, reportlab, uvicorn, xlrd, yt_dlp" 2>/dev/null; then
  "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
fi

set -a
source "$ROOT/.env"
set +a

exec "$ROOT/.venv/bin/python" -m app.server
