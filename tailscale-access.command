#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PUBLIC_PORT="${PUBLIC_PORT:-8443}"

pause() {
  echo
  read -r -p "Enter drücken zum Schließen …" _ || true
}
trap pause EXIT

TAILSCALE=""
if command -v tailscale >/dev/null 2>&1; then
  TAILSCALE="$(command -v tailscale)"
elif [[ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]]; then
  TAILSCALE="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi

if [[ -z "$TAILSCALE" ]]; then
  echo "Tailscale wurde nicht gefunden."
  echo "Installiere zuerst die macOS-App von https://tailscale.com/download/mac"
  exit 1
fi

if ! "$TAILSCALE" status --peers=false >/dev/null 2>&1; then
  echo "Tailscale ist noch nicht verbunden."
  echo "Öffne die Tailscale-App, melde dich an und starte diese Datei erneut."
  exit 1
fi

if ! curl -kfsS --max-time 5 "https://127.0.0.1:${PUBLIC_PORT}/api/config" >/dev/null; then
  echo "Mini LLM antwortet noch nicht auf Port ${PUBLIC_PORT}."
  echo "Starte zuerst start.command und führe diese Datei danach erneut aus."
  exit 1
fi

echo
echo "Private Tailscale-Freigabe wird eingerichtet …"
"$TAILSCALE" serve --bg "https+insecure://127.0.0.1:${PUBLIC_PORT}"

SERVE_STATUS="$("$TAILSCALE" serve status)"
TAILSCALE_URL="$(printf '%s\n' "$SERVE_STATUS" | awk '/^https:/{print $1; exit}')"

echo
echo "✓ Mini LLM ist privat im Tailscale-Netz erreichbar."
if [[ -n "$TAILSCALE_URL" ]]; then
  echo
  echo "$TAILSCALE_URL"
fi
echo
echo "Auf dem iPhone muss Tailscale installiert, verbunden und für dasselbe"
echo "Tailscale-Netz freigeschaltet sein. Routerfreigabe und eigenes Zertifikat"
echo "sind für diese Adresse nicht nötig."
echo
echo "Aktuelle Freigabe:"
printf '%s\n' "$SERVE_STATUS"

