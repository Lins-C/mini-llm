> **Stand 19.09.2026:** Umgesetzt. Die aktuelle Architektur beschreibt [JOSHI.md](JOSHI.md). Abweichend von diesem Plan wurde der Code-Harness gleich mit ersetzt (Archiv: `archiv/coding-harness/`); die Modellschicht blieb in `app/main.py` und wird JOSHI als `MiniLLMModellzugang` hereingereicht.

# JOSHI – Repository-Audit und Migrationsplan (Phase 1)

Stand: 2026-09-19. Dieser Befund beschreibt den vorhandenen Bestand und einen
inkrementellen Migrationsweg. Er implementiert **keine** JOSHI-Produktfunktion
und ändert keine bestehende Laufzeit außer dieser Dokumentation.

## Ziel und Leitplanken

JOSHI (*Just On-demand Software from Human Intent*) wird eine zweite,
produktorientierte Arbeitsfläche neben dem unveränderten Chat. Es erzeugt in V1
eine selbstenthaltende einzelne HTML-Datei, führt sie in einer isolierten
Browser-Runtime aus und setzt den Status `READY` nur nach technischer Prüfung.

Dabei gelten folgende Architekturentscheidungen:

- JOSHI verwendet ausschließlich die bestehende zentrale Mini-LLM-
  Modellschicht; keine eigene Ollama-URL, keine direkte Browser-zu-Ollama-
  Verbindung und keine fest eincodierten Modellnamen.
- JOSHI ist ein begrenzter Produkt-Lifecycle (`UNDERSTAND → BUILD → VALIDATE →
  optional REPAIR → READY → REFINE → EXPORT/SHARE`), kein offener
  Werkzeug-Agent und keine IDE.
- Chat und JOSHI bleiben getrennte Produkte mit einer expliziten Brücke. Ein
  laufender JOSHI-Job darf den normalen Chat nicht blockieren.
- HTML und Laufzeit-State sind unterschiedliche Artefakte. Export, Versionen
  und Freigaben müssen beides nachvollziehbar behandeln.

## A. Repository-Befund

### Bestand und Laufzeit

Das Projekt ist eine FastAPI-Anwendung mit statischem Vanilla-JavaScript.
Server und Routen liegen zurzeit überwiegend in `app/main.py`; es gibt noch
keine Router- oder Service-Schicht für Funktionsbereiche. Die sichtbare App
besteht aus `static/index.html`, `static/app.js`, `static/coding.js` und
`static/styles.css`. Daten liegen standardmäßig außerhalb des Repositories in
`~/Library/Application Support/MiniLLM/data` (auf macOS); der Pfad ist per
`MINI_LLM_DATA_DIR` konfigurierbar.

Der Arbeitsordner ist keine Git-Working-Tree-Kopie (kein `.git` am
Repository-Root). Deshalb können beim Audit keine Git-Diff-/Branch-Informationen
als Migrationssicherung verwendet werden; die bestehenden Tests sind die
relevante Rückfallabsicherung.

### Bisheriger Harness: Frontend und Navigation

Der sichtbare Harness ist der **Coding-Arbeitsmodus**:

| Teil | Fundstelle | Tatsächliche Aufgabe |
| --- | --- | --- |
| Einstieg / Navigation | `static/index.html` (`#coding-open`, Zeilen 121–125) | Header-Button „Code“ öffnet die separate Vollansicht. |
| Arbeitsfläche | `static/index.html` (`#coding-view`, Zeilen 537–726) | Projektordner, Dateibaum, Editor/Dateivorschau, Auftrag, Aktivität, Diffs, Tests, Modell- und Budget-Steuerung. |
| Browser-Logik | `static/coding.js` | Lokaler Sitzungszeiger, Ordnerwahl, Dateien, multipart-Upload, Cmd/Strg+V, Drag & Drop, NDJSON-Stream, Wiederverbinden, Stop, Diff-Aktionen und Modellverwaltung. |
| Styling | `static/styles.css` | Enthält die Coding-Ansichts-, Pane-, Mobil- und Dialog-Stile. |
| Zurück zum Chat | `static/coding.js`, `schliesseAnsicht()` | Blendet nur die Coding-Vollansicht aus; der Chat-DOM bleibt erhalten und Coding-Jobs laufen weiter. |

Der Harness ist damit schon als eigene Arbeitsfläche integriert, aber semantisch
eine IDE für einen beliebigen lokalen Projektordner. Auffällige, für JOSHI nicht
passende Elemente sind Dateibaum, manueller Editor, Git-Anzeige, Diff-Apply,
Ordner-Browser und konfigurierbare 40–400 bzw. unbegrenzte Agentenschritte.

### Bisheriger Harness: Backend, Prompts und Modellaufrufe

`app/main.py` enthält die `/api/coding/*`-Endpunkte. Sie öffnen einen
lokalen Ordner, lesen/schreiben Projektdateien, berechnen Diffs, führen Python-
und erkannte Projektprüfungen aus und starten den Agenten. Die Sessions werden
in `coding_sessions` persistiert; ergänzende Artefakte (`plan.md`, Journal,
Checkpoint, Anhänge, Änderungen, Bericht) liegen unter `DATA_DIR/coding/<id>`.

`app/coding.py` ist die fachliche Agentenimplementierung. Sie enthält:

- Projektpfad- und Traversal-Schutz, Dateiindex, Arbeitsbereich/Diffs und
  atomare Dateischreibvorgänge;
- ein JSON-Werkzeugprotokoll mit Lese-, Schreib-, Rename-, Test- und
  Shell-nahen Projektaktionen;
- `erstelle_plan`, den mehrschrittigen Loop `fuehre_agent_aus` und
  `pruefe_abschluss`;
- den Prompt für genau einen Werkzeugschritt sowie Plan- und
  Abschlusskontrollprompts;
- Schleifen-/Budget-/Stillstandsschutz und Wiederaufnahme über `Anker`.

Die Prompttexte liegen nicht in separaten Dateien, sondern direkt in
`app/coding.py` (insbesondere bei den Schemata und Funktionen um
`erstelle_plan`, `pruefe_abschluss` und `fuehre_agent_aus`). Der Run-Endpunkt
in `app/main.py` baut eine lokale `strukturiert(...)`-Funktion und übergibt sie
an den Agenten. Diese ruft `ollama_structured_complete(...)` auf.

Die zentrale Modellanbindung selbst liegt heute ebenfalls in `app/main.py`:

