# Voraussetzungen und Abhängigkeiten

*Mini LLM – powered by AI-Implements · C. Lins*

## Pflicht

| Was | Warum | Installieren |
|---|---|---|
| **macOS 13 oder neuer** | Startskripte, Dauerdienst, WebKit | – |
| **Python 3.10 – 3.13** | Server | `brew install python@3.12` oder [python.org](https://www.python.org/downloads/macos/) |
| **Ollama** | führt die Sprachmodelle aus | [ollama.com/download](https://ollama.com/download) oder `brew install ollama` |
| **Ein Modell** | ohne Modell keine Antworten | `ollama pull gemma3:4b` |
| **openssl** | HTTPS-Zertifikat | bei macOS dabei |

> macOS bringt nur Python 3.9 mit – das reicht **nicht**. `start.command` sucht automatisch
> ein passendes Python und sagt Bescheid, falls keins da ist.

## Empfohlen

| Was | Wofür | Installieren |
|---|---|---|
| **Xcode Command Line Tools** | JOSHI lädt und bedient erzeugte Anwendungen in WebKit (Swift) | `xcode-select --install` |
| **Homebrew** | bequemes Installieren von Python und Ollama | [brew.sh](https://brew.sh) |
| **Tailscale** | sicherer Zugriff von unterwegs | [tailscale.com/download](https://tailscale.com/download) |

Ohne Command Line Tools funktioniert der Chat vollständig; JOSHI baut Anwendungen, kann sie
aber nicht im Browser prüfen.

## Hardware

| Arbeitsspeicher | Passende lokale Modelle |
|---|---|
| 8 GB | kleine Modelle bis ~4B (z. B. `gemma3:4b`) |
| 16 GB | 7–8B-Modelle (z. B. `qwen3:8b`, `granite4.1:8b`) |
| 32 GB+ | 14B und größer |

Cloud-Modelle von Ollama (Namen mit `:cloud`) laufen unabhängig vom Arbeitsspeicher, brauchen
aber eine Anmeldung in der Ollama-App und Internet.

## Python-Pakete

Werden von `start.command` automatisch in eine eigene Umgebung installiert
(`requirements.txt`):

| Paket | Aufgabe |
|---|---|
| fastapi, uvicorn, python-multipart | Webserver |
| httpx | Verbindung zu Ollama und Webseiten |
| argon2-cffi | sichere Passwörter |
| pypdf, python-docx, openpyxl, xlrd, lxml | Dokumente lesen |
| reportlab | PDF-Export |
| ddgs | Websuche (DuckDuckGo) |
| faster-whisper, yt-dlp | Transkription von Audio, Video, YouTube |
| psutil | Anzeige von CPU und Arbeitsspeicher |

## Prüfen

```bash
scripts/voraussetzungen.sh --pruefen
```
