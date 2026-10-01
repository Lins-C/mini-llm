# Mini LLM

*powered by AI-Implements · C. Lins*

Eine private, selbst gehostete KI-Oberfläche für [Ollama](https://ollama.com/) – mit Chat,
Dokumentenarbeit, Websuche und **JOSHI**, das aus einer Idee eine geprüfte, teilbare
Web-Anwendung baut. Alles läuft auf deinem eigenen Rechner; Daten verlassen ihn nur, wenn du
ausdrücklich ein Cloud-Modell oder die Websuche nutzt.

> Optimiert für macOS auf Apple Silicon (M1–M4). Der Chat läuft auch unter Linux;
> JOSHIs Browserprüfung nutzt WebKit von macOS.

## Schnellstart

1. **Ollama** installieren und öffnen – <https://ollama.com/download>
2. Ein Modell laden: `ollama pull gemma3:4b`
3. **`start.command` doppelklicken** – los geht's.

`start.command` prüft die Voraussetzungen, richtet alles ein, startet Mini LLM dauerhaft im
Hintergrund, öffnet den Browser und zeigt beim ersten Mal die Zugangsdaten an.

| Dokumentation | |
|---|---|
| [Erste Schritte](docs/ERSTE-SCHRITTE.md) | in fünf Minuten startklar |
| [Voraussetzungen](docs/VORAUSSETZUNGEN.md) | was installiert sein muss und warum |
| [Anleitungen](docs/ANLEITUNGEN.md) | Modelle, Handy, Tailscale, 24/7, JOSHI, Update, Backup, Probleme lösen |
| [JOSHI-Architektur](docs/JOSHI.md) | wie JOSHI Anwendungen baut und prüft |
| [Mitmachen](CONTRIBUTING.md) · [Sicherheit](SECURITY.md) · [Änderungen](CHANGELOG.md) | |

---

## Funktionen

**Chat**
- Lokale und Cloud-Modelle von Ollama, Antworten live gestreamt
- Aufträge laufen serverseitig weiter, auch wenn der Browser geschlossen wird
- Dateien als Kontext: PDF, Word, Excel, CSV, Code, Text, ZIP-Archive, ganze Ordner
- Bilder mit Vision-Modellen, Audio/Video/YouTube per lokalem Whisper transkribiert
- Zuschaltbare Websuche mit Quellen
- Export von Antworten als DOCX, XLSX, PDF oder E-Mail-Entwurf
- Skills für Brief, Bericht, Protokoll, Übersetzung, Zusammenfassung, Analyse
- Mehrere Nutzer mit Anmeldung (Argon2), getrennte Chats und Projektordner
- Responsiv für Desktop und Handy, heller und dunkler Modus

**JOSHI – Idee → Anwendung**
- Beschreibe, was du brauchst („Baue einen ROI-Rechner …“), gern mit Bildern oder Dateien
- JOSHI baut eine eigenständige HTML-Anwendung, **lädt und bedient sie im Browser**,
  prüft sie gegen einen Abnahmevertrag und repariert gefundene Fehler selbst
- Jede Änderung wird eine neue Version; „Rückgängig“ holt die vorige zurück
- Große Änderungen in geprüften Schritten, große Anwendungen intern als Projektdateien
- **Web-Schalter:** recherchiert aktuelle Produkte und Preise mit Quelle, bevor gebaut wird
- Export als PNG/JPG, PDF (A4, eine Seite wenn möglich), Word; Teilen als HTML oder ZIP

Details zur Architektur: [docs/JOSHI.md](docs/JOSHI.md)

---

## Voraussetzungen

| | |
|---|---|
| Betriebssystem | macOS 13 oder neuer (Apple Silicon empfohlen), Linux für den Chat |
| Python | 3.10 oder neuer |
| Ollama | aktuelle Version, siehe unten |
| Xcode Command Line Tools | für JOSHIs WebKit-Prüfung (`xcode-select --install`) |
| Arbeitsspeicher | 16 GB empfohlen für lokale 8B-Modelle |

---

## Installation

### 1. Ollama installieren

**macOS:** Die App von [ollama.com/download](https://ollama.com/download) laden und installieren,
oder mit Homebrew:

```bash
brew install ollama
```

**Linux:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Anschließend mindestens ein Modell laden, zum Beispiel:

```bash
ollama pull gemma3:4b          # klein und schnell
ollama pull qwen3:8b           # stärker, braucht ~8 GB RAM
```

Cloud-Modelle von Ollama (Namen mit `:cloud`) funktionieren ebenfalls, sobald du in der
Ollama-App angemeldet bist.

### 2. Mini LLM holen

```bash
git clone https://github.com/Lins-C/mini-llm.git
cd mini-llm
cp .env.example .env           # optional anpassen, siehe „Konfiguration“
```

### 3. Starten

**macOS:** `start.command` doppelklicken. Das Skript prüft die Voraussetzungen (Python ab 3.10,
Ollama), startet Ollama, legt eine Python-Umgebung an, installiert die Abhängigkeiten, richtet
den Dauerdienst ein und öffnet <https://127.0.0.1:8443>. Beim allerersten Öffnen fragt macOS
eventuell nach: Rechtsklick → **Öffnen**.

**Terminal (macOS und Linux):**

```bash
chmod +x start.sh
./start.sh
```

Dann im Browser öffnen: <http://localhost:8000> (ohne Dauerdienst, gut zum Ausprobieren)

### Erster Start und Anmeldung

Beim allerersten Start ist die Datenbank leer. Mini LLM legt dann einen ersten Nutzer an:

- Name und E-Mail aus `.env` (`BOOTSTRAP_USER_NAME`, `BOOTSTRAP_USER_EMAIL`),
  sonst `Admin` / `admin@minillm.local`
- Passwort aus `BOOTSTRAP_USER_PASSWORD` – ist es leer, erzeugt Mini LLM ein **zufälliges
  Passwort**. Es steht im Terminal bzw. Protokoll und in `erstes-passwort.txt` im Datenordner
  (nur für dich lesbar). Nach der ersten Anmeldung ändern und die Datei löschen.

Weitere Personen: In `.env` `ALLOW_REGISTRATION=true` setzen und neu starten – dann legen sie über
„Neuen Nutzer anlegen“ eigene Konten an; ihre Chats und Daten bleiben getrennt.

> **Mehrere Installationen auf einem Rechner:** Alle nutzen standardmäßig denselben
> Datenordner (`~/Library/Application Support/MiniLLM/data`). Für eine zweite, getrennte
> Installation vorher `MINI_LLM_DATA_DIR` auf einen eigenen Ordner setzen, zum Beispiel
> `MINI_LLM_DATA_DIR=~/mini-llm-test ./start.sh`.

---

## Zugriff vom Handy

### Im selben WLAN

```bash
ipconfig getifaddr en0         # IP des Rechners ermitteln (macOS)
```

Auf dem Handy `http://<IP-des-Rechners>:8000` öffnen. Die macOS-Firewall muss eingehende
Verbindungen für Python erlauben.

### Unterwegs mit Tailscale (optional, empfohlen)

[Tailscale](https://tailscale.com/) verbindet deine Geräte privat – ohne Portfreigabe im
Router und mit gültigem HTTPS-Zertifikat.

1. Tailscale auf dem Rechner und dem Handy installieren und mit demselben Konto anmelden.
2. Mini LLM einmal mit `start.command` starten.
3. `tailscale-access.command` doppelklicken.
4. Die angezeigte feste Adresse `https://<rechner>.<tailnet>.ts.net` auf dem Handy öffnen.

Die Freigabe bleibt nach einem Neustart bestehen. Weitere Personen lädst du in dein
Tailscale-Netz ein; die Anmeldung in Mini LLM trennt ihre Daten weiterhin.

### Direkt über das Internet (fortgeschritten)

`start-public.command` startet Mini LLM mit HTTPS auf Port `8443` und einer eigenen, lokal
erzeugten Zertifizierungsstelle. Die Router-Freigabe richtest du selbst ein;
`network-info.command` zeigt die nötigen Adressen. Wer nur privat zugreifen will, ist mit
Tailscale einfacher und sicherer unterwegs.

---

## Dauerbetrieb (24/7, macOS)

```bash
./install-24-7.command         # oder doppelklicken
```

Mini LLM startet dann nach jeder Anmeldung automatisch und wird nach einem Absturz neu
gestartet. Der Installer legt eine Laufzeitkopie unter
`~/Library/Application Support/MiniLLM` an; nach Updates einfach erneut ausführen.
Entfernen mit `uninstall-24-7.command`.

Zusätzlich sinnvoll: Ollama als Anmeldeobjekt aktivieren und den Ruhezustand verhindern.

---

## Konfiguration

Alle Werte stehen in `.env` (Vorlage: [.env.example](.env.example)).

| Variable | Standard | Bedeutung |
|---|---|---|
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Adresse des Ollama-Servers |
| `PORT` | `8000` | Port der Oberfläche |
| `MINI_LLM_DATA_DIR` | macOS: `~/Library/Application Support/MiniLLM/data` | Datenordner (Datenbank, Caches, JOSHI-Projekte) |
| `BOOTSTRAP_USER_NAME` | `Admin` | Name des ersten Nutzers |
| `BOOTSTRAP_USER_EMAIL` | `admin@minillm.local` | E-Mail des ersten Nutzers |
| `BOOTSTRAP_USER_PASSWORD` | automatisch | Passwort des ersten Nutzers |
| `ALLOW_REGISTRATION` | `false` | Neue Nutzer dürfen sich selbst registrieren (für Familie/Team auf `true`) |
| `SESSION_DAYS` | `365` | Dauer einer Anmeldung |
| `MAX_UPLOAD_MB` | `250` | Upload-Limit pro Nachricht |
| `WHISPER_MODEL` | `small` | Lokales Whisper-Modell (`tiny` … `large-v3`) |
| `WEB_RESULTS` | `5` | Treffer der Websuche |
| `OLLAMA_CLOUD_USAGE_API_KEY` | – | Optional: zeigt den Ollama-Cloud-Verbrauch an |

Weitere Grenzen für große Dateien und den Chatverlauf sind in `.env.example` beschrieben.

---

## Datenschutz und Sicherheit

- Chats, Dokumente, Produkte und Einstellungen liegen in einer lokalen SQLite-Datenbank im
  Datenordner – nicht im Projektordner und nie im Repository.
- `.env`, Zertifikate (`.certs/`), Datenbank und Logs sind per `.gitignore` ausgeschlossen.
  Den Schlüssel `.certs/mini-llm-ca.key` niemals weitergeben.
- Ohne Cloud-Modell und ohne Websuche verlässt nichts deinen Rechner.
- JOSHI-Anwendungen laufen in einem abgeschotteten Rahmen ohne Netzwerkzugriff.

---

## Hinweis zur Nutzung

Websuche (DuckDuckGo), das Laden von Webseiten und die YouTube-Transkription (yt-dlp) bitte nur
für Inhalte verwenden, zu deren Nutzung du berechtigt bist, und die Bedingungen der jeweiligen
Anbieter beachten. Antworten von Sprachmodellen können falsch sein – wichtige Angaben prüfen.

## Entwicklung und Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MINI_LLM_DATA_DIR=$(mktemp -d) PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -q
```

Tests schreiben nie in echte Daten: Ohne `MINI_LLM_DATA_DIR` nimmt die Testumgebung
automatisch einen Wegwerf-Ordner. Die WebKit-Tests von JOSHI laufen nur auf macOS und werden
sonst übersprungen.

### Aufbau

```text
app/            Server (FastAPI), Chat, Exporte, Websuche
app/joshi/      JOSHI: Pipeline, Abnahme, Recherche, Projektdateien, WebKit-Renderer
static/         Oberfläche (HTML, CSS, JavaScript)
tests/          Unit- und Browser-Tests
docs/           Architektur und Entwicklungsnotizen
scripts/        Hilfsskripte für Dienst, Netzwerk und Vorlagen
*.command       Startskripte für macOS (Doppelklick)
```

---

## Lizenz und Urheber

**Mini LLM – powered by AI-Implements · C. Lins**

Veröffentlicht unter der [MIT-Lizenz](LICENSE): Du darfst den Code frei verwenden, verändern,
erweitern und weitergeben – auch kommerziell. Bedingung: Der Urheberhinweis mit
„powered by AI-Implements · C. Lins“ und der Lizenztext bleiben in allen Kopien und abgeleiteten
Werken erhalten. Jede Quelldatei trägt diesen Hinweis als Kopfkommentar – bitte stehen lassen.

Name und Logo „AI-Implements“ sind von der Lizenz ausgenommen und dürfen nur zur Nennung des Urhebers verwendet werden. Eigene Ableger bitte mit eigenem Namen und Logo veröffentlichen.