- `OLLAMA_URL` ist die einzige konfigurierbare Ollama-Adresse.
- `ollama_chat_post`, `ollama_complete` und
  `ollama_structured_complete` vereinheitlichen Request, Retry,
  Kontextoptionen, Thinking-Kontrolle, Fehlermeldungen und Tokenzählung.
- Der normale Chat streamt direkt über dieselbe Schicht gegen
  `/api/chat`; der Coding-Harness verwendet strukturierte, nicht-streamende
  Modellaufrufe über dieselbe Schicht.

Das ist eine geeignete Basis, aber technisch noch keine eigenständige
`ModelGateway`-Abstraktion. Ein neues JOSHI-Modul darf `main.py` daher nicht
importieren (Zyklusgefahr), sondern muss diese Schicht zuerst klein und
verhaltensgleich herauslösen oder über eine injizierte Gateway-Schnittstelle
erhalten.

### Background-Jobs, Abbruch und Streaming

Es gibt drei voneinander getrennte In-Memory-Manager in `app/main.py`:

| System | Persistenz / Reconnect | Abbruch |
| --- | --- | --- |
| `ChatJobManager` | Puffert NDJSON-Ereignisse, persistiert das Endergebnis in den Chat und liefert Snapshots über `/api/chat/jobs/{request_id}`. | `StopState` und `/api/stop/{request_id}`. |
| `CodingJobManager` | Puffert Coding-Events pro Session, Reconnect über `GET /api/coding/run/{session_id}`; Arbeitsstand zusätzlich in SQLite/Anker-Dateien. | Session-Flag `abbruch`, `/api/coding/stop/{session_id}`. |
| `OllamaPullManager` | Läuft entkoppelt weiter und wird per Polling beobachtet. | Kein Benutzer-Stop-Endpunkt. |

Browser-Verlust beendet weder Chat- noch Coding-Job. Nach einem Dienstneustart
sind aktive asyncio-Tasks jedoch nicht fortsetzbar; Chat und Coding stellen
jeweils einen gespeicherten Zwischen-/Fehlerstand wieder her. JOSHI kann dieses
Muster wiederverwenden, muss aber für jeden Lifecycle-Status einen persistenten
Job- und Produkt-Snapshot schreiben, nicht nur einen Bericht.

### Uploads, Anhänge und Kontext

Der normale Chat besitzt einen reifen Mehrdatei-Flow in `static/app.js`:
Dateiauswahl, Ordner-Drop, globales Drag & Drop, Clipboard-Bilder sowie lange
Clipboard-Texte als Datei. `static/coding.js` dupliziert einen kleineren,
arbeitsflächenspezifischen Flow inklusive Drop und Cmd/Strg+V.

Serverseitig prüft `read_upload` Größenlimits. `prepare_attachments` in
`app/main.py` extrahiert bzw. klassifiziert Bilder, PDF, DOCX, XLSX/XLS, Text,
ZIP und Medien; Medien werden separat mit Whisper transkribiert. Textkontext
wird mit `app/intelligence.py::cache_context` gehasht, gechunked und durch
`user_contexts` pro Benutzer autorisiert. Coding-Anhänge werden zusätzlich in
seinem Ankerordner gespeichert.

Für JOSHI sind Parser, Limits, Bildübertragung und Kontextberechtigung direkt
brauchbar. Nicht übernehmen sollte JOSHI die aktuelle Kopplung an reine
Chat-Nachrichten beziehungsweise Coding-Anker; es braucht Produkt-Anhang-
Referenzen mit nachvollziehbarem Besitzer und Version.

### HTML-Preview und bisherige Exportfunktion

Der normale Chat kann bereits HTML aus Modellantworten erkennen und anzeigen:

- `extractHtmlPreviewSource`, `guardedDocument` und `openHtmlPreview` in
  `static/app.js` erkennen vollständige HTML-Dokumente und setzen `iframe.srcdoc`.
- Das iframe hat `sandbox="allow-scripts"` und eine restriktive CSP:
  keine Netzwerkverbindung, keine Frames/Objekte, keine Form-Submission;
  Bilder/Medien nur `data:` oder `blob:`. Damit ist es eine gute Basis für die
  JOSHI-Runtime.
- Die Vorschau fängt JS-Fehler über eine Prelude ab und kann einen kleinen
  String-Storage per `postMessage` zurückreichen. Dieser Storage ist derzeit
  global (`mini-llm-preview-storage`), nicht produkt- oder versionsbezogen.
- Der PDF-Druck nutzt ein zweites `srcdoc`-iframe ohne Skripte und ruft den
  Browserdruck auf. Es gibt noch keine automatische, serverseitig überprüfbare
  HTML-Validierung, keinen Screenshot-Export und keinen Produkt-State-Export.

`app/exports.py` und `/api/export` erzeugen heute aus Chat-Markdown DOCX,
XLSX, PDF, PPTX und EML. Das ist als Dokument-/E-Mail-Export wiederverwendbar,
aber **nicht** als HTML-Produktexport: Es kennt keinen DOM-State, keine
Runtime-Screenshots und keine gerenderte Einzelseiten-App.

### Storage, normaler Chat und Skills

`app/database.py` besitzt Benutzer, Login-Sessions, Chat-Metadaten,
separate Chat-Payloads, Profile, `user_contexts` und `coding_sessions`.
SQLite ist WAL-aktiv und die Datenpfade haben restriktive Dateirechte.
`app/verlauf.py`, `app/kontext.py`, `app/intelligence.py` und
`app/task_skills.py` tragen Chat-Verlauf, Kontextplanung, Recherche/
Dokumentkontext und Skills. Der Chat-Endpunkt in `app/main.py` verbindet dies
alles; seine Nachrichten, Folder, Skills und Profil-/Persona-Logik dürfen von
JOSHI nicht umgedeutet oder mit neuen Pflichtfeldern belastet werden.

Ein „Chat → JOSHI“-/„JOSHI → Chat“-Übergang existiert noch nicht. Die einzige
gegenwärtige Navigation zwischen Chat und Harness ist der „Code“-Button. Der
normale Chat kann parallel weiterlaufen, weil Coding nur eine ein-/ausblendbare
Ansicht besitzt; das ist die gewünschte Entkopplungsrichtung.

### Vorhandene Regressionstests und Audit-Verifikation

