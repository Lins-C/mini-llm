#!/usr/bin/env bash
# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
#
# Findet ein passendes Python (3.10 oder neuer) und prüft, ob Ollama da ist.
#   source scripts/voraussetzungen.sh   → setzt MINI_LLM_PYTHON
#   scripts/voraussetzungen.sh --pruefen → zeigt nur den Stand an

python_finden() {
  local kandidat
  for kandidat in python3.12 python3.11 python3.13 python3.10 \
                  /opt/homebrew/bin/python3 /usr/local/bin/python3 \
                  /Library/Frameworks/Python.framework/Versions/Current/bin/python3 python3; do
    if command -v "$kandidat" >/dev/null 2>&1 && \
       "$kandidat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$kandidat"
      return 0
    fi
  done
  return 1
}

if ! MINI_LLM_PYTHON="$(python_finden)"; then
  echo
  echo "✗ Python 3.10 oder neuer wurde nicht gefunden."
  echo "  macOS bringt nur Python 3.9 mit. Bitte eines davon installieren:"
  echo "    brew install python@3.12"
  echo "    oder: https://www.python.org/downloads/macos/"
  echo "  Danach start.command erneut doppelklicken."
  [[ "${BASH_SOURCE[0]}" == "$0" ]] && exit 1 || return 1
fi
export MINI_LLM_PYTHON

if [[ "${1:-}" == "--pruefen" ]]; then
  echo "✓ Python: $MINI_LLM_PYTHON ($("$MINI_LLM_PYTHON" --version 2>&1))"
  if command -v ollama >/dev/null 2>&1 || [[ -d /Applications/Ollama.app || -d "$HOME/Applications/Ollama.app" ]]; then
    echo "✓ Ollama ist installiert"
  else
    echo "✗ Ollama fehlt – https://ollama.com/download (oder: brew install ollama)"
  fi
  if command -v swiftc >/dev/null 2>&1; then echo "✓ Swift (für JOSHIs Browserprüfung)"
  else echo "• Swift fehlt – optional für JOSHI: xcode-select --install"; fi
  command -v openssl >/dev/null 2>&1 && echo "✓ openssl" || echo "✗ openssl fehlt"
fi
