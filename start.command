#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PUBLIC_PORT="${PUBLIC_PORT:-8443}"
LOCAL_URL="https://127.0.0.1:${PUBLIC_PORT}"
OLLAMA_LOG="$ROOT/logs/ollama.log"
CURRENT_STEP="Start wird vorbereitet"
ERROR_LINE=""

remember_error() {
  local exit_code=$?
  ERROR_LINE="${BASH_LINENO[0]:-unbekannt}"
  return "$exit_code"
}

pause_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    echo
    echo "Mini LLM konnte nicht vollständig gestartet werden."
    echo "Fehlgeschlagener Schritt: $CURRENT_STEP"
    [[ -n "$ERROR_LINE" ]] && echo "Skriptzeile: $ERROR_LINE"
    if [[ -f "$HOME/Library/Application Support/MiniLLM/logs/webui-error.log" ]]; then
      echo
      echo "Letzte Meldungen des Webdienstes:"
      tail -n 18 "$HOME/Library/Application Support/MiniLLM/logs/webui-error.log" || true
    fi
    echo
    read -r -p "Enter drücken zum Schließen …" _ || true
  fi
  exit "$exit_code"
}
trap remember_error ERR
trap pause_on_error EXIT

echo
echo "Mini LLM wird gestartet …"
echo
CURRENT_STEP="Voraussetzungen werden geprüft"
"$ROOT/scripts/voraussetzungen.sh" --pruefen
echo

# Ollama möglichst automatisch starten. Falls die Desktop-App nicht installiert
# ist, wird die Kommandozeilenversion im Hintergrund verwendet.
if ! curl -fsS --max-time 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
  if [[ -d "/Applications/Ollama.app" || -d "$HOME/Applications/Ollama.app" ]]; then
    CURRENT_STEP="Ollama wird geöffnet"
    if ! open -gj -a "Ollama"; then
      echo "Hinweis: Die Ollama-App konnte nicht automatisch geöffnet werden."
    fi
  elif command -v ollama >/dev/null 2>&1; then
    mkdir -p "$ROOT/logs"
    nohup "$(command -v ollama)" serve >>"$OLLAMA_LOG" 2>&1 &
  else
    echo "Hinweis: Ollama wurde nicht gefunden. Die WebUI startet trotzdem."
  fi
fi

ERSTER_START=false
[[ -f "${MINI_LLM_DATA_DIR:-$HOME/Library/Application Support/MiniLLM/data}/mini-llm.sqlite3" ]] || ERSTER_START=true
SERVICE_WAS_READY=false
if curl -kfsS --max-time 2 "$LOCAL_URL/api/config" >/dev/null 2>&1; then
  SERVICE_WAS_READY=true