Die Test-Suite deckt Chat-Speicher, Kontext, Upload-/Dokumentverarbeitung,
HTML-Preview, Exporte, Skills, Laufzeit sowie Coding-Agent/-Resume/-Handoff ab
(`tests/test_*.py`). Ein Ausführen war in der Audit-Shell nicht möglich:
`pytest` ist nicht im PATH und `python3 -m pytest` meldet fehlendes Modul
`pytest`. Vor Umsetzung muss die projektübliche virtuelle Umgebung aus
`start.sh` aktiviert bzw. die Testabhängigkeit installiert werden; diese
Beobachtung ist kein Produktfehler.

## B. KEEP / REMOVE / REFACTOR / ADD

### KEEP

- Die zentrale Ollama-Konfiguration, Modellliste, Modellwahl und die
  Retry-/Fehler-/Tokenlogik in `app/main.py`. JOSHI erhält sein Modell aus
  derselben Auswahl wie Chat, niemals aus einer eigenen Konstante.
- `ChatJobManager` als bewährtes Muster für gepufferte NDJSON-Ereignisse,
  Browser-Reconnect und Endzustands-Persistenz; `StopState` als Vorbild für
  cancelbare Modellläufe.
- Authentifizierung, Benutzerisolation, SQLite-/`DATA_DIR`-Grundlagen und
  `user_contexts`-Autorisierung aus `app/database.py`.
- `read_upload`, `prepare_attachments`, Datei-/ZIP-Grenzen, Bildverarbeitung,
  OCR-/Dokumentpfade soweit vorhanden und Transkription.
- Die isolierte HTML-Preview samt CSP/Sandbox, Fehler-Overlay und
  `postMessage`-Kanal aus `static/app.js` als Ausgangspunkt für JOSHI Runtime.
- Chat-UI, Chat-Nachrichtenmodell, Skills, Websuche, Persona, Profile und
  Export-Renderer. Sie bleiben funktional unverändert.
- Dokument-/Mail-Builder in `app/exports.py` für sinnvolle Ableitungen aus
  einem JOSHI-Produkt (z. B. Begleitmail, später DOCX), nicht für den primären
  HTML-Export.

### REMOVE (erst nach vollständiger JOSHI-Migration)

Kein Entfernen in Phase 1. Sobald JOSHI V1 produktiv ist, keine Nutzer oder
persistierten Coding-Sessions mehr darauf verweisen und die Regressionstests
ersetzt sind, können folgende Harness-spezifische Teile entfallen:

- die sichtbare `#coding-view`-IDE inklusive Header-Button „Code“,
  Ordnerpicker, Dateibaum, Editor, Git- und Diff-/Apply-/Undo-Oberfläche;
- `static/coding.js` und die nur dafür bestimmten CSS-Regeln;
- `/api/coding/*`, `CodingJob*`, `CODING_LAEUFT`, `coding_sessions` und
  `DATA_DIR/coding/*`, **erst nach expliziter Datenmigrations-/Archivpolitik**;
- `app/coding.py` mit seinem freien Mehrschritt-Werkzeugagenten, lokalen
  Projekt-Schreibrechten, Testkommando-Erkennung und Ankerjournal.

Das Entfernen darf nicht als „Code aufräumen“ vorgezogen werden: Der normale
Chat nutzt die zentrale Modell-, Upload-, Export- und Preview-Infrastruktur,
nicht aber den Coding-Agenten. Der Coding-Harness selbst bleibt bis zum Cutover
kompatibel, damit keine aktive Sitzung verloren geht.

### REFACTOR

| Bestand | JOSHI-sichere Anpassung |
| --- | --- |
| Modellfunktionen in `app/main.py` | In ein kleines `app/model_gateway.py` verschieben oder als Gateway injizieren. Signaturen, `OLLAMA_URL`, Options/Retry und Fehlermeldungen zunächst unverändert halten. `main.py`, Chat, Coding und JOSHI verwenden danach dieselbe Instanz. |
| Job-Manager in `app/main.py` | Gemeinsame Event-/Abo-Primitiven extrahieren oder `JoshiJobManager` bewusst nach gleichem Muster bauen. Keine generische Großabstraktion vor dem ersten JOSHI-Job. |
| `prepare_attachments` | Parser behalten, Rückgabe um eine persistierbare `AttachmentRef`-Schicht ergänzen. Raw-Dateien, abgeleiteter Text, Bildreferenz, Hash und Eigentümer/Produktbezug müssen getrennt verwaltet werden. |
| Chat-Preview in `static/app.js` | In ein wiederverwendbares `joshiRuntime`-Modul auslagern. Storage-Key sowie `postMessage`-Protokoll müssen `productId` und `versionId` tragen; das bestehende Chat-Preview-Verhalten bleibt als Adapter bestehen. |
| `app/exports.py` | Chat-Export unverändert lassen. JOSHI-spezifische Export-Adapter hinzufügen (HTML+State, PNG/JPG, PDF); keinen HTML-State durch Markdown-Parser pressen. |
| `app/database.py` | Neue Tabellen und gezielte Query-Funktionen ergänzen; weder Chat-JSON noch `coding_sessions` als JOSHI-Speicher missbrauchen. |
| `static/index.html` / `styles.css` | Navigation um eine zweite Arbeitsfläche erweitern. Chat-Markup und IDs nicht umbenennen, da `app.js` und UI-Tests daran hängen. |

### ADD

- Eine eigene JOSHI-Arbeitsfläche mit Prompt, Anhängen, laufender Preview,
  Jobstatus, Versionen sowie Export-/Share-Aktionen.
- Persistente Produkte, Versionen, Jobs, Anhangreferenzen und Share-Tokens.
- Einen begrenzten Builder-Prompt für vollständiges Single-File-HTML sowie
  einen strikt technischen Validator. Nur Validator-Ergebnisse dürfen
  `READY` setzen.
- Einen höchstens kleinen, explizit budgetierten Repair-Pfad (z. B. maximal
  ein erster Rebuild plus ein Repair pro Nutzeraktion). Keine freie
  150-Schritte-Schleife.
- Produktbezogenen Runtime-State und eine Exportstrategie, die HTML und
  aktuellen State zuverlässig kombiniert.
- Bidirektionale `ChatJoshiBridge`-Aktionen mit unveränderlichem Snapshot:
  „Mit JOSHI umsetzen“ und „Im Chat besprechen“.

## C. Zielarchitektur

### Modulstruktur passend zum heutigen Projekt

Als neuer, gekapselter Bereich wird ein Paket eingeführt. FastAPI kann den
Router einbinden, ohne die bestehenden Chat-Routen zu verschieben:

