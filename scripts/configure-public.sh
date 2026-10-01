#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

QUIET="${1:-}"
CERT_DIR="$ROOT/.certs"
ENV_FILE="$ROOT/.env"
INFO_FILE="$ROOT/.public-network.txt"
PUBLIC_PORT="${PUBLIC_PORT:-8443}"

if ! command -v openssl >/dev/null 2>&1; then
  echo "Fehler: openssl wurde nicht gefunden."
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  PASSWORD="$(openssl rand -hex 18)"
  {
    echo "OLLAMA_URL=http://127.0.0.1:11434"
    echo "MAX_UPLOAD_MB=250"
    echo "BOOTSTRAP_USER_NAME=Admin"
    echo "BOOTSTRAP_USER_EMAIL=admin@minillm.local"
    echo "BOOTSTRAP_USER_PASSWORD=$PASSWORD"
  } > "$ENV_FILE"
elif ! grep -Eq '^BOOTSTRAP_USER_PASSWORD=.+' "$ENV_FILE"; then
  PASSWORD="$(openssl rand -hex 18)"
  {
    grep -Eq '^BOOTSTRAP_USER_NAME=.+' "$ENV_FILE" || echo "BOOTSTRAP_USER_NAME=Admin"
    grep -Eq '^BOOTSTRAP_USER_EMAIL=.+' "$ENV_FILE" || echo "BOOTSTRAP_USER_EMAIL=admin@minillm.local"
    echo "BOOTSTRAP_USER_PASSWORD=$PASSWORD"
  } >> "$ENV_FILE"
fi

INTERFACE="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
LAN_IP=""
if [[ -n "$INTERFACE" ]]; then
  LAN_IP="$(ipconfig getifaddr "$INTERFACE" 2>/dev/null || true)"
fi
if [[ -z "$LAN_IP" ]]; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "$LAN_IP" ]]; then
  LAN_IP="127.0.0.1"
fi

GLOBAL_IPV6=""
if [[ -n "$INTERFACE" ]]; then
  # Der Router ordnet IPv6 Host Exposure der per DHCPv6 vergebenen
  # Adresse zu. macOS besitzt daneben meist weitere SLAAC-/Privacy-Adressen,
  # die trotz derselben MAC-Adresse von der Routerregel blockiert bleiben können.
  GLOBAL_IPV6="$(
    ipconfig getv6packet "$INTERFACE" 2>/dev/null |
      sed -n 's/.*IAADDR \([^ ]*:[^ ]*\) Preferred.*/\1/p' |
      head -n 1
  )"
fi
if [[ -z "$GLOBAL_IPV6" && -n "$INTERFACE" ]]; then
  GLOBAL_IPV6="$(
    ifconfig "$INTERFACE" 2>/dev/null |
      awk '$1 == "inet6" && $2 !~ /^fe80:/ && $2 != "::1" { print $2; exit }'
  )"
fi

PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org 2>/dev/null || true)"
if [[ ! "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  PUBLIC_IP=""
fi

mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

CA_KEY="$CERT_DIR/mini-llm-ca.key"
CA_CERT="$CERT_DIR/mini-llm-ca.crt"
SERVER_KEY="$CERT_DIR/server.key"
SERVER_CERT="$CERT_DIR/server.crt"
CERT_CONFIG="$CERT_DIR/server.cnf"
IP_STATE="$CERT_DIR/addresses.txt"
CURRENT_ADDRESSES="$LAN_IP|$PUBLIC_IP|$GLOBAL_IPV6"

if [[ ! -f "$CA_KEY" || ! -f "$CA_CERT" ]]; then
  openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
    -keyout "$CA_KEY" \
    -out "$CA_CERT" \
    -subj "/CN=Mini LLM private CA" >/dev/null 2>&1
  chmod 600 "$CA_KEY"
fi

PREVIOUS_ADDRESSES="$(cat "$IP_STATE" 2>/dev/null || true)"
if [[ ! -f "$SERVER_KEY" || ! -f "$SERVER_CERT" || "$PREVIOUS_ADDRESSES" != "$CURRENT_ADDRESSES" ]]; then
  {
    echo "[req]"
    echo "distinguished_name=dn"
    echo "prompt=no"
    echo "[dn]"
    echo "CN=Mini LLM"
    echo "[ext]"
    echo "subjectAltName=@alt"
    echo "keyUsage=digitalSignature,keyEncipherment"
    echo "extendedKeyUsage=serverAuth"
    echo "[alt]"
    echo "IP.1=127.0.0.1"
    echo "IP.2=$LAN_IP"
    NEXT_IP_INDEX=3
    if [[ -n "$PUBLIC_IP" ]]; then
      echo "IP.$NEXT_IP_INDEX=$PUBLIC_IP"
      NEXT_IP_INDEX=$((NEXT_IP_INDEX + 1))
    fi
    if [[ -n "$GLOBAL_IPV6" ]]; then
      echo "IP.$NEXT_IP_INDEX=$GLOBAL_IPV6"
    fi
  } > "$CERT_CONFIG"

  openssl req -new -newkey rsa:2048 -nodes \
    -keyout "$SERVER_KEY" \
    -out "$CERT_DIR/server.csr" \
    -config "$CERT_CONFIG" >/dev/null 2>&1
  openssl x509 -req -sha256 -days 825 \
    -in "$CERT_DIR/server.csr" \
    -CA "$CA_CERT" \
    -CAkey "$CA_KEY" \
    -CAcreateserial \
    -out "$SERVER_CERT" \
    -extfile "$CERT_CONFIG" \
    -extensions ext >/dev/null 2>&1
  chmod 600 "$SERVER_KEY"
  echo "$CURRENT_ADDRESSES" > "$IP_STATE"
fi

{
  echo "Mini LLM Netzwerkadressen"
  echo
  echo "Im Heimnetz: https://$LAN_IP:$PUBLIC_PORT"
  if [[ -n "$GLOBAL_IPV6" ]]; then
    echo "Aus dem Internet per IPv6: https://[$GLOBAL_IPV6]:$PUBLIC_PORT"
  else
    echo "Globale IPv6-Adresse konnte nicht ermittelt werden."
  fi
  if [[ -n "$PUBLIC_IP" ]]; then
    echo "Aus dem Internet per IPv4: https://$PUBLIC_IP:$PUBLIC_PORT"
  else
    echo "Öffentliche IPv4-Adresse konnte nicht ermittelt werden."
  fi
  echo
  echo "Router IPv6: Host Exposure für diesen Mac auf TCP $PUBLIC_PORT"
  echo "Router IPv4: TCP $PUBLIC_PORT extern -> $LAN_IP:$PUBLIC_PORT intern"
  echo "iPhone-Zertifikat: $CA_CERT"
} > "$INFO_FILE"

if [[ "$QUIET" != "--quiet" ]]; then
  echo
  echo "Mini LLM – direkter Internetzugriff"
  echo "====================================="
  cat "$INFO_FILE"
  echo
  echo "Erster Nutzer:"
  sed -n 's/^BOOTSTRAP_USER_EMAIL=//p' "$ENV_FILE" | tail -n 1
  echo "Erstes Passwort:"
  sed -n 's/^BOOTSTRAP_USER_PASSWORD=//p' "$ENV_FILE" | tail -n 1
  echo
  echo "Ohne die passende IPv6 Host Exposure oder IPv4-Portfreigabe im Router"
  echo "ist die jeweilige Internetadresse nicht erreichbar."
fi
