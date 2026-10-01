# Mitmachen

*Mini LLM – powered by AI-Implements · C. Lins*

Danke, dass du Mini LLM verbessern willst! Beiträge sind willkommen – Fehlerberichte, Ideen,
Dokumentation und Code.

## Kurz und knapp

1. Repository forken und einen Branch anlegen: `git checkout -b mein-thema`
2. Änderung machen – im Stil des umgebenden Codes (deutsche Bezeichner, knappe Kommentare,
   die erklären **warum**)
3. Tests laufen lassen:
   ```bash
   MINI_LLM_DATA_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q
   ```
4. Pull Request mit kurzer Beschreibung: Was war das Problem, was ändert sich, wie getestet?

## Regeln

- **Urheberhinweis bleibt:** Der Kopfkommentar „powered by AI-Implements · C. Lins“ steht in
  jeder Quelldatei und bleibt erhalten. Neue Dateien bekommen denselben Kopf.
- **Keine persönlichen Daten:** keine echten Namen, Adressen, Schlüssel oder `.env`-Inhalte in
  Code, Tests oder Issues. Für Beispiele: Max Mustermann, Beispiel GmbH, Musterstadt.
- **Neue Funktion = neuer Test.** Fehlerbehebungen bekommen einen Test, der den Fehler zeigt.
- **Oberfläche geändert?** Die Versionsnummer `?v=` in `static/index.html` hochzählen, sonst
  sehen Nutzer die alte Fassung aus dem Browser-Cache.

## Lizenz

Mit deinem Beitrag stimmst du zu, dass er unter der [MIT-Lizenz](LICENSE) des Projekts
veröffentlicht wird.