```text
app/
  model_gateway.py              # aus main.py herausgelöste zentrale LLM-Calls
  joshi/
    __init__.py
    api.py                      # APIRouter: /api/joshi/*; require_user vom Host
    models.py                   # Pydantic/Dataclasses, Zustände und Eventformen
    store.py                    # SQLite-Operationen für JOSHI-Tabellen
    jobs.py                     # JoshiJob, JoshiJobManager, abonnierbare NDJSON-Events
    prompts.py                  # Build/Refine/Repair-Prompts und Antwortschema
    builder.py                  # JoshiBuilder: UNDERSTAND + BUILD über ModelGateway
    runtime.py                  # JoshiRuntime: HTML-Normalisierung, Runtime-Vertrag/State
    validator.py                # JoshiValidator: syntaktisch + Browser-Lade-/Fehlernachweis
    refiner.py                  # JoshiRefiner: gezielte Änderung, dann erneute Validierung
    exporter.py                 # JoshiExporter: HTML+State, Screenshot, PDF, Ableitungen
    share.py                    # JoshiShare: unerratbare Tokens, Ablauf, Read-only-Auslieferung
    bridge.py                   # ChatJoshiBridge: Snapshots/Referenzen zwischen Bereichen
static/
  joshi.js                      # Arbeitsfläche, Runtime-Client, Versionen, Events
  joshi.css                     # isolierte JOSHI-Stile (oder klar benannter styles.css-Abschnitt)
```

`app/main.py` bleibt zunächst App-Assembler: Lifespan, zentrale Gateway-
Initialisierung und `app.include_router(joshi_router)`. Der JOSHI-API-Layer
darf ausschließlich `ModelGateway` verwenden. Dadurch bleibt `OLLAMA_URL`
einziger Modellzugang und die Auswahl des UI-Modells wird als Requestwert
durchgereicht und serverseitig geprüft.

### Fachobjekte und Statusmodell

| Objekt | Verantwortung |
| --- | --- |
| `JoshiProduct` | Benutzerzugehöriges Produkt: Titel, Intent, aktive Version, Status, angeheftete Kontext-/Anhangreferenzen und optionaler Ursprungschat. |
| `JoshiProductVersion` | Unveränderlicher Stand: vollständiges HTML, normalisierter State-Snapshot, Änderungsanweisung, Validatorbericht, Parent-Version, Modell-/Prompt-Metadaten und Zeitstempel. |
| `JoshiJob` | Ein cancelbarer Lifecycle-Run pro Produkt, mit Status, Eventpuffer, Tokenverbrauch, Fehler und Verweis auf Zielversion. |
| `JoshiBuilder` | Erzeugt aus Intent/Anhängen ein vollständiges HTML-Dokument; gibt kein Produktversprechen ab. |
| `JoshiRuntime` | Liefert die isolierte iframe-Runtime, verarbeitet produktbezogene State-/Fehler-/Ready-Nachrichten und serialisiert State nach festem Vertrag. |
| `JoshiValidator` | Prüft HTML-Struktur und Browser-Realität (load, Runtime-Fehler, expliziter Handshake, zeitgebundene Stabilität). Nur es vergibt `READY`/`INVALID`. |
| `JoshiRefiner` | Erzeugt aus Nutzeränderung + vorherigem HTML + gespeichertem State eine neue Version und triggert erneut Validate/optional Repair. |
| `JoshiExporter` | Exportiert den validierten Versionsstand inklusive State. PNG/JPG/PDF benötigen eine deterministische Render-Engine, nicht den manuellen Browserdruck. |
| `JoshiShare` | Stellt eine abgesicherte, begrenzte read-only Produkt-/Versionsansicht über Token bereit; keine authentifizierte App-Sitzung in eingebettetem HTML. |
| `ChatJoshiBridge` | Erstellt immutable Übergabesnapshots. Chat-Nachricht → neuer `JoshiProduct`; Produktversion → referenzierbarer Chat-Kontext, niemals stilles Mergen beider Historien. |

Empfohlene Zustände: Job `queued | understanding | building | validating |
repairing | ready | failed | cancelled`; Produkt `draft | building | ready |
needs_attention | archived`. `ready` wird ausschließlich nach einem
gespeicherten positiven Validatorbericht gesetzt. Der Builder darf höchstens
`built` melden.

### Persistenzmodell

Neue SQLite-Tabellen (mit `user_id`-Foreign-Key und `(user_id, updated_at)`-
Indizes) statt eines großen JSON-Felds:

```text
joshi_products(id, user_id, title, intent, status, active_version_id,
               source_chat_id, created_at, updated_at)
joshi_product_versions(id, product_id, parent_version_id, html, state_json,
               change_request, model, build_metadata_json,
               validation_json, created_at)
joshi_jobs(id, product_id, user_id, status, phase, model, error,
           usage_json, target_version_id, created_at, updated_at, finished_at)
joshi_attachments(id, product_id, version_id, context_id, storage_path,
                  filename, content_type, sha256, metadata_json, created_at)
joshi_shares(id, product_id, version_id, token_hash, permission, expires_at,
             revoked_at, created_at)
```

`state_json` bleibt begrenzt und nur JSON-kompatibel. Der Runtime-Vertrag muss
eine klare Größe und erlaubte Typen vorgeben. Rohdateien gehören in einen
benutzer-/produktisolierten Unterordner von `DATA_DIR`, mit Restriktionen wie
bei Uploads; die Datenbank speichert Referenzen und Hashes. Share-Tokens werden
nur gehasht gespeichert und nie aus einer Produkt-ID ableitbar erzeugt.

### Lifecycle und Validierungsgrenze

```text
Intent + Anhänge
  → JoshiBuilder (zentraler ModelGateway)
  → neue immutable HTML-Version
  → JoshiRuntime lädt Sandbox
  → JoshiValidator: Struktur + Load + Fehler/Handshake + Stabilität
      → READY: Version aktivieren
      → Fehler: ein gezielter JoshiRefiner/Repair mit Validatorbefund
          → erneut validieren
          → needs_attention (nicht „funktioniert“)
```