fi
SERVICE_ROOT="$HOME/Library/Application Support/MiniLLM"
SOURCE_CHANGED=false
for SOURCE_FILE in "$ROOT"/app/*.py "$ROOT"/static/* "$ROOT"/scripts/*.sh "$ROOT"/requirements.txt; do
  RELATIVE_FILE="${SOURCE_FILE#"$ROOT"/}"
  if [[ ! -f "$SERVICE_ROOT/$RELATIVE_FILE" ]] || ! cmp -s "$SOURCE_FILE" "$SERVICE_ROOT/$RELATIVE_FILE"; then
    SOURCE_CHANGED=true
    break
  fi
done
CERT_STATE_BEFORE="$(cat "$ROOT/.certs/addresses.txt" 2>/dev/null || true)"

# Ermittelt die aktuellen LAN-/Internetadressen und erneuert bei einer
# Adressänderung automatisch das lokale HTTPS-Zertifikat.
CURRENT_STEP="Netzwerkadressen und HTTPS-Zertifikat werden geprüft"
if ! "$ROOT/scripts/configure-public.sh" --quiet; then
  echo "Hinweis: Die öffentlichen Netzwerkadressen konnten nicht aktualisiert werden."
  if [[ "$SERVICE_WAS_READY" != "true" ]]; then
    exit 1
  fi
fi
CERT_STATE_AFTER="$(cat "$ROOT/.certs/addresses.txt" 2>/dev/null || true)"

# Ein bereits gesunder Dienst wird nicht bei jedem Doppelklick neu gestartet.
# So laufen Chat- und Cowork-Aufträge beim Öffnen der Startdatei ungestört weiter.
# Nur ein fehlender Dienst oder ein erneuertes Zertifikat erfordert die Installation.
if [[ "$SERVICE_WAS_READY" != "true" || "$SOURCE_CHANGED" == "true" || "$CERT_STATE_BEFORE" != "$CERT_STATE_AFTER" ]]; then
  CURRENT_STEP="Der dauerhafte Webdienst wird eingerichtet"
  "$ROOT/install-24-7.command" --non-interactive
else
  echo "✓ Der 24/7-Dienst läuft bereits und bleibt ohne Neustart aktiv"
fi

WEB_READY=false
CURRENT_STEP="Der Webdienst wird geprüft"
for _ in {1..60}; do
  if curl -kfsS --max-time 2 "$LOCAL_URL/api/config" >/dev/null 2>&1; then
    WEB_READY=true
    break
  fi
  sleep 1
done

if [[ "$WEB_READY" != "true" ]]; then
  echo "Fehler: Der Webdienst antwortet nicht unter $LOCAL_URL."
  echo "Protokoll: $HOME/Library/Application Support/MiniLLM/logs/webui-error.log"
  exit 1
fi

OLLAMA_READY=false
for _ in {1..15}; do
  if curl -fsS --max-time 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    OLLAMA_READY=true
    break
  fi
  sleep 1
done

LAN_URL=""
INTERNET_IPV6_URL=""
INTERNET_IPV4_URL=""
if [[ -f "$ROOT/.public-network.txt" ]]; then
  LAN_URL="$(sed -n 's/^Im Heimnetz: //p' "$ROOT/.public-network.txt" | head -n 1)"
  INTERNET_IPV6_URL="$(
    sed -n 's/^Aus dem Internet per IPv6: //p' "$ROOT/.public-network.txt" | head -n 1
  )"
  INTERNET_IPV4_URL="$(
    sed -n 's/^Aus dem Internet per IPv4: //p' "$ROOT/.public-network.txt" | head -n 1
  )"
fi
TAILSCALE_URL=""
TAILSCALE=""
if command -v tailscale >/dev/null 2>&1; then
  TAILSCALE="$(command -v tailscale)"
elif [[ -x "/Applications/Tailscale.app/Contents/MacOS/Tailscale" ]]; then
  TAILSCALE="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
fi
if [[ -n "$TAILSCALE" ]]; then
  # „tailscale serve status" endet mit Code 1, sobald Tailscale gestoppt ist.
  # Ohne das abschließende || true bricht der gesamte Start ab, obwohl die
  # WebUI längst läuft. Tailscale ist eine Zugabe, keine Startbedingung.
  TAILSCALE_STATUS="$("$TAILSCALE" serve status 2>/dev/null || true)"
  TAILSCALE_URL="$(printf '%s\n' "$TAILSCALE_STATUS" | awk '/^https:/{print $1; exit}')"
fi

CURRENT_STEP="Die WebUI wird im Browser geöffnet"
if ! open "$LOCAL_URL"; then
  echo "Hinweis: Der Browser konnte nicht automatisch geöffnet werden."
  echo "Öffne die Adresse bitte manuell: $LOCAL_URL"
fi

echo "✓ WebUI läuft dauerhaft"
if [[ "$OLLAMA_READY" == "true" ]]; then
  echo "✓ Ollama ist verbunden"
else
  echo "! Ollama ist noch nicht erreichbar. Bitte die Ollama-App öffnen."
fi
echo
echo "Auf diesem Mac:  $LOCAL_URL"
[[ -n "$LAN_URL" ]] && echo "Im Heimnetz:      $LAN_URL"
[[ -n "$INTERNET_IPV6_URL" ]] && echo "Internet (IPv6):  $INTERNET_IPV6_URL"
[[ -n "$INTERNET_IPV4_URL" ]] && echo "Internet (IPv4):  $INTERNET_IPV4_URL"
[[ -n "$TAILSCALE_URL" ]] && echo "Privat (Tailscale): $TAILSCALE_URL"
if [[ -n "$TAILSCALE" && -z "$TAILSCALE_URL" ]]; then
  echo "! Tailscale ist gestoppt. Die private Adresse ist gerade nicht"
  echo "  erreichbar. Öffne dazu die Tailscale-App und melde dich an."
fi
echo
if [[ "$ERSTER_START" == "true" ]]; then
  echo "Erste Anmeldung:"
  echo "  E-Mail:   $(sed -n 's/^BOOTSTRAP_USER_EMAIL=//p' "$ROOT/.env" | tail -n 1)"
  echo "  Passwort: $(sed -n 's/^BOOTSTRAP_USER_PASSWORD=//p' "$ROOT/.env" | tail -n 1)"
  echo "  (steht auch in .env – nach der Anmeldung unter „Über mich“ ändern)"
  echo
fi
echo "Die WebUI wurde im Browser geöffnet."
echo "Der 24/7-Dienst läuft weiter, wenn dieses Fenster geschlossen wird."
echo
if [[ -n "$TAILSCALE_URL" ]]; then
  echo "Empfohlen unterwegs: Nutze die feste private Tailscale-Adresse oben."
  echo "Sie benötigt keine Routerfreigabe und kein eigenes iPhone-Zertifikat."
  echo
fi
echo "Zugriff von unterwegs: siehe docs/ANLEITUNGEN.md (Tailscale empfohlen)."
echo
read -r -p "Enter drücken zum Schließen …" _ || true

trap - ERR EXIT
