# Erste Schritte

*Mini LLM – powered by AI-Implements · C. Lins*

In fünf Minuten von null zur laufenden KI auf deinem Mac.

---

## Kurzfassung

1. **Ollama** installieren und öffnen → <https://ollama.com/download>
2. Ein Modell laden: `ollama pull gemma3:4b`
3. **`start.command` doppelklicken** – fertig. Der Browser öffnet sich von selbst.

Alles andere erledigt `start.command`: Voraussetzungen prüfen, Python-Umgebung anlegen,
Abhängigkeiten installieren, Zertifikat erzeugen, Dienst starten, Browser öffnen.

---

## Schritt für Schritt

### 1. Voraussetzungen prüfen

Einmal im Terminal im Projektordner:

```bash
scripts/voraussetzungen.sh --pruefen
```

Fehlt etwas, steht dort genau, was zu tun ist. Details: [VORAUSSETZUNGEN.md](VORAUSSETZUNGEN.md)

### 2. Ollama starten und ein Modell laden

Die Ollama-App öffnen (sie läuft danach im Hintergrund, erkennbar am Symbol in der
Menüleiste) und ein Modell laden:

```bash
ollama pull gemma3:4b
```

Welches Modell passt? Siehe [ANLEITUNGEN.md → Modell wählen](ANLEITUNGEN.md#modell-wählen).

### 3. Mini LLM starten

`start.command` im Finder doppelklicken.

> Beim allerersten Mal fragt macOS eventuell, ob die Datei geöffnet werden darf:
> Rechtsklick → **Öffnen** → **Öffnen** bestätigen. Das ist nur einmal nötig.

Der erste Start dauert einige Minuten, weil die Python-Abhängigkeiten geladen werden.
Danach startet Mini LLM in wenigen Sekunden.

### 4. Anmelden

Das Terminal zeigt die Zugangsdaten des ersten Nutzers (`Admin` / `admin@minillm.local`
und ein zufälliges Passwort). Sie stehen zusätzlich in `.env` im Projektordner.

- Mit diesen Daten anmelden
- Unter **Über mich** Name und Passwort anpassen
- Weitere Personen: in `.env` `ALLOW_REGISTRATION=true` setzen, dann über **Neuen Nutzer anlegen**

### 5. Loslegen

- **Chat:** Modell oben auswählen, Frage stellen, Dateien per Drag-and-drop dazulegen
- **Web:** Schalter „Web“ für Antworten mit aktuellen Quellen
- **JOSHI:** oben auf **JOSHI** – beschreiben, was du brauchst, JOSHI baut die Anwendung

---

## Wie geht es weiter?

| Ziel | Anleitung |
|---|---|
| Vom Handy zugreifen | [ANLEITUNGEN.md → Handy](ANLEITUNGEN.md#vom-handy-zugreifen) |
| Unterwegs per Tailscale | [ANLEITUNGEN.md → Tailscale](ANLEITUNGEN.md#unterwegs-mit-tailscale) |
| Dauerbetrieb rund um die Uhr | [ANLEITUNGEN.md → 24/7](ANLEITUNGEN.md#dauerbetrieb-247) |
| Etwas klappt nicht | [ANLEITUNGEN.md → Probleme lösen](ANLEITUNGEN.md#probleme-lösen) |