V1-Validator: (1) vollständiges `<!doctype html>`/`<html>` und Größengrenze,
(2) CSP/Sandbox-kompatibles HTML, (3) iframe-`load`, (4) im Prelude erfasste
`error`/`unhandledrejection`, (5) dokumentierter `joshi-runtime-ready`-
Handshake und ein kurzer Stabilitätszeitraum. Dies ist ein technischer
Ladenachweis, keine fachliche Behauptung über jede Nutzeranforderung. Später
sollte ein echter Browser-Runner (z. B. isolierter Playwright-Prozess) genau
diesen Vertrag automatisieren; er ist im aktuellen `requirements.txt` nicht
vorhanden und darf nicht stillschweigend als Voraussetzung angenommen werden.

## D. Betroffene Dateien und Module

| Datei/Modul | Phase-1-Befund | Geplante spätere Änderung |
| --- | --- | --- |
| `app/main.py` | Monolithische App, Chat/Modelle/Jobs/Coding/API | Gateway herauslösen, JOSHI-Router/Lifespan ergänzen; Chat-Verhalten unverändert lassen. |
| `app/coding.py` | Alter mehrschrittiger Dateisystem-Agent samt Prompts | Nicht für JOSHI wiederverwenden; erst nach Cutover entfernen/archivieren. |
| `app/database.py` | SQLite-Schema und Coding-Sessions | JOSHI-Tabellen + Migration + gezielte Store-Funktionen. |
| `app/intelligence.py` | Kontextcache, Medien, Recherche | Kontext-/Attachment-Referenzen wiederverwenden. |
| `app/exports.py` | Chat-Markdown-/Dokumentexport | Ergänzen nur über JOSHI-Exporter-Adapter. |
| `static/index.html` | Chat, Vorschau und Coding-Vollansicht | Navigation und JOSHI-Arbeitsfläche additiv; Coding erst später entfernen. |
| `static/app.js` | Chat, Upload, Preview, Export, Background-Sync | Preview-/Upload-Hilfen extrahieren oder als stabile Adapter verwenden. |
| `static/coding.js` | Alter Harness | Während Migration unangetastet; danach entfernen. |
| `static/styles.css` | Gemeinsame Chat-/Coding-Stile | JOSHI klar separiert ergänzen; keine globalen Selektor-Kollisionen. |
| `tests/test_*.py` | Bestehende Regressionen | Vor jeder Phase laufen lassen; JOSHI-Tests additiv anlegen. |
| `app/joshi/*`, `static/joshi.*` | Noch nicht vorhanden | Neue, isolierte JOSHI-Implementierung gemäß Zielstruktur. |

## E. Implementierungsphasen

1. **Sicherungsbasis und Extraktionsvorbereitung**
   - Projektvenv/Testwerkzeug herstellen und vorhandene Suite als Baseline
     ausführen.
   - Charakterisierungstests für Chat-Stream, Cancel, Uploads, HTML-Preview
     und Exporte ergänzen, sofern Lücken sichtbar sind.
   - `ModelGateway` verhaltensgleich aus `main.py` extrahieren und Chat/Coding
     umstellen. Keine UI- oder Promptänderung.

2. **Datenmodell und begrenzter Job-Unterbau**
   - Tabellen/Migrationen und `app/joshi/store.py` bauen.
   - `JoshiJobManager` mit NDJSON, User-Ownership, Cancel, Reconnect und
     persistierten Snapshots implementieren.
   - Tests: Ownership, Restart-Snapshot, Cancel, paralleler Chat- und
     JOSHI-Job.

3. **JOSHI V1 Build + Runtime + technisches Gate**
   - `JoshiBuilder`, Prompt-Schema und komplette Single-File-HTML-Ausgabe.
   - Produktbezogene Sandbox-Runtime aus dem vorhandenen Preview-Code ableiten.
   - `JoshiValidator` und ein begrenzter Repair-Versuch; sichtbare Statuskette
     statt Fertigmeldung durch das Modell.
   - Erst danach eine additive JOSHI-Arbeitsfläche mit Text/Bildern/Dateien,
     Drop, Paste, Preview und Hintergrundfortschritt aktivieren.

4. **Versionierung und sprachliches Verfeinern**
   - Immutable Versionen, aktive Version, Rücksprung/Undo und State-Snapshot.
   - `JoshiRefiner` für „ändere …“, immer Build → Validate.
   - Tests für State-Erhalt, invalides HTML, JS-Fehler, Repair-Limit und
     Versionswechsel.

5. **Export und sichere Freigabe**
   - Download eines HTML-Bundles mit aktuellem State; je nach Runtime-Vertrag
     als HTML mit eingebettetem State-Bootstrap.
   - Deterministischer Full-Page PNG/JPG/PDF-Renderer und anschließende
     Artefaktprüfung; DOCX/EML nur dort, wo eine Produktbeschreibung oder
     Begleitkommunikation sinnvoll ist.
   - `JoshiShare` mit Ablauf, Widerruf, read-only Sandbox und Zugriffs-/Rate-
     Regeln.

6. **Chat-Brücke und Cutover**
   - „Mit JOSHI umsetzen“ erzeugt aus einer explizit gewählten
     Chat-Nachricht/einem Kontext-Snapshot ein Produkt.
   - „Im Chat besprechen“ übergibt eine gewählte Produktversion samt
     Validatorbericht als klar gekennzeichneten Kontext.
   - Erst nach produktiver Parität, Migration/Archivierung alter Sitzungen,
     Telemetrie/Fehlerkontrolle und bestandenem Regressionspaket den sichtbaren
     Code-Harness entfernen.

## F. Risiken und mögliche Regressionen

| Risiko | Schutzmaßnahme |
| --- | --- |
| Direkte oder abweichende Ollama-Integration | Vor dem JOSHI-Builder Gateway extrahieren; Architekturtest, dass kein `app/joshi/*` selbst `/api/chat` oder `OLLAMA_URL` anspricht. |
| Chat wird durch neue Navigation/DOM-IDs beschädigt | Additive IDs/Container, Charakterisierungstests für `static/app.js`, keine Umbenennung des Chat-Markups. |
| Hintergrundjob verliert Endstand bei Browserverlust/Restart | Job-Snapshot und Produktversion beim Phasenwechsel persistieren; Reconnect-Tests. |
| Validator behauptet zu viel | `READY` ausschließlich als technischer Runtime-Nachweis formulieren; fachliche Abnahme nicht simulieren. |
| iframe wird zu offen oder Funktionsapps werden durch CSP kaputt | Bestehende strenge Sandbox als Startpunkt, explizite Capability-Liste und Sicherheits-/Kompatibilitätstests pro Ausnahme. Keine `allow-same-origin`-Erweiterung für die interaktive Runtime. |
| State geht beim Refine/Export verloren | Versioniertes `state_json`, Message-Schema, Größenlimits und Test für Export → Reload → gleicher Zustand. |
| Globaler Preview-Storage mischt Produkte | Produkt-/versionsgebundene Storage-Namespace und serverseitige Ownership-Prüfung. |
| Upload-Daten leaken zwischen Chat, Coding und JOSHI | `user_contexts` weiter erzwingen, separate Produkt-Anhangreferenzen, keine bloßen Client-Dateinamen als Autorisierung. |
| Screenshot/PDF unterscheidet sich von der sichtbaren App | Gleichen HTML+State-Bootstrap in der isolierten Render-Engine laden; Renderer-Output gegen Version/Hash registrieren. |
| Zu frühes Löschen des Coding-Harness zerstört Sitzungen | Cutover-Gate, Archiv-/Migrationsplan und Entfernen erst nach erfolgreichem JOSHI-Rollout. |
| Doppelter Upload-/Preview-Code wächst weiter | Erst nach stabilem JOSHI V1 gezielt gemeinsame, getestete Hilfen extrahieren; nicht in der ersten UI-Phase zugleich umschreiben. |

