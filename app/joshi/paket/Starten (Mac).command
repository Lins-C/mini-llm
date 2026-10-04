#!/bin/bash
# Startet die Anwendung im Browser (siehe LIESMICH.txt).
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 start.py
fi
echo "Python 3 fehlt. Im Terminal einmal ausführen:  xcode-select --install"
echo "oder installieren von https://www.python.org/downloads/"
read -r -n 1 -p "Taste drücken zum Schließen …"
