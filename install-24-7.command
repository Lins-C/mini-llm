#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

"$ROOT/scripts/configure-public.sh" --quiet

LABEL="de.minillm.webui"
SERVICE_ROOT="$HOME/Library/Application Support/MiniLLM"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$SERVICE_ROOT/logs"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

mkdir -p "$PLIST_DIR" "$SERVICE_ROOT" "$LOG_DIR"
ditto "$ROOT/app" "$SERVICE_ROOT/app"
ditto "$ROOT/static" "$SERVICE_ROOT/static"
ditto "$ROOT/scripts" "$SERVICE_ROOT/scripts"
ditto "$ROOT/.certs" "$SERVICE_ROOT/.certs"
cp "$ROOT/requirements.txt" "$SERVICE_ROOT/requirements.txt"
cp "$ROOT/.env" "$SERVICE_ROOT/.env"
chmod 700 "$SERVICE_ROOT/.certs"
chmod 600 "$SERVICE_ROOT/.env" "$SERVICE_ROOT/.certs/"*.key
chmod +x "$SERVICE_ROOT/scripts/"*.sh

source "$ROOT/scripts/voraussetzungen.sh"
if [[ -d "$SERVICE_ROOT/.venv" ]] && ! "$SERVICE_ROOT/.venv/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  rm -rf "$SERVICE_ROOT/.venv"      # mit zu altem Python angelegt
fi
if [[ ! -d "$SERVICE_ROOT/.venv" ]]; then
  "$MINI_LLM_PYTHON" -m venv "$SERVICE_ROOT/.venv"
fi

if ! "$SERVICE_ROOT/.venv/bin/python" -c "import argon2, ddgs, docx, fastapi, faster_whisper, httpx, lxml, multipart, openpyxl, psutil, pypdf, reportlab, uvicorn, xlrd, yt_dlp" 2>/dev/null; then
  "$SERVICE_ROOT/.venv/bin/python" -m pip install -r "$SERVICE_ROOT/requirements.txt"
fi

{
  echo '<?xml version="1.0" encoding="UTF-8"?>'
  echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
  echo '<plist version="1.0">'
  echo '<dict>'
  echo '  <key>Label</key>'
  echo "  <string>$LABEL</string>"
  echo '  <key>ProgramArguments</key>'
  echo '  <array>'
  echo '    <string>/bin/bash</string>'
  echo "    <string>$SERVICE_ROOT/scripts/start-public-service.sh</string>"
  echo '  </array>'
  echo '  <key>WorkingDirectory</key>'
  echo "  <string>$SERVICE_ROOT</string>"
  echo '  <key>RunAtLoad</key>'
  echo '  <true/>'
  echo '  <key>KeepAlive</key>'
  echo '  <true/>'
  echo '  <key>ProcessType</key>'
  echo '  <string>Background</string>'
  echo '  <key>StandardOutPath</key>'
  echo "  <string>$LOG_DIR/webui.log</string>"
  echo '  <key>StandardErrorPath</key>'
  echo "  <string>$LOG_DIR/webui-error.log</string>"
  echo '</dict>'
  echo '</plist>'
} > "$PLIST"

plutil -lint "$PLIST"
BOOTSTRAP_OK=false
for _ in {1..15}; do
  if launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>"$LOG_DIR/launchctl-bootstrap.log"; then
    BOOTSTRAP_OK=true
    break
  fi
  # launchd benötigt nach bootout gelegentlich einen kurzen Moment, bevor
  # derselbe Dienstname erneut registriert werden kann.
  sleep 1
done
if [[ "$BOOTSTRAP_OK" != "true" ]]; then
  cat "$LOG_DIR/launchctl-bootstrap.log" >&2
  exit 1
fi

echo
echo "24/7-Autostart ist eingerichtet."
echo "Mini LLM startet künftig nach deiner macOS-Anmeldung automatisch."
echo "Dienstordner: $SERVICE_ROOT"
echo
echo "Wichtig: Aktiviere Ollama ebenfalls als Anmeldeobjekt und verhindere den Ruhezustand des Macs."
echo
if [[ "${1:-}" != "--non-interactive" ]]; then
  read -r -p "Enter drücken zum Schließen …" _
fi