## Phase-1-Abschluss

In dieser Phase wurden keine produktiven Funktionen, Datenbanktabellen,
Prompts, API-Routen oder UI-Elemente verändert. Nächster sinnvoller Schritt ist
Phase 2.1: Testlaufumgebung herstellen und die zentrale Modellschicht
verhaltensgleich in ein Gateway extrahieren. Das schafft die verbindliche
Wiederverwendung, bevor irgendein JOSHI-Builder geschrieben wird.

## Astra Review

Am 19.09.2026 wurde der implementierte JOSHI-V1-Stand gezielt gehärtet (kein
Neuaufbau und keine UI-Migration):

- **Geprüft:** zentrale Modellschicht und Streaming, Job-/Cancel-/Restart-Pfad,
  SQLite-Versionen und Zustand, Upload-/Attachment-Ownership, CSP/iframe und
  Laufzeit-Hülle, WebKit-Navigation und Exporte, Chat-Brücke sowie die sechs
  echten WebKit-Szenarien.
- **Behoben:** statische Renderer-Ersatzprüfung kann keine `ready`-Version mehr
  erzeugen; Job und Produkt melden dafür konsistent `needs_attention`.
  Abbruch/Neustart bewahrt den tatsächlichen Status der letzten Version.
  WebKit erlaubt vor `didFinish` nur noch die künstliche Initial-Herkunft;
  Compiler-/Renderer-Prozesse werden bei Timeout/Cancel sauber beendet und
  temporäre Binärdateien entfernt. `needs_attention` ist ein terminaler
  Jobstatus.
- **Bewusst offen:** Portable, exportierte HTML-Dateien laufen außerhalb des
  iframe-Sandkastens; externe Navigation wird dort nicht technisch ersetzt.
  Das bleibt ein klar dokumentiertes Export-Risiko und ist kein stilles
  Sicherheitsversprechen.
- **Verifikation:** Baseline vor dem Review: 286 Tests, vollständig grün,
  inklusive sechs echter WebKit-Tests. Nach den Regressionstests erneut die
  komplette Suite ausführen; auf Rechnern ohne `swiftc` werden die sechs
  Renderer-Tests erwartungsgemäß übersprungen.

## Post-Astra Verification

Nachprüfung am 19.09.2026 nach dem Hardening von `pruefer.py`, `pipeline.py`,
`jobs.py`, `speicher.py`, `renderer/__init__.py`, `joshi_render.swift` und
`tests/test_joshi.py`. Keine neuen Funktionen, keine Umstrukturierung.

**Renderer Build.** Über den vorgesehenen Projektweg `app.joshi.renderer.programm()`:
`swiftc` übersetzt `app/joshi/renderer/joshi_render.swift` und legt das Programm
nach Quelltext-Hash in `~/Library/Caches/MiniLLM/` ab. Neuer Hash
`1f6ac945c2c1` (2 s); der Build des Vorgängerstands wurde dabei automatisch
entfernt. Kein zweiter Renderer, keine globale Installation. `selbsttest()`
meldet „JOSHI-Renderer bereit“. Der 24/7-Dienst wurde eingespielt und nutzt
denselben Stand: gleicher Quelltext-Hash im Dienstordner, genau dieses Programm
im Cache, Startprotokoll „JOSHI-Renderer bereit (1.3 s)“.

**WebKit Tests.** Die sechs echten Renderer-Tests liefen tatsächlich (keine
Übersprungenen, 8,0 s): funktionierender Rechner, Skriptfehler mit Zeilennummer,
„NaN“ nach Eingabe, Hervorhebung als Reaktion, Download-Knopf bricht die
Bedienprobe nicht ab, Gesamtbild über die Viewport-Höhe hinaus.

**Gesamttests.** `unittest discover`: 290 Tests, alle grün, 0 übersprungen.

**Smoke Test.** Echtes Cloud-Modell auf einer isolierten Instanz:
Trinkgeld-Rechner in 12,7 s gebaut; Phasenkette verstehen → erstellen →
verbinden → prüfen → teilbar; `ready` erst nach der Browserprüfung
(`browser=true`, 4 Felder gefüllt, 2 Knöpfe geklickt). Zustand gespeichert,
PNG 2560×1800 (2 s) und A4-PDF mit echtem Text (2,1 s) gerendert; die
Anwendung rechnet korrekt (120 € bei 15 % → 18,00 € / 138,00 € / 69,00 € pro Person).

**Astras Fixes einzeln geprüft.**

| Punkt | Ergebnis |
| --- | --- |
| Ohne Renderer kein READY | `JOSHI_RENDERER=aus`: Produkt- und Auftragsstatus `needs_attention`, `ok=false`, `browser=false`; Bildexport 503 mit klarer Meldung, HTML-Export funktioniert weiter |
| `needs_attention` konsistent | Auftrag endet ebenfalls auf `needs_attention` (in `ENDSTATUS`), Endzeit gesetzt; nach Neustart bleibt eine ungeprüfte aktive Version `needs_attention` |
| Aktive Version bestimmt den Status | `status_fuer_version()` wird von Abbruch, Fehlschlag und Neustart-Aufräumen genutzt |
| Externe Navigation blockiert | Klick auf einen fremden Link und `window.open` werden abgelehnt und protokolliert, die Prüfseite lebt weiter |
| Interne Hash-Anker | Anker funktionieren: `location.hash = "#zwei"`, Seite scrollt (y = 394), Dokument bleibt dasselbe |
| Prozessende bei Cancel/Timeout | Endlosschleife mit Zeitüberschreitung (5,4 s) und Abbruch mitten im Lauf: danach kein `joshi-render`-Prozess mehr |
| Temporäre Dateien | Nach Zeitüberschreitung und Abbruch keine `joshi-*`-Ordner in TMPDIR; abgebrochene Übersetzungen räumen ihre `.tmp`-Datei ab |

**Verbleibende Risiken.**

- *Portable HTML außerhalb des Sandkastens:* Die exportierte Datei trägt
  dieselbe restriktive CSP wie die Vorschau. Gemessen im Export: `fetch`, XHR,
  WebSocket, externe Bilder, externe Skripte, iframes und Formularversand
  werden vom Dokument selbst blockiert (CSP-Verstöße `connect-src`, `img-src`,
  `script-src-elem`, `frame-src`, `form-action`). **Nicht** eingeschränkt ist
  Navigation: `location`-Zuweisung, `window.open` und Linkklicks lösen keinen
  CSP-Verstoß aus — in der JOSHI-Vorschau verhindert das der iframe-Sandkasten,
  in einer weitergegebenen Datei nicht. Eine solche Datei könnte also den Tab zu
  einer fremden Adresse schicken und dabei ihren eingebetteten Zustand in der URL
  mitgeben. Meta-CSP kann das nicht ausdrücken (`sandbox` und `navigate-to`
  wirken nur als HTTP-Header bzw. sind entfallen), deshalb bewusst keine
  Änderung. Ebenso bleiben Browser-Berechtigungsdialoge (Kamera, Ort) möglich;
  sie erfordern eine Zustimmung des Empfängers.
- *Renderer-Abhängigkeit:* Ohne Xcode Command Line Tools entsteht kein `ready`
  und kein Bild-/PDF-Export. Das ist beabsichtigt und wird klar gemeldet.
- *Modellabhängige Qualität:* Der Prüfer belegt Laden, Fehlerfreiheit und
  Reaktion — keine fachliche Richtigkeit der Berechnungen.

## Acceptance Validation Hardening

Stand 20.09.2026. Anlass: zwei reale Fehler aus dem Torture-Test.

**Problem.**
- *Fehler A:* Eine Änderung erzeugte eine praktisch leere Anwendung. Sie lud
  technisch fehlerfrei und wurde deshalb sichtbar — die funktionierende
  Vorgängerversion war verdrängt.
- *Fehler B:* Eine Änderung war technisch lauffähig, setzte den Wunsch aber
  nicht um (keine Druckmaske, kein Absender, kein Empfänger, keine
  Word-/PDF-Ausgabe) und galt trotzdem als fertig.
- Gemeinsame Ursache: „bereit“ hing allein an der technischen Prüfung. Es gab
  weder ein Maß für „zeigt die Anwendung überhaupt etwas“ noch einen Abgleich
  mit der vorherigen Version noch eine Prüfung gegen den konkreten Auftrag.
  Zudem wurde eine neue Version sofort aktiv und erst danach beurteilt.

**Lösung** (in der bestehenden Architektur, kein zweites System):
- `pruefer.leerbefunde`: Aus der WebKit-Messung kommen jetzt sichtbare
  Elemente, interaktive Elemente und die Fläche des sichtbaren Inhalts. Leere
  oder komplett ausgeblendete Seiten sind ein Fehler.
- `pruefer.regressionsbefunde`: relativer Vergleich mit der Messung der zuletzt
  geprüften Version (Text, Bedienelemente, Elemente). Ein ausdrücklich
  gewünschter Rückbau hebt den Vergleich auf.
- `app/joshi/abnahme.py`: Abnahmevertrag aus dem Änderungswunsch (ein
  kompakter Aufruf über die zentrale Modellschicht, robustes Parsen, Rückfall
  ohne Modell), Beweisbericht aus der Messung, deterministische Prüfung und
  höchstens ein weiterer Modellaufruf für die offenen Kriterien. Das Modell
  sieht nie die HTML-Datei.
- `renderer/pruefung.js`: Die Bedienprobe hält jetzt fest, was jeder Klick
  erscheinen lässt (neue Felder, Beschriftungen, Knöpfe). Damit sind
  Anforderungen wie „beim Klick erscheint eine Maske“ wirklich prüfbar.
- `pipeline`: Abnahmebefunde blockieren wie technische Fehler und gehen in
  dieselbe, auf zwei Versuche begrenzte Reparatur — mit dem ursprünglichen
  Wunsch und den fehlgeschlagenen Kriterien.
- `speicher.version_festschreiben`: Versionseintrag und Aktivierung in einer
  Transaktion. Ein Kandidat wird nur nach bestandener Prüfung aktiv; sonst
  bleibt die alte Version samt Zustand aktiv, und der Kandidat bleibt als
  abgelehnte Version nachlesbar.

**Tests.** 316 Tests grün, 0 übersprungen (vorher 290). Neu: Leer- und
Regressionsregeln, Abnahmelogik (Beweise, Interaktionskriterien, strenge
Wertung, Vertragsrobustheit), Kandidat/Promotion (Zustand bleibt, Export nutzt
die aktive Version, zwei gescheiterte Reparaturen) und in echtem WebKit die
Kette leer → unvollständig → vollständig sowie eine per CSS versteckte Seite.

**Realer Retest** (isolierte Instanz, `glm-5.3-flash:cloud`,
KI-Schulungs-Angebotskonfigurator, exakter Originalwunsch):
- Erster Kandidat: praktisch leer → abgelehnt (Leerprüfung und Regression),
  Version 1 blieb aktiv.
- Zweiter Lauf: erster Kandidat wieder leer → Reparatur; die reparierte Fassung
  erfüllte alle vier Abnahmekriterien allein aus der Messung → erst dann
  Version 3 aktiv und bereit. Die Maske mit Absender, Empfänger,
  Angebotsvorlage sowie PDF- und Word-Ausgabe ist im Bild belegt.
- Im ersten Lauf blieb nach zwei Reparaturen alles unerfüllt: Version 1 blieb
  aktiv, die vier offenen Punkte wurden benannt.

**Bekannte Grenzen.**
- Die Abnahme prüft Sichtbarkeit und Bedienbarkeit, keine fachliche
  Richtigkeit: Dass ein PDF-Knopf existiert und reagiert, heißt nicht, dass das
  erzeugte Dokument inhaltlich korrekt ist.
- Stichwortbasierte Nachweise können bei ungewöhnlichen Synonymen einen
  erfüllten Wunsch als offen melden; dann greift die Reparatur, im
  schlechtesten Fall bleibt die alte Version aktiv (sichere Richtung).
- Antwortet die Modellschicht beim Abnahmeurteil gar nicht, gilt ein Kriterium
  ohne Spur in der Messung als nicht umgesetzt. Eine Änderung wird dann eher
  abgelehnt als fälschlich übernommen.
- Der Regressionsvergleich erlaubt gewollten Rückbau nur, wenn der
  Abnahmevertrag ihn erkennt (`rueckbau`).
- Kosten: pro Änderung ein zusätzlicher Vertragsaufruf und höchstens ein
  Abnahmeaufruf je Prüfrunde; deterministische Nachweise kommen ohne Modell aus
  (im Retest erfüllte die finale Fassung alle Kriterien ohne Modellurteil).

## Sandboxed Document Export

Stand 20.09.2026.

**Problem.** Eine laufende JOSHI-Anwendung konnte „Angebot drucken / als PDF
speichern“ anbieten, aber nicht ausführen: Im Sandkasten gibt es kein
`window.print()`, keinen Download und keinen Netzzugriff. Der Nutzer musste
erst die HTML-Datei exportieren, sie separat öffnen und dort erneut drucken.

**Lösung.** Eine kleine, erlaubnisbasierte Host-Bridge. Die Anwendung
beschreibt den Export, JOSHI führt ihn mit den vorhandenen Exportern aus:

- Laufzeit (`laufzeit.js`): `window.JOSHI.export({type, target, filename, title})`
  — mehr API gibt es nicht. Die Laufzeit sammelt den Ausschnitt (outerHTML des
  Ziels) und die Stile der Seite und schickt sie per `postMessage`.
- Oberfläche (`joshi.js`): prüft Absenderrahmen, Produkt, aktive Version und
  Typ, ruft den Server, löst den Browserdownload aus und antwortet der
  Anwendung (`{ok, filename}` bzw. `{ok:false, error}`).
- Server (`api.py`, `export.py`): prüft Besitz, aktive Version, Typ (`pdf`,
  `docx`, `png`, `jpg`), Größe (1 MB HTML, 400 KB CSS), höchstens zwei
  gleichzeitige Exporte je Produkt, sanitisierten Dateinamen; entfernt
  `<script>` und `on…`-Attribute aus dem Ausschnitt und rendert ihn mit
  derselben strengen Richtlinie. PDF über den vorhandenen WebKit-Renderer
  (A4, echter Text), DOCX über den vorhandenen Word-Export.
- Prompt: Regel 12 nennt dem Modell die API statt `window.print()` oder
  Blob-Tricks.
- Rückwärtskompatibel: `window.print()` wird im Sandkasten auf einen
  PDF-Export der ganzen Anwendung abgebildet; im exportierten HTML bleibt es
  der normale Browserdruck.

**Security.** Die Sandbox bleibt unverändert (`allow-scripts`, keine eigene
Herkunft, kein `allow-downloads`, `allow-popups`, `allow-forms`,
`allow-same-origin`), die CSP bleibt unverändert, Netzzugriff bleibt gesperrt.
Den Download löst nur die JOSHI-Oberfläche aus. Abgelehnt werden: unbekannte
Nachrichtenarten, unbekannte Typen, fremde Produkte, nicht aktive Versionen,
leere oder zu große Ausschnitte, Pfadangaben im Dateinamen.

**Abnahme.** Ein Kriterium, das eine Datei verlangt, gilt nur als erfüllt,
wenn die Bedienprobe den Export wirklich ausgelöst hat und JOSHI daraus eine
gültige Datei erzeugt hat (PDF-Kopf, lesbares DOCX, Größe > 0). Die
Bedienprobe drückt dafür jetzt auch Knöpfe, die erst nach einem Klick
erscheinen (etwa in einer geöffneten Maske).

**Tests.** 335 Tests grün, 0 übersprungen (vorher 316). Neu: gültige PDF- und
DOCX-Anfrage, unbekannte Capability, fremdes Produkt, nicht aktive Version,
leerer und zu großer Ausschnitt, Dateinamen-Sanitizing, Skript-Entfernung,
Abnahme nur mit echter Datei, fehlgeschlagener Export als Nicht-Nachweis,
Apps ohne API, sowie in echtem WebKit: Bedienprobe erzeugt PDF und DOCX,
winzige API-Oberfläche, unbekanntes Ziel, exportierte Datei ohne Host,
Abbruch ohne Reste, `window.print()`-Rückfall und der normale Produktexport.

**Realer Test.** Angebotskonfigurator (Cloud-Modell, isolierte Instanz): Die
erzeugte Anwendung nutzt `window.JOSHI.export` (kein `window.print`, keine
Blob-Tricks). In der laufenden Vorschau meldete der Klick auf „Angebot drucken
/ als PDF speichern“ direkt „PDF wurde erstellt: angebot-ki-schulung.pdf“;
Server: `POST …/export/pdf 200`, danach `…/export/docx 200`. Die Dateien
enthalten Absender, Empfänger, Positionstabelle, Netto, MwSt. und
Gesamtbetrag (25.153,63 €); das PDF ist eine A4-Seite mit echtem Text, das
DOCX hat eine Tabelle mit sechs Zeilen.

**Bekannte Grenzen.**
- Exportiert wird, was im Ausschnitt sichtbar ist: Canvas-Diagramme erscheinen
  im PDF/Bild, im DOCX dagegen nicht (dort landen Text und Tabellen).
- Der Ausschnitt wird ohne Skripte gerendert; Inhalte, die erst nach dem Laden
  per JavaScript entstehen würden, müssen zum Zeitpunkt des Klicks schon im
  DOM stehen (bei einer sichtbaren Vorschau ist das der Normalfall).
- Nur die aktive Version darf exportieren; ein Export aus einer älteren
  Version wird abgelehnt.
- Die exportierte, weitergegebene HTML-Datei hat keinen Host: `window.print()`
  druckt dort normal, ein Word-Export ist dort nicht möglich und meldet das.
- Bildexporte (`png`, `jpg`) sind erlaubt, aber vom Modell selten genutzt;
  E-Mail, Netzwerk, Dateisystem und Shell bleiben ausgeschlossen.
