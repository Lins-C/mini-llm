# JOSHI – Just On-demand Software from Human Intent

JOSHI macht aus einer Idee (Text, Bilder, Dateien, optional Chat-Kontext) eine
laufende, benutzbare, änderbare und teilbare Anwendung. Das Produkt ist die
Anwendung, nicht der Code. Format in V1: **eine eigenständige HTML-Datei**.

Chat und JOSHI sind zwei Arbeitswelten in derselben App: Im Chat wird
gedacht, gefragt und geschrieben, in JOSHI erstellt, benutzt, geändert und
geteilt. JOSHI ersetzt den früheren Code-Harness. Der liegt vollständig unter
`archiv/coding-harness/`, die Tabelle `coding_sessions` bleibt unangetastet.

## Aufbau

```text
app/joshi/
  api.py          HTTP /api/joshi/*; bekommt Anmeldung, Modellzugang, Upload- und
                  Dokumentlogik von main.py hereingereicht (Anbindung)
  modell.py       Schnittstelle Modellzugang (strukturiert, strom, faehigkeiten, fenster)
  pipeline.py     der feste Ablauf (Lauf) – Verstehen, Bauen, Ändern, Reparieren
  prompts.py      Anweisungen je Phase, Bauregeln für die HTML-Datei
  html_werk.py    HTML aus Modellantworten, Änderungsblöcke, Bilder, Laufzeit-Hülle,
                  statische Prüfung, Exportdokument
  laufzeit.js     Vorrede in jedem Produkt: Fehler fangen, Speicher, Zustand, alert
  export.py       HTML mit Zustand, PNG/JPG, PDF, DOCX, E-Mail, Abschnittsexport
  pruefer.py      Prüfbericht aus statischer Prüfung + Browsermessung,
                  Leerprüfung, Regressionsvergleich, Aktionsproben und Szenarien
  abnahme.py      Abnahmevertrag (mit Nachweisart), Beweisbericht, Abnahmeurteil
  aenderung.py    Änderungslinie: Retry/Ergänzung/Verwerfen, Root-Vertrag, Stufenplan
  grenzen.py      zentrale Grenzen, Wächter, „abgeschnitten ist nicht fertig“
  dateien.py      freigegebene Ordner: Asset-/Eingabeordner (lesen), Workspace (lesen+schreiben),
                  Pfadprüfung, interne Fähigkeiten inbound.* / workspace.*
  eingaben.py     welche Eingabedateien ein Auftrag braucht, ihre Rolle, Build-Snapshot
  projekt.py      Einzeldatei oder Workspace? Projektordner, JOSHI_PROJECT.md, README.md
  projektdateien.py  verlustfreie interne Zerlegung großer Apps, Dateiauswahl,
                     sichere Antwortanwendung und Auftrags-Snapshot
  renderer/       WebKit-Renderer (Swift) + Prüf-, Inhalts- und Szenarioskript
  jobs.py         Hintergrundaufträge mit Ereignispuffer (NDJSON), Abbruch
  speicher.py     SQLite-Tabellen joshi_* + Bilddateien unter DATA_DIR/joshi/<produkt>
  bruecke.py      Chat → JOSHI, JOSHI → Chat
static/joshi.js   Arbeitsfläche; static/modelle.js Modellverwaltung (von überall zu öffnen)
```

## Modellanbindung

JOSHI spricht nie selbst mit Ollama. `app/main.py` reicht einen
`MiniLLMModellzugang` herein. Der nutzt dieselbe zentrale Schicht wie der Chat:
`OLLAMA_URL`, Wiederholungen bei 429/5xx, Denkstrom-Grenzen, verständliche
Fehlertexte (Nutzungslimit, Anmeldung) und `ollama_chat_stream` für
streamende Antworten. Das Modell ist das im Chat gewählte. Lokale Modelle
bekommen `num_ctx = max(16384, Regler der Ollama-App)` (`JOSHI_NUM_CTX` überschreibt),
Cloud-Modelle rechnen mit `CLOUD_CONTEXT_TOKENS`. Ob ein Modell Bilder sieht,
fragt `faehigkeiten()` über `/api/show` ab. Ein anderer Anbieter oder ein
Routing nach Fähigkeiten tauscht nur diesen Zugang aus. Ein Architekturtest
stellt sicher, dass `app/joshi/` weder Ollama-Adressen noch Modellnamen enthält.

## Auftrag (Job) – Lebenslauf

`queued → understanding → building → validating → (repairing → validating)* → ready | failed | cancelled`

- Ein Auftrag läuft als asyncio-Task im Serverprozess (`jobs.verwaltung`).
  Der Browser hört nur zu (`GET /api/joshi/auftraege/{id}/ereignisse?ab=n`)
  und kann sich jederzeit neu verbinden. „← Zurück zum Chat“, ein Neuladen
  oder ein geschlossenes Fenster beenden nichts.
- Pro Produkt läuft höchstens ein Auftrag. Status und Fortschritt stehen bei
  jedem Phasenwechsel in `joshi_jobs`, die Ereignisse am Ende.
- Nach einem Dienstneustart setzt `nach_neustart_aufraeumen()` offene
  Aufträge ehrlich auf `failed`; die letzte fertige Version bleibt aktiv.
- Arten: `bauen`, `aendern`, `reparieren` (ein im Browser gemeldeter Fehler),
  `importieren` (fertiges HTML aus einer Chat-Antwort).

Ereignisse (NDJSON): `plan`, `status`, `schritt` (verstehen, erstellen,
verbinden, pruefen, teilbar mit offen/aktiv/fertig/fehler/reparatur),
`fortschritt`, `verstaendnis`, `hinweis`, `technik` (nur „Technische
Details“), `tokens`, `stufen` (der vollständige Stufenplan) und `stufe` (der
Zustand der aktuell laufenden Stufe), `fertig`, `fehler`. Bei einer gestuften
Änderung zeigt die Arbeitsfläche deshalb nicht nur einen globalen Schritt,
sondern etwa „Schritt 1 bestanden“ und gleichzeitig „Schritt 2 · wird
erstellt“.

## Pipeline

```text
VERSTEHEN  strukturiertes JSON: Titel, Zweck, Funktionen, Bedienelemente
BAUEN      Stream der ganzen HTML-Datei; nur direkte ganze Dateien dürfen höchstens
           zweimal fortgesetzt werden
VERBINDEN  deterministisch: viewport/charset/title, Bildverweise joshi:bild-N
PRÜFEN     statisch + WebKit (Desktop mit Bedienprobe, 390 px für das Layout)
REPARIEREN höchstens 2 Runden, gezielt mit den Befunden; die beste Fassung zählt
BEREIT     neue Version; Status ready oder needs_attention
```

Änderungen und Reparaturen: Kleine Dateien (< 7.000 Zeichen) schreibt das
Modell ganz neu, größere ändert es über `SUCHEN/ERSETZEN`-Blöcke. Blöcke, die
nicht passen, werden einmal gezielt nachgetragen (nur sie, auf dem teilweise
geänderten Stand). Fehlt danach noch etwas, wird bei einer normalen Änderung die
ganze Datei geschrieben, sofern sie ins Kontextfenster passt. Sonst sagt JOSHI
klar, dass das Fenster zu klein ist. Eine Antwort mit `length` oder einem
vergleichbaren Provider-Grund ist kein fertiger Patch. In einem gestuften
Schritt wird sie nicht fortgesetzt und niemals angewendet; bei einer direkten
ganzen Datei darf nur die vollständig zusammengesetzte HTML-Datei weiter zur
Browserprüfung. Abgeschnittene Antworten, übergroße Änderungen und
Patchkonflikte: siehe „Große Änderungen“.

Eine Reparatur darf nie verschlechtern: Jede Fassung wird nach
(Fehler, Lücken) bewertet, und weiter geht es immer von der besten.
Scheitert eine Änderung an einem funktionierenden Produkt, bleibt die
bisherige Version aktiv.

## Prüfer

„Bereit“ vergibt nur der Prüfer — und zwar erst, wenn Technik, Sichtbarkeit
und Abnahme zusammen bestehen. Befundarten:

- `abnahme`: Der Auftrag ist nachweislich nicht umgesetzt — blockiert und wird
  repariert (siehe „Abnahme“).
- `fehler`: blockiert und wird repariert. Dazu zählen: kein oder abgeschnittenes
  HTML, externe Skripte/CDNs, Skriptfehler beim Laden oder beim Klick (mit
  Knopfname und Zeile der Originaldatei), Hängen/Absturz, leere Seite, „NaN“,
  „undefined“ oder „[object Object]“ nach der Eingabe, keinerlei Reaktion auf
  Felder und Knöpfe.
- `luecke`: Ein laut Verständnis erwarteter Handlungsknopf („Zurücksetzen“)
  fehlt. Wird repariert, solange Versuche übrig sind, blockiert aber nicht.
- `warnung` / `info`: Anzeige in den Details, z. B. Überlauf bei 390 px,
  `console.error`, blockierte Navigation, Download-Knöpfe.

Die Bedienprobe (`renderer/pruefung.js`) füllt alle sichtbaren Felder mit
plausiblen Werten und klickt bis zu 30 Knöpfe, zerstörerische wie
„Zurücksetzen“ oder „Export“ zuletzt. Als Reaktion zählen Text,
Ausgabewerte, Canvas, SVG, Elementzahl und Klassen- bzw. ARIA-Zustände.

## Abnahme: drei Ebenen bis „bereit“

Technisch lauffähig heißt nicht erfüllt. Eine Kandidatenversion wird erst
aktiv, wenn alle drei Ebenen bestehen:

```text
1. TECHNIK        lädt, keine Skriptfehler, reagiert, kein „NaN“
2. SICHTBARKEIT   nicht leer, und gegenüber der aktiven Version nichts weggerissen
3. ABNAHME        der konkrete Auftrag ist in der Messung nachweisbar umgesetzt
        ⇣ nur alle drei zusammen
   READY + aktive Version
```

**Leerprüfung (`pruefer.leerbefunde`).** Aus der Browsermessung kommen
sichtbare Elemente, interaktive Elemente und die Fläche des sichtbaren
Inhalts. Eine Seite, die lädt, aber nichts zeigt (`<body></body>`, alles
`display:none`, weiße Fläche), ist ein Fehler — kein „bereit“.

**Regressionsvergleich (`pruefer.regressionsbefunde`).** Bei einer Änderung
liegt die Messung der zuletzt geprüften Version als Vergleich vor. Verglichen
wird relativ (Text, Bedienelemente, Elemente), damit kleine Anwendungen nicht
an festen Zahlen scheitern. Will der Nutzer ausdrücklich etwas entfernen
(`rueckbau` im Vertrag), greift nur noch die Leerprüfung.

**Abnahmevertrag (`app/joshi/abnahme.py`).** Vor einer Änderung entstehen aus
dem Wunsch 2–6 prüfbare Kriterien mit Stichworten und dem Vermerk, ob erst
eine Bedienung sie sichtbar macht — über die zentrale Modellschicht, ein
kompakter Aufruf. Beim Neubau entsteht der Vertrag ohne Zusatzaufruf aus dem
bereits vorhandenen Verständnis; dort sind die Kriterien Hinweise, keine
Sperre.

**Beweise statt HTML.** Geprüft wird gegen einen Beweisbericht aus der
WebKit-Messung: Überschriften, Knöpfe, Feldbeschriftungen, sichtbarer Text und
— wichtig für Anforderungen wie „beim Klick erscheint eine Maske“ — was jeder
Klick zusätzlich erscheinen ließ (neue Felder, neue Beschriftungen, neue
Knöpfe). Erst deterministisch (Stichworte in den Beweisen), und nur für die
dabei offenen Kriterien ein einziger kompakter Modellaufruf. Das Modell sieht
nie die HTML-Datei und darf nur bestätigen oder widerlegen, was gemessen
wurde. Ohne messbare Beweise urteilt die Abnahme gar nicht — dann entscheidet
die Leerprüfung.

**Kandidat und Promotion.** Eine neue Version entsteht immer als Kandidat.
Besteht sie, werden Versionseintrag und aktive Version in einer Transaktion
gesetzt (`speicher.version_festschreiben`). Besteht sie nicht, bleibt die
bisherige Version aktiv, ihr Zustand bleibt erhalten, und der Kandidat bleibt
als abgelehnte Version nachlesbar. Der Nutzer liest: „JOSHI konnte die
gewünschte Änderung noch nicht vollständig umsetzen. Deine letzte
funktionierende Version bleibt aktiv“ — darunter die offenen Punkte.

**Reparatur.** Abnahmelücken gehen wie technische Fehler in dieselbe, auf zwei
Versuche begrenzte Reparaturschleife; die Reparatur bekommt den ursprünglichen
Wunsch, die fehlgeschlagenen Kriterien und die Befunde. Es gilt weiter: Die
beste geprüfte Fassung zählt, eine Reparatur darf nie verschlechtern.

Export und Teilen verwenden immer die aktive Version — ein abgelehnter
Kandidat wird nie exportiert.

## Große Änderungen: Linie, Routing, Grenzen, Stufen, Beweise

Anlass war ein Tabellenkalkulations-Stresstest am 21.09.2026. Nach einem
gescheiterten Versuch schrieb der Nutzer nur „versuch es erneut“. Die Antwort
lief 587 s, endete mit `length` nach 217.048 Zeichen und enthielt 112 Blöcke,
von denen 4 nicht passten. Ein kleiner Nachtrag wurde auf das *Original*
angewendet, dabei gingen 108 Änderungen still verloren. Der Vertrag schrumpfte
auf „Anwendung öffnet sich“ und „Knöpfe anklickbar“, und „Speichern“ galt als
nicht umgesetzt, weil kein neues DOM erschien. Richtig war nur: Version 1 blieb
aktiv.

### Invarianten

1. **A retry never loses the original change intent.** Ein Änderungsauftrag
   (`joshi_changes`) hat einen Root-Wunsch und einen Root-Vertrag mit stabilen
   Kriterien-IDs. „versuch es erneut“, „nochmal“ oder „probier es nochmal“ ist
   ein weiterer Versuch derselben Linie. Das Modell bekommt den Root-Wunsch und
   die Befunde der bisherigen Versuche, der Vertrag wird nicht neu erfragt.
   Neuer Inhalt bei offenem Auftrag ist eine Ergänzung: neue Kriterien mit
   eigenen IDs, die alten Pflichtkriterien bleiben. „Verwirf die Änderung“ oder
   „stattdessen …“ schließt die Linie bewusst. Aufträge von vor der Linie
   (Altbestand) werden bei einer Wiederholungsbitte aus den gescheiterten
   Aufträgen nachgebildet. Wird der ursprüngliche Root-Wunsch oder der
   vollständige Root-Wunsch inklusive Ergänzungen erneut gesendet, ist das
   ebenfalls deterministisch ein Retry: verglichen werden nur
   Unicode-Normalisierung, Groß-/Kleinschreibung, Leerraum und Satzzeichen.
   Es gibt bewusst keine unscharfe Ähnlichkeitssuche; neue Wörter bleiben eine
   Ergänzung mit eigenen Kriterien.
2. **A truncated model response is never considered a completed candidate.**
   Endet eine Generierung mit `length`, `max_tokens` o. ä.
   (`grenzen.ist_abgeschnitten`), werden Änderungsblöcke nicht angewendet
   (TRUNCATED_PATCH). Eine direkte ganze Datei darf höchstens zweimal
   fortgesetzt werden und wird erst danach im Browser geprüft. Bleibt sie
   offen, entsteht kein Kandidat, auch keine Erstfassung. Für einen gestuften
   Schritt gilt strenger: `TRUNCATED_STAGE` wird *vor* HTML- oder
   Patch-Verarbeitung ausgelöst; weder zufällig vollständiges HTML noch ein
   scheinbar vollständiger Block darf aus einem als abgeschnitten gemeldeten
   Stream übernommen werden.
3. **Partial patch application is never silently treated as complete
   success.** Passen nicht alle Blöcke (PARTIAL_PATCH), gibt es genau einen
   gezielten Nachtrag. Er gilt nur den fehlenden Blöcken und bezieht sich auf
   den teilweise geänderten Stand. Danach wird geprüft, ob jede fehlende
   Änderung wirklich angekommen ist. Fehlt noch etwas, ist es ein PATCH_CONFLICT:
   bei einer normalen Änderung folgt die ganze Datei neu, bei einer übergroßen
   oder gestuften Änderung ein kontrollierter Abbruch.
4. **Complex changes start staged before a monster call.** Das Routing ist
   deterministisch und läuft vor dem ersten großen Modellaufruf. Es wählt den
   gestuften Modus, wenn ein früherer Versuch bereits gestuft war, abgeschnitten
   ist, an einer harten Grenze scheiterte oder einen Patchkonflikt hatte. Ohne
   Vorbefund entscheidet der Root-Vertrag: mindestens acht Pflichtkriterien,
   davon mindestens vier echte Zustands-/Mehrschritt-Abläufe; mindestens sechs
   Pflichtkriterien mit einer schweren Systemanforderung; mindestens zwei
   schwere Anforderungen aus verschiedenen Bereichen; oder eine Anwendung ab
   60.000 Zeichen mit grundlegender schwerer Änderung. Schwere Bereiche sind
   etwa Leistung, große Datenmengen, Virtualisierung, Mehrbenutzer-
   Synchronisation, Engine oder Daten-/Zustandsarchitektur. Reine Bedienung
   oder Gestaltung bleibt absichtlich schnell — auch acht Knöpfe oder
   UI-Kriterien sind kein Architekturumbau. Trifft eine direkte Einmal-Änderung
   dennoch auf einen Grenzfall, wechselt derselbe Auftrag anschließend in
   Schritte. Der Plan (2–8 Schritte, `aenderung.stufenplan_erzeugen`, Rückfall
   nach Regel) verteilt die Root-Kriterien. Jeder Schritt ist klein, wird
   geprüft (höchstens eine Reparatur) und als interner Checkpoint gesichert.
5. **Intermediate stages never replace the active accepted product.**
   Checkpoints liegen in `joshi_changes.checkpoint`, nicht in den Versionen.
   Scheitert ein Schritt, bleibt die aktive Version. Ein neuer Versuch setzt am
   letzten Checkpoint fort, sofern die aktive Version dieselbe ist.
6. **Final promotion always evaluates the complete root acceptance
   contract.** `stage_contract ⊂ root_contract`. Die Endabnahme läuft gegen
   `root_contract + Ergänzungen` und gegen die Messung der ursprünglich aktiven
   Version (Regression). Promotion geschieht genau einmal.
7. **Acceptance is evidence-based and action-specific.** Jedes Kriterium hat
   eine Nachweisart: `inhalt`, `bedienung` (mit Aktion), `gestaltung`, `ablauf`
   oder `nicht_pruefbar`. Belege:
   - je Klick typisierte Wirkungen: `text_changed`, `value_changed`,
     `local_storage_changed`, `element_shown/hidden`, `dom_added`,
     `route_changed`, `modal_opened`, `export_requested`,
     `download_triggered`, `state_changed`, `runtime_error` (Downloads werden
     nur gezählt, nie ausgeführt);
   - Aktionsproben: Speichern ändert den Speicher; Speichern → Ändern → Laden
     stellt den Stand wieder her; Neu setzt zurück; Rückgängig/Wiederholen;
   - Szenarien (Arrange → Act → Assert) als Daten, ausgeführt vom festen Code
     in `renderer/szenario.js`. `neu_laden` startet eine neue Seite mit dem
     gespeicherten Zustand, also ein echtes Neuladen. `dauer_hoechstens`
     speichert Messwerte;
   - Stil vorher/nachher für Gestaltungswünsche.
   Aktionsproben und Szenarien laufen nur, wenn der Vertrag sie verlangt.
8. **UNKNOWN / NOT_PROVEN is not PASS.** Je Kriterium PASS, FAIL oder
   NOT_PROVEN. Ein unbewiesenes Pflichtkriterium blockiert (`unbewiesen`,
   reparierbar). Was die Prüfumgebung grundsätzlich nicht kann (zweite
   Sitzung, echte Offline-/Online-Verbindung), ist `unbeweisbar`: Es blockiert,
   wird aber nicht sinnlos repariert. Das Modellurteil kommt zuletzt und nur für
   Offenes. Für „erfüllt“ muss es einen Beleg nennen (`klick:…`, `aktion:…`,
   `szenario:…`, `stil`, `export`, …), den es im Beweisbericht wirklich gibt
   und der zur Nachweisart passt. Sonst bleibt das Kriterium unbewiesen.
9. **The last accepted version always wins over an unverified candidate.**
   Abgelehnte Kandidaten stehen in der Versionsliste als „abgelehnt · nie
   freigegeben“. „Rückgängig“ überspringt sie. Aktivieren geht nur ausdrücklich
   (`?bewusst=1` nach Rückfrage) und dann mit Status `needs_attention`.
10. **The model creates; JOSHI decides whether the result is sufficiently
    proven.**

### Stufen: Laufzeit, Sichtbarkeit und Abnahme

Ein Stufenplan ist ein interner Arbeitsplan, keine Folge neuer Produkte. Die
Serverereignisse `stufen` und `stufe` enthalten Nummer, Gesamtzahl, Titel und
den aktuellen Zustand `planned`, `generating`, `connecting`, `validating`,
`repairing`, `passed`, `failed` oder `aborted`. Die Oberfläche aktualisiert
diese Zustände unabhängig vom groben Job-Status; nach einem bestandenen
Schritt bleibt er sichtbar als bestanden, während die nächste Stufe ihren
eigenen aktuellen Zustand zeigt.

Jeder Schritt prüft nur seinen Teilvertrag, speichert bei Erfolg einen
Checkpoint und trägt seine Usage in `diagnose.stufen[].usage` ein. Ein
Checkpoint ist nie aktiv. Die endgültige Promotion prüft weiterhin den
vollständigen Root-Vertrag einschließlich Ergänzungen gegen die Browserbelege;
`PASS`, `FAIL` und `NOT_PROVEN` bleiben dabei getrennte Urteile. Ein
unbewiesenes Pflichtkriterium ist kein PASS und kann keine aktive Version
freigeben.

Das gilt auch für Reparaturen innerhalb einer Stufe: Ein `finish_reason` wie
`length` wird vor HTML-, Patch- oder Fortsetzungsverarbeitung verworfen. Ein
zufällig mit `</html>` endender Nachtrag kann dadurch keinen Stage-Kandidaten
freigeben. Die Ablaufdetails zeigen die Usage je Stage einschließlich
bestätigter Ausgabe, Schätzung, unvollständiger Ausgabe, Aufrufen und
Modellzeit.

### Belege für Handy, Aufklapper und Ziehen (27.09.2026)

Anlass war eine Fitness-App (einer großen Fitness-App, deepseek-v4.1-flash). Eine
Änderung kam zweimal nicht über den ersten Versuch hinaus.

**Versuch 1:** Das Modell lieferte einen Änderungsblock mit zwei `=======`.
JOSHI fügte den ERSETZEN-Teil samt Trennmarke ein, und sie stand danach mitten
im JavaScript („Unexpected token '==='“). Die Reparaturen bekamen nur
„Zeile 754“ genannt und fanden die Stelle nicht.

- Blöcke mit einer Trennmarke im ERSETZEN-Teil werden nie angewendet
  (`html_werk.MARKE`); sie gehen in den gezielten Nachtrag.
- Übrig gebliebene Marken sind ein statischer Fehler mit Zeilennummer.
- Jeder Skriptfehler mit Zeilennummer bekommt einen nummerierten Code-Ausschnitt
  (±5 Zeilen, `>>` an der Fehlerzeile) in den Reparaturauftrag.

**Versuch 2:** Die Anwendung war technisch sauber und hatte fast alles umgesetzt,
die Abnahme sah es nur nicht. Es gab drei Runden mit exakt PASS 2 / FAIL 6.
Seitdem gilt:

- **Symbolknöpfe** („i“, „×“, „⇄“) heißen, was `aria-label`/`title` sagt;
  „(i)“ zählt als „Info“. Klassen und `data-`-Attribute der geklickten
  Knöpfe werden mit erfasst („chip-info“).
- **Aufklapper** (`<summary>`, alles mit `aria-expanded`) klickt die Probe
  zweimal: auf und wieder zu (`toggled`). Nennt ein Kriterium einen konkreten
  Knopf („Info-Knopf“), zählt nur dieser.
- **Aufgedeckter Text:** Je Klick werden die neu sichtbaren Zeilen erfasst
  (bis 600 Zeichen), etwa die aufgeklappte Übungsbeschreibung.
- **Fokus statt Zufall:** Die Probe klickt zuerst, was die Stichworte des
  Vertrags nennen. Gleichartige Knöpfe („+ hinzufügen“ ×20) klickt sie
  höchstens zweimal.
- **Handybreite** (390 px) ist ein eigener Beleg `mobil`:
  - Spalten und Breite der wiederholten Karten;
  - horizontaler Überlauf;
  - leere Flächen, die farblich vom Hintergrund abstechen (der „weiße Kasten“);
  - sichtbare Bedienelemente.
  Mobil-Wünsche zu Spalten, weißen Kästen, Überlauf und „mobil first“
  entscheidet die Messung deterministisch; bei einem Fehlschlag steht die
  gemessene Position in der Begründung.
- **Ziehen:** Neue Aktion `ziehen`. Bei mobilen Wünschen läuft sie als
  `ziehen_touch` in Handybreite. Die Probe klappt zuerst alles auf und setzt
  am Griff an (`[data-grip]`, `*grip*`, `*handle*`). Dann versucht sie:
  1. Touch-Ziehen per Pointer-Events (`pointerType: touch`), wobei Folgeereignisse
     wie auf echten Geräten an das Startelement gehen (implizites Capture);
  2. Antippen → Ziel antippen;
  3. auf dem Desktop HTML5-Drag&Drop;
  4. ein „Verschieben nach …“-Menü (auch als `<select>`).
  Gemessen wird die Verteilung nach Überschriften, sodass Neuzeichnen nicht
  stört. Nennt ein Kriterium ausdrücklich Schieben, Ziehen, Drag oder Finger,
  zählt nur echtes Ziehen; Antippen und Menü belegen dann nichts. Reines
  HTML5-draggable scheitert per Touch mit einem konkreten Hinweis
  (Pointer-Events oder Antippen ergänzen).
- **Probe am falschen Knopf zählt nicht:** Nennt ein Kriterium einen Knopf
  („Übung hinzufügen“), belegt eine Aktionsprobe an einem anderen Knopf („Als
  PDF sichern“) nichts. Passt der genannte Knopf nicht zur vermuteten Aktion,
  zählt jede sichtbare oder gespeicherte Wirkung, aber nur, wenn sich
  mindestens die Hälfte der Stichworte in Knopf, Rückmeldung oder Seite
  wiederfindet.
- **Stillstand:** Liefert eine Reparatur exakt dieselben Befunde wie davor,
  hört JOSHI auf, statt weiter zu raten.
- **Bauregeln 13/14:** Mobile first (390 px, eine Spalte); Drag & Drop auch
  per Finger (Pointer-Events oder Antippen); Aufklapper mit `<details>` oder
  `aria-expanded`; Symbolknöpfe mit `aria-label`.

**Nachmessung ohne Modell** (echter Vertrag 6a34362a, echtes WebKit):

| Fassung | vorher | jetzt |
| --- | --- | --- |
| v1 (aktiv) | – | PASS 3 · NOT_PROVEN 5 — Info, Aufklapper und Touch-Ziehen fehlen wirklich |
| v3 (abgelehnt) | PASS 2 · FAIL 6 | PASS 7 · NOT_PROVEN 1 — Karten nur über ein Menü, nicht per Finger |

**Stresstest mit Modell** (isolierte Instanz, Kopie von v1, dein Wortlaut,
`deepseek-v4.1-flash:cloud`):

- Versuch 1: PASS 6 · FAIL 1. Das allgemeine Mobil-Kriterium hatte noch keine
  Messregel. Nach der zweiten wirkungslosen Reparatur stoppte die
  Stillstandsregel.
- „Versuch es erneut“: dieselben 7 Kriterien, Version 3 in 130 s ohne Reparatur
  befördert, PASS 7 · FAIL 0 · NOT_PROVEN 0 allein aus der Messung. Die
  Fassung hat Info-Knöpfe mit ausführlicher Ausführung, aufklappbare Bereiche,
  eigene Übungen und Touch-Ziehen am Griff.
- Gegen den Originalvertrag nachgemessen: PASS 8/8, Touch-Ziehen per Finger belegt.
- Frischer Lauf 3 (neuer Auftrag, gleicher Wortlaut): Das Modell wollte die
  62.000 Zeichen große App ganz neu schreiben und dachte dabei 625.000
  Zeichen, ohne zu schreiben. Danach lief die Änderung gestuft in 6 Schritten.
  Die Schritte 1–5 bestanden (Schritt 2 mit echtem `touch_drag`), Schritt 6
  („Beschreibung aufklappen“) scheiterte. Ursache war die Probe, nicht die App:
  - Die Info-Knöpfe steckten in Karten, die erst „Karten ausklappen“ zeigt.
    Die Probe klappte den Bereich auf, zum Beweis des Zuklappens wieder zu und
    sah die Info-Knöpfe danach nie. Jetzt klappt sie ihn nach dem Beweis
    wieder auf, sodass die Knöpfe darin geklickt werden.
  - `info_aufklappen` bekam dadurch ein falsches PASS über „Karten
    ausklappen“. Jetzt gilt: Nennt die Beschreibung ausdrücklich einen
    „Info-Knopf“ (allgemein `<Name>-Knopf/-Button/-Schalter/-Symbol`), zählt
    nur ein Knopf dieses Namens, auch wenn die Probe keinen fand.
  - Nachgemessen: Zwischenstand 5 erfüllt alle 7 Kriterien mit echten Belegen,
    auch die Beschreibung mit Kontrolle, langsam, ruhig und Kraft.

**Denkbudget und große Dateien** (aus Lauf 3):

- Der Denkstrom (Reasoning ohne Ausgabetext) hat eine eigene harte Grenze:
  `max(150.000, 3 × Anwendungsgröße)`, bei Neubau 300.000 Zeichen, höchstens
  die harte Ausgabegrenze. Ab der Hälfte ohne einen Buchstaben Ausgabe kommt
  ein weicher Hinweis. Einstellbar über `JOSHI_GRENZE_DENK_FAKTOR`,
  `JOSHI_GRENZE_DENK_MINIMUM` und `JOSHI_GRENZE_DENK_NEU`.
- Scheitert der Patch einer Anwendung über 40.000 Zeichen (`GROSSE_DATEI`),
  lässt JOSHI sie nicht ganz neu schreiben, sondern geht in geprüfte Schritte.

Nicht reproduzierbar war der „weiße Kasten oben links“: Weder WebKit noch
Chromium zeigen ihn in 390 px, auch nicht im Sandkasten-iframe der Vorschau
mit dem gespeicherten Zustand. Die Messung in Handybreite würde eine leere
Kontrastfläche melden.

### Daten aus dem Netz: Preise recherchieren (`app/joshi/recherche.py`, 29.09.2026)

Ein Modell kann „aktualisiere die Preise“ nicht aus dem Gedächtnis — es erfindet
Zahlen. Deshalb recherchiert JOSHI selbst, bevor das Modell schreibt:

1. **Erkennen:** Der Wunsch nennt Preise und etwas Aktuelles („aktualisieren“,
   „echte/aktuelle Preise“, „Internet“, „abgleichen“ …) → eigener Schritt
   „Daten aus dem Netz“ vor „Änderung umsetzen“.
2. **Positionen:** Das Modell liest aus der App nur ab, welche Produkte mit
   welchem Preis darin stehen (höchstens 40; Platzhalter wie „Midi-Tower
   Standard“ fallen heraus).
3. **Suchen:** je Produkt über DuckDuckGo („… Preis“, „… ab €“) und gezielt bei
   geizhals.de und idealo.de, bei Hardware zuerst mindfactory.de. Preise zählen
   nur aus dem Titel eines passenden Treffers oder aus der Umgebung des
   Produktnamens auf der geladenen Seite (derselbe geschützte Abruf wie im Chat).
4. **Auswählen:** Modellnummern müssen exakt passen; Nachbarmodelle (Ti, Super,
   Plus, Pro, X, X3D …) zählen nicht. Plausibel ist 45–250 % des alten Preises.
   Vorrang haben Preisvergleiche und Wunschhändler, Suchlisten von Shops nur als
   Rückfall; der günstigste plausible Preis gewinnt. Ein einzelner Beleg mit mehr
   als 40 % Sprung gilt als unsicher — dann bleibt der alte Preis.
5. **Einsetzen — durch JOSHI selbst:** Seit dem ersten Live-Lauf (Modell setzte
   den Preisblock vor die Definition von `CAT_KEYS`, App tot) ersetzt JOSHI die
   Preise direkt im Code: exakter Produktname in Anführungszeichen, im selben
   Objekt genau ein Preisfeld mit dem alten Wert (`price:200` → `price:149.89`).
   Nachbarmodelle bleiben unberührt. Das Modell soll danach nur noch „Preise
   Stand …“ und die Quellen anzeigen. Am echten PC-Konfigurator: 27 von 27
   eingesetzt, App startet fehlerfrei. Nur was JOSHI nicht eindeutig findet,
   geht an das Modell.
   Früher: Das Modell bekam die Tabelle (Preis, Quelle, Link) und die
   Regeln: genau diese Werte, als Daten ablegen, „Preise Stand <Datum>“ und
   Quellen anzeigen, Berechnungen nutzen die neuen Preise.
6. **Prüfen:** Zusätzliches Pflichtkriterium „preise_recherchiert“: mindestens
   80 % der gefundenen Preise stehen im Code der neuen Version, sonst ein
   reparierbarer Befund mit der Liste der fehlenden.

Die Tabelle liegt im Arbeitsordner unter `recherche/preise-<Datum>.json`; jede
Position steht auch in den technischen Details. Gemessen an sechs PC-Teilen:
10–15 s, 3–4 von 6 mit belastbarer Quelle — die Trefferlage von DuckDuckGo
schwankt von Lauf zu Lauf. Tests: `tests/test_joshi_recherche.py`.

### Bibliotheken: einbetten statt verbieten (`app/joshi/bibliotheken.py`, 02.10.2026)

Ein Modell band für ein 3D-Sonnensystem three.js von cdn.jsdelivr.net ein; die Sandbox blockt
das Netz, die Seite blieb schwarz, und beide Reparaturen schrieben dieselbe Einbindung erneut.
Jetzt dürfen Anwendungen bekannte Bibliotheken als klassisches Skript von jsdelivr, unpkg oder
cdnjs einbinden (Bauregel 2). JOSHI lädt sie beim Verbinden einmal herunter (nur JavaScript,
höchstens 3 MB), legt sie unter `<Datenordner>/joshi-bibliotheken/` ab und ersetzt die
Einbindung durch `<script data-joshi-bibliothek="…" data-quelle="…"></script>`. Vorschau,
Prüfung, Export und Teilen betten den Code ein – die Datei läuft ohne Internet, der gespeicherte
Code bleibt klein. Fehlt eine Bibliothek im Datenordner, lädt JOSHI sie über die Quelle nach.
ES-Module (`import … from 'https://…'`) und andere Server bleiben blockiert.

Nachgemessen: die zuvor schwarze v1 des 3D-Sonnensystems läuft fehlerfrei mit allen Planeten.

### Recherche für jeden Auftrag (`recherche.recherche_planen`, 02.10.2026)

Mit eingeschaltetem **Web** plant JOSHI zuerst, welche Daten der Auftrag aus dem Netz braucht:

| Plan | Weg |
|---|---|
| `produkte` – kaufbare Produkte mit Preisen | Katalog bzw. Preisaktualisierung über Preisvergleiche (wie unten beschrieben) |
| `daten` – Orte, Adressen, Öffnungszeiten, Vereine, Termine, Kennzahlen … | bis zu 6 Themen: suchen, Seiten lesen, Einträge mit Feldern und Quelle ziehen |
| `keine` – Gestaltung, Rechner, Logik | keine Recherche, kein Zeitverlust |

Bei `daten` nennt das Modell nur Einträge, die in den gelesenen Texten stehen (JOSHI prüft
nach), Quellen nur aus den tatsächlich geladenen URLs. Die Tabelle geht als verbindliche
Datenbasis in Bau- oder Änderungsauftrag („bestehende Daten ergänzen, nichts erfinden“), liegt
im Arbeitsordner unter `recherche/daten-<Datum>.json`, und die Abnahme prüft, dass mindestens
70 % der Einträge in der neuen Version stehen. „Preise aktualisieren“ bei einer Änderung nutzt
weiter den direkten Preistausch.

Real gemessen: Reiseplaner Barcelona → 12 Sehenswürdigkeiten mit Quelle in 6 s;
Bundesliga-Übersicht → 18 Vereine in 14 s; BMI-Rechner → keine Recherche.

### Neubau mit aktuellen Produktdaten aus dem Netz (`recherche.katalog_erstellen`, 29.09.2026)

Verlangt ein Neubau aktuelle Daten aus dem Netz („PC-Konfigurator mit aktuellen
Hardware-Daten inkl. Preis und Leistung“, `bedarf_neubau`), kommt nach „Idee
verstehen“ der Schritt „Daten aus dem Netz“:

1. Das Modell plant bis zu 8 Kategorien mit je einer Suchanfrage nach einer
   aktuellen Bestenliste/Kaufberatung (mit Jahreszahl).
2. JOSHI sucht, lädt die besten drei Seiten und gibt deren Text dem Modell.
3. Das Modell nennt je Kategorie bis zu 6 Produkte — nur solche, deren Name
   wörtlich in den Texten steht (JOSHI prüft nach; Erfundenes fliegt raus) —
   mit Leistungsindex 1–100 aus Tests und Rangfolge (als Einschätzung markiert)
   und Merkmalen.
4. Für jedes Produkt läuft die Preisrecherche; in den Katalog kommt nur, was
   einen belastbaren Preis mit Quelle hat.
5. Der Katalog geht als verbindliches Material in den Bauauftrag; die Abnahme
   prüft, dass die Preise im Code stehen. Katalog als JSON im Arbeitsordner
   unter `recherche/katalog-<Datum>.json`.

Real gemessen: Bestenlisten 2026 liefern tatsächlich aktuelle Hardware
(RTX 50xx, RX 9070 XT, Ryzen 7 9800X3D, Core Ultra) — nicht den Stand aus dem
Modellgedächtnis.

### Arbeitsordner statt Workspace, Teil-Übernahme, Ablauf (29.09.2026)

- **Kein Workspace-Schalter mehr.** Jedes Produkt hat intern einen Arbeitsordner
  `<Datenordner>/joshi-projekte/<titel>-<id>/`. Nach jeder angenommenen Version
  schreibt JOSHI dort `index.html` (Bilder unter `assets/`, Daten unter `data/`),
  `JOSHI_PROJECT.md` und `README.md`, bei großen Anwendungen (ab 40.000 Zeichen)
  zusätzlich die Projektdateien unter `dateien/`. Aufträge rechnen in
  `auftraege/<job>/`. Rückfragen („Workspace aktivieren?“, „überführen?“) gibt es
  nicht mehr.
- **Größe erkennt JOSHI selbst.** Überschreitet ein Produkt erstmals die Grenze,
  bekommt der Nutzer einen Hinweis; das Moduszeichen zeigt dann „📁 Projekt“.
- **Teilen:** eine HTML-Datei, solange alles hineinpasst (Bilder eingebettet);
  gehören Daten- oder Mediendateien dazu, ein ZIP aus dem Arbeitsordner.
- **Mindestens eine funktionierende Version:** Läuft ein Änderungskandidat
  fehlerfrei, ging nichts verloren (keine Regression, nicht „deutlich kleiner“)
  und ist mindestens ein Pflichtpunkt nachgewiesen, wird er aktiv — Status
  „braucht Aufmerksamkeit“, mit der Liste des Offenen. Der Auftrag bleibt offen;
  „versuch es erneut“ setzt auf dieser Version fort. Kandidaten mit Fehlern
  oder ohne einen nachgewiesenen Punkt werden weiterhin abgelehnt.
- **Ablauf bleibt sichtbar:** Jede fertige Antwort zeigt ihre Schritte
  (Phasen bzw. Stufen mit Endzustand und Grund) — aufgeklappt, wenn etwas offen ist.
- **Tests schreiben nie in echte Daten:** Läuft unittest ohne
  `MINI_LLM_DATA_DIR`, nimmt `app/database.py` einen Wegwerf-Ordner.

### Anweisungen an JOSHI, Filter und Gestaltungsbelege (29.09.2026)

Anlass: Schichtplaner → Pflegedienst (`glm-5.3-flash:cloud`), zweimal abgelehnt,
obwohl der zweite Kandidat alles Gewünschte enthielt.

- **Anweisungen sind keine Anforderungen:** „nutz den Workspace“, „im
  Projektordner“ usw. (`aenderung.steuerung`) werden vor der Absichtserkennung
  entfernt. „Versuch es erneut und nutzt den workspace“ ist ein weiterer Versuch
  mit Projektdateien, auch unter 40.000 Zeichen. Alte Linien heilen sich:
  Kriterien aus so einer „Ergänzung“ entfallen (`vertrag_bereinigen`).
- **Filter leeren die Liste nicht mehr:** Sind nach dem Ausfüllen weniger als
  70 % der Knöpfe sichtbar, setzt die Bedienprobe die schuldigen Felder
  (etwa einen Statusfilter) auf den Ausgangswert zurück (`zurueckgesetzt`).
- **Farben und Glas werden gemessen** (`inhalt.js` → `gestaltung`): Farbfamilien
  auf sichtbaren Elementen (rot, orange, gelb, grün, türkis, blau, lila, pink)
  und Glaseffekte (`backdrop-filter`, halbtransparente Flächen). „In Rot, Gelb,
  Grün“ verlangt je Familie mindestens 2 Elemente; „Glas-Optik“ mindestens
  2 Elemente mit `backdrop-filter` und 2 halbtransparente Flächen.
- **Ein kopierbarer Link ist keine Datei:** Ein PDF-Export belegt ihn nicht.

Nachgemessen am abgelehnten Kandidaten 3: vorher PASS 1 / NOT_PROVEN 6,
jetzt alle 5 echten Kriterien PASS (Umplanen, Maps-Link, E-Mail-Vorlage,
rot 40× / gelb 5× / grün 86×, 20 Glas-Elemente). Die Ausgangsversion v1
fällt bei Farben und Glas weiterhin korrekt durch. Tests:
`tests/test_joshi_steuerung.py`.

### Wächter und Grenzen (`app/joshi/grenzen.py`)

Jede Generierung wird beobachtet: Zeichen, Dauer, Zahl der Änderungsblöcke
und Wiederholung (Kompressionsrate der letzten 16.000 Zeichen). Die Grenzen
sind relativ zur aktiven Anwendung und über `JOSHI_GRENZE_<NAME>` einstellbar:

| Grenze | weich (Hinweis) | hart (Abbruch) |
| --- | --- | --- |
| Ausgabe bei Änderung | max(60.000, 4 × Anwendung) | max(160.000, 10 × Anwendung) |
| Ausgabe bei Neubau | 150.000 | 720.000 |
| Änderungsblöcke | max(25, Anwendung/1.000) | max(60, Anwendung/400) |
| Dauer | 240 s | 900 s |
| Wiederholung | – | Kompression < 4 % ab 24.000 Zeichen |

Eine Stufe hat zusätzlich ihr eigenes, engeres Budget; die globale harte
Grenze bleibt dabei die Obergrenze:

| Stufengrenze | weich (Hinweis) | hart (Abbruch) |
| --- | --- | --- |
| Ausgabe | `min(globale harte Grenze, max(60.000, Anwendungsgröße))` | `min(globale harte Grenze, max(150.000, 1,5 × Anwendungsgröße))` |
| Änderungsblöcke | 20 | 40 |
| Dauer | 180 s | 480 s |

Die Stufenwerte lassen sich als `JOSHI_STAGE_SOFT_SECONDS`,
`JOSHI_STAGE_HARD_SECONDS`, `JOSHI_STAGE_SOFT_OUTPUT`,
`JOSHI_STAGE_HARD_OUTPUT` und `JOSHI_STAGE_MAX_PATCH_BLOCKS` setzen (oder
über die entsprechenden `JOSHI_GRENZE_STUFE_*`-Namen). Die Wiederholungsregel
gilt weiterhin auch innerhalb einer Stufe.

Der Wächter prüft die Grenzen nach **jedem** empfangenen Stream-Stück und auch
während er auf das nächste Stück wartet — nicht erst beim 1,2-Sekunden-Takt
der Oberfläche. Sichtbare Ausgabe und Denkstrom zählen beide. Damit kann ein
einzelner großer Chunk das Ausgabelimit nicht umgehen und langes Denken ohne
Text erreicht zuverlässig das Zeitlimit. Eine harte Grenze oder ein Abbruch
schließt den Iterator kontrolliert; der unvollständige Stand wird nicht
übernommen. Der Nutzer liest „Die Änderung ist ungewöhnlich groß. JOSHI
zerlegt sie in mehrere geprüfte Schritte.“ oder „Die Modellantwort erreichte
ihr Ausgabelimit. Der unvollständige Stand wurde nicht übernommen.“ Technische
Einzelheiten stehen in den Details.

### Technische Details

Jeder Auftrag trägt in `ergebnis.diagnose`: Versuch, Linie, Zahl der
Root-Kriterien, Routing-Gründe, Stufe, Ausgabegröße, Ende (`finish_reason`
bzw. `waechter`), Patch (gesamt/angewendet/Konflikte), Abnahme
PASS/FAIL/NOT_PROVEN, Reparaturen und ob befördert wurde. Für jede Stufe stehen
zusätzlich Zustand, Grenzfälle und eine eigene Usage mit bestätigten,
geschätzten oder unvollständigen Ausgabetokens. „Technische Details → Ablauf“
zeigt das als kleine Tabelle über dem Protokoll.

### Realer Retest (21.09.2026, `glm-5.3-flash:cloud`, isolierte Instanz)

1. v1 „Notiz-App“ gebaut: 4.519 Zeichen, bereit.
2. Große Änderung mit 7 Punkten (Speichern, Laden, Neu, Rückgängig/Wiederholen,
   Wortzähler, PDF über JOSHI, Neuladen). Daraus wurde ein Root-Vertrag mit 8
   typisierten Kriterien. Der Wächter war für diesen Lauf absichtlich eng
   eingestellt (`JOSHI_GRENZE_HART_MINIMUM=3000`), um die Ausgabegrenze
   nachzustellen. Die Einmal-Änderung wurde bei 3.377 Zeichen kontrolliert
   beendet, JOSHI plante 6 Schritte, Schritt 1 lief ebenfalls in die Grenze.
   Der Versuch scheiterte, v1 blieb aktiv.
3. Neustart mit normalen Grenzen, „versuch es erneut es umzusetzten“: dieselben
   8 Kriterien-IDs, kein neuer Vertragsaufruf, 6 Schritte. Schritt 3 war
   zuerst FAIL (kein Rückgängig-Knopf) und nach einer Reparatur PASS.
   Endabnahme **PASS 8 · FAIL 0 · NOT_PROVEN 0 allein aus der Messung**:
   - 5 Aktionsproben (Speicher geändert, Stand wiederhergestellt, 2 Felder
     zurückgesetzt, undo/redo);
   - 2 Szenarien, eines über ein echtes Neuladen (2 Phasen);
   - ein echtes PDF (5.331 Bytes).
   v2 wurde genau einmal befördert, 99 s, 7.463 Ausgabetokens.

## Asset-/Eingabeordner und Projekt-Workspace

JOSHI bleibt zuerst: Idee → schnelle kleine Anwendung → benutzen → teilen.
Zwei Ordner erweitern das, ohne es zu verlangsamen. Sie sind getrennte
Begriffe:

| | Asset-/Eingabeordner (technisch „inbound“) | Projekt-Workspace |
| --- | --- | --- |
| Bedeutung | „Hier darf JOSHI Material **finden**.“ | „Hier darf JOSHI an einem Projekt **arbeiten**.“ |
| Rechte | JOSHI nur lesen/auflisten; Nutzer kann bewusst Dateien importieren | lesen und schreiben, nur innerhalb der Wurzel; Nutzer kann bewusst Dateien importieren |
| Standard | aus, `~/JOSHI-Eingaben` | aus, `~/JOSHI-Workspace` |
| Oberfläche | „Assets / Eingaben“: Schalter, Pfad, Dateiliste ✓/○, Ordner auswählen, Geräte-Import, Finder anzeigen, Aktualisieren | „Projekt-Workspace“: Schalter, Pfad, Ordner auswählen, Geräte-Import, Finder anzeigen |

### Prinzipien

1. **Single File First.** Standard ist eine portable HTML-Datei.
2. **Inbound When Useful.** Dateien aus dem Eingabeordner werden genutzt,
   wenn ein Auftrag sie braucht.
3. **Workspace Only When Necessary.** Ein Projektordner entsteht nur, wenn
   die reale Struktur es verlangt.
4. **Inbound and Workspace are separate concepts.** Zwei Wurzeln, zwei
   Schalter, zwei Pfade. Keiner darf im anderen liegen (422 beim Speichern).
5. **Files are not automatically sent to models.** Eine neue Datei ist nur
   verfügbar. Ein Auftrag bekommt, was er ausdrücklich nennt (`@kunden.csv`,
   `logo.png`, eindeutig „das Logo“) oder eindeutig verlangt („aus der CSV“,
   „nutze das vorhandene Bild“, „daraus“). Sonst nichts: „Baue einen
   Taschenrechner“ bekommt keine Datei, auch wenn 25 im Ordner liegen.
   Abgeschaltete Dateien (○) bleiben draußen, außer man nennt sie ausdrücklich.
6. **Workspace activation does not force workspace usage.** Ein
   eingeschalteter Workspace erlaubt nur. Kleine Produkte bleiben
   Einzeldateien, ohne Ordner.
7. **JOSHI may recommend escalation from prototype to project.** Bei Bedarf
   und ausgeschaltetem Workspace (Neubau) antwortet die API mit einer
   `empfehlung` statt eines Auftrags: „Dieses Vorhaben wird größer als eine
   typische JOSHI-Einzelanwendung …“ mit [Workspace aktivieren] und [Weiter als
   Einzeldatei]. Wächst ein bestehendes Produkt, kommt das Angebot [In
   Workspace überführen] / [Als Einzeldatei weiterführen]. Der Nutzer
   entscheidet, es wird nichts automatisch geschrieben.
8. **Generated products never receive unrestricted filesystem access.** Die
   Anwendung im Sandkasten kennt nur `window.JOSHI.export`. Die
   Ordnerfähigkeiten (`inbound.list/read`, `workspace.list/read/write/mkdir/copy/delete`)
   sind interne Host-Funktionen mit festem Schema, kein RPC für Anwendungen,
   keine Shell.
9. **Workspace projects are automatically documented.** `JOSHI_PROJECT.md`
   wird angelegt und nach jeder angenommenen Version fortgeschrieben. Ein
   eigener Abschnitt „## Notizen“ bleibt erhalten. `README.md` wird einmal
   angelegt und danach dem Nutzer überlassen.
10. **Accepted products never silently change when input files change.** Beim
    Build werden die gewählten Dateien einmal gelesen (Snapshot mit Name, Art,
    Rolle, Größe, Änderungszeit, SHA-256, Zeitpunkt, in `joshi_jobs.input` und
    im Prüfbericht der Version). Bilder liegen als Kopie in JOSHIs Ablage,
    Daten stecken in der Version. Ins Projekt kommen Kopien des Snapshots, nie
    das Original.

### Rollen

`context` (nur zum Verstehen, etwa Anforderungen als PDF/MD), `data`
(Datenquelle, CSV/Excel/JSON), `asset` (sichtbar, etwa Logo, Icon, Foto),
`project_file` (bleibt eigene Datei: Video/Audio, Bilder > 6 MB, Daten > 2 MB,
wird dem Modell nicht geschickt), `output` (von JOSHI erzeugt). Die Rolle wird
deterministisch bestimmt. Ein Dokument wird nur zum Asset, wenn der Auftrag
das sagt („zum Download verfügbar“). Die Inhalte laufen durch dieselbe
Dateiverarbeitung wie hochgeladene Dateien (`prepare_attachments`: PDF, DOCX,
XLSX/XLS, CSV/JSON/MD/TXT), dazu eine kurze Rollenübersicht für das Modell.

### Wann ein Workspace nötig ist (`projekt.bedarf`)

Gezählt wird Struktur, nicht Tokens. +3 für Mediendateien oder übergroße
Dateien, mehr als 12 Bilder oder mehr als 8 MB Bilder, Mengenangaben wie „2.000
Produktbilder“. +2 je verlangtem Strukturmerkmal (mehrteilig/Module,
Verwaltungssystem, Dokumentation, Weiterentwicklung, großes System,
Datenimport). +1 für mindestens 4 Bilder, mindestens 5 Eingabedateien oder
Daten über 300 KB. +2, wenn ein bestehendes Produkt schon über 120.000 Zeichen
hat. Ab 3 Punkten ist ein Workspace sinnvoll.

### Projekt im Workspace

```text
<workspace>/<produkt>/
  index.html        Anwendung; Bilder relativ als assets/…, CSP erlaubt dafür 'self' file: (Netz bleibt gesperrt)
  assets/           nur die Bilder, die die Anwendung wirklich zeigt
  data/             Kopien der Datenquellen aus dem Snapshot
  JOSHI_PROJECT.md  Zweck, Ursprung, Funktionsumfang, Architektur, Daten, Eingaben (Rolle, Quelle,
                    Snapshot, Hash), Assets, JOSHI Capabilities, Persistenz, Export/Share,
                    Version/Stand, offene Punkte, Verlauf, Notizen
  README.md         Einstieg: was, wie starten, wichtigste Dateien
```

Leere Ordner entstehen nicht. Die Einzeldatei in JOSHI (Vorschau, Export,
Teilen) bleibt unverändert portabel.

### Interne Projektdateien bei großen Änderungen

Der interne Arbeitsmodus ist vom oben beschriebenen, vom Nutzer gewählten
Export-Workspace getrennt. Ab 40.000 Zeichen zerlegt `pipeline.py` eine
bestehende Anwendung in `index.html` und sichere Inline-CSS-/JavaScript-Teile;
Browser und Datenbankversion bleiben weiterhin eine einzige HTML-Datei. Die
zerlegte Fassung liegt nur intern unter
`DATA_DIR/joshi-projekte/<produkt>/auftraege/<job-id>/`. Pro Änderungsaufruf
bekommt das vorhandene zentrale Modell-Streaming eine Übersicht aller Teile
und den begrenzten Inhalt der für den Wunsch relevantesten Dateien. Antworten
werden auf erlaubte Pfade und tatsächlich mitgegebene Dateien geprüft;
Konflikte, fehlende Einbindungen und abgeschnittene Ausgaben verwerfen den
gesamten Kandidaten. Ein gezielter einmaliger Nachtrag ist nur für nicht
passende Patchanker erlaubt. Erst nach verlustfreier Zusammensetzung gehen
HTML, Browserprüfung, Reparatur und Promotion durch den bestehenden Ablauf.
`PROJEKT.md` und `manifest.json` sind auftragsbezogene interne Notizen, nicht
Teil des Produktexports. Der normale Chat, der Einzeldatei-Export und der
Nutzer-Workspace werden dadurch nicht umgestellt.

### Sicherheit

- Wurzeln im Benutzerordner, in `~/Library/Mobile Documents` bzw.
  `~/Library/CloudStorage` (iCloud/Cloud-Speicher) oder auf einem ausdrücklich
  eingehängten Laufwerk unter `/Volumes`; nicht die jeweilige Wurzel selbst,
  keine versteckten Ordner, nicht andere `~/Library`-Bereiche und nicht die
  Daten oder Programmdateien von Mini LLM.
- Jeder Pfad relativ: kein `..`, keine absoluten Pfade, keine versteckten
  Dateien, Symlinks werden aufgelöst und gegen die Wurzel geprüft.
- Schreiben geschieht atomar.
- Der Eingabeordner ist schreibgeschützt; `inbound.write` gibt es nicht.
- „Im Finder anzeigen“ zeigt nur freigegebene Wurzeln oder den eigenen
  Projektordner im Finder des Mac mini. „Ordner auswählen“ öffnet auf dem Mac
  einen nativen Ordnerdialog und speichert die Auswahl sofort. Auf iPhone/iPad
  wird kein Mac-Pfad vorgetäuscht: „Vom Gerät importieren“ überträgt bewusst
  ausgewählte Dateien in die aktivierte Wurzel.

### Erkennung und Oberfläche

Neue, geänderte und entfernte Dateien erkennt die Oberfläche durch leichtes
Nachsehen alle 6 s. Das passiert nur, solange JOSHI offen und sichtbar und der
Eingabeordner an ist; einen Hintergrund-Wächter gibt es nicht. Neue Dateien
werden angezeigt („Neue Datei erkannt: hero.jpg“), aber nie in einen laufenden
Build übernommen. Beim Tippen von `@` erscheinen passende Dateien als
Vorschläge. Die Werkzeugleiste zeigt dezent „⚡ Schnell-Anwendung“ oder
„📁 Workspace-Projekt“. Im Menü „…“ gibt es „In Workspace überführen“ bzw.
„Projektordner öffnen“. „Auswählen“ macht den Pfad editierbar: Der Ordner liegt
auf dem Mac mini. Für die mobile Nutzung wird Mini LLM über die in
`.public-network.txt` ausgegebene HTTPS-Adresse geöffnet (im Heimnetz direkt,
unterwegs über die konfigurierte VPN-/Router-Verbindung); das private
Mini-LLM-Zertifikat muss auf dem iPhone einmal vertraut werden.

API: `GET/PUT /api/joshi/einstellungen`, `GET /api/joshi/eingaben`,
`PUT /api/joshi/eingaben/datei`, `POST /api/joshi/ordner/{eingaben|workspace}/auswaehlen`,
`POST /api/joshi/ordner/{eingaben|workspace}/importieren`,
`POST /api/joshi/ordner/{eingaben|workspace}/oeffnen`,
`POST /api/joshi/produkte/{id}/workspace` (überführen),
`POST /api/joshi/produkte/{id}/workspace/oeffnen`. Neubau und Änderung nehmen
`modus` (`einzeldatei` | `workspace`) nach einer Empfehlung entgegen.

### Realer Smoke-Test (21.09.2026, `glm-5.3-flash:cloud`, isolierte Instanz mit eigenem HOME)

1. Eingaben `logo.png`, `kunden.csv`, `notizen-alt.txt`; Workspace an;
   „Erstelle aus der CSV ein kleines Kundendashboard und verwende das Logo.“
   Ergebnis: `kunden.csv` als Datenquelle, `logo.png` als Asset, die Notiz nicht
   verwendet. Einzeldatei (29 KB, Logo als Data-URI, Kundendaten im HTML), der
   Workspace-Ordner blieb leer. PASS 5/5, 56 s.
2. Dazu 6 Produktbilder, `produkte.csv`, `kategorien.csv`, `anforderungen.md`;
   Workspace aus; „Erstelle daraus eine größere mehrteilige Anwendung.“
   Ergebnis: Empfehlung („7 Bilder · 12 Eingabedateien · mehrteilig“), kein
   Produkt, nichts geschrieben.
3. Workspace an; „… vollständigen Produktkatalog mit Verwaltung …“.
   Ergebnis: Projekt `produktkatalog-mit-verwaltung/` mit `index.html`,
   `assets/` (7), `data/` (3), `JOSHI_PROJECT.md`, `README.md`, ohne leere
   Ordner und ohne Datei außerhalb des Projektordners. Im Browser luden alle
   7 Bilder relativ aus `assets/`, ohne Laufzeitfehler. Das erste Produkt
   blieb unverändert (v1, kein Workspace).

### Grenzen

- Rollen und Relevanz sind deterministisch (Wortlisten, Dateinamen). Ungewöhnliche
  Formulierungen treffen sie nicht immer; ausdrücklich `@datei` nennen hilft
  immer.
- Der Eingabeordner wird flach gelesen (keine Unterordner), höchstens 300
  Dateien.
- `index.html` im Workspace lädt Bilder über `file:`/`'self'`. Über HTTP ist
  das geprüft. Das direkte Öffnen als Datei hängt vom Browser ab und konnte
  hier nicht automatisch geprüft werden.
- Daten früherer Builds kopiert „In Workspace überführen“ nur, wenn die Datei
  im Eingabeordner noch denselben Hash hat; sonst stehen sie nur in der
  Dokumentation.

## Host Capability Bridge: Dokumente aus der laufenden Anwendung

Die Anwendung im Sandkasten darf nichts Privilegiertes tun. Sie soll aber
„Angebot als PDF speichern“ anbieten können, ohne dass jemand erst HTML
exportiert und separat öffnet. Deshalb beschreibt die Anwendung nur, **was**
exportiert werden soll; **ausgeführt** wird es von JOSHI.

```text
Anwendung (Sandkasten)      window.JOSHI.export({type, target, filename, title})
   ↓ postMessage (Laufzeit sammelt Ausschnitt + Stile)
JOSHI-Oberfläche            prüft Herkunft, Produkt, aktive Version, Typ
   ↓ POST /api/joshi/produkte/<id>/export/<typ>
Server                      prüft Besitz, Version, Größe, Dateiname; entfernt
                            Skripte aus dem Ausschnitt
   ↓ vorhandene Exporter (WebKit-PDF, Word-Export)
Download beim Nutzer
```

**API in der Anwendung** (mehr gibt es nicht):

```js
const antwort = await window.JOSHI.export({
  type: "pdf",            // pdf | docx | png | jpg
  target: "#angebot",     // CSS-Selektor des Bereichs; ohne target die ganze Seite
  filename: "angebot.pdf",
  title: "Angebot",
});
// { ok: true, filename: "angebot.pdf" } oder { ok: false, error: "…" }
```

**Was geprüft wird.** Kommt die Nachricht aus genau diesem Vorschaurahmen?
Gehört das Produkt dem angemeldeten Nutzer? Ist es die *aktive* Version? Ist
der Typ erlaubt (`pdf`, `docx`, `png`, `jpg` — nichts anderes)? Ist der
Ausschnitt vorhanden und nicht zu groß (1 MB HTML, 400 KB CSS)? Der Dateiname
wird auf einen reinen Downloadnamen gekürzt (kein `../`, keine Pfade, keine
Nullbytes). Höchstens zwei Exporte gleichzeitig je Produkt. Unbekannte
Nachrichtenarten und Typen werden abgelehnt.

**PDF** entsteht mit dem vorhandenen WebKit-Renderer als A4-Druckfassung mit
echtem Text (kein Screenshot-PDF), **DOCX** über den vorhandenen Word-Export
(Überschriften, Absätze, Tabellen, Beträge). Der Ausschnitt wird vor dem
Rendern von `<script>` und `on…`-Attributen befreit und mit derselben strengen
Richtlinie geladen.

**Sicherheit bleibt unverändert:** Die Sandbox behält `allow-scripts` ohne
eigene Herkunft, ohne `allow-downloads`, `allow-popups`, `allow-forms` oder
`allow-same-origin`; die CSP wird nicht gelockert. Den Download löst die
JOSHI-Oberfläche aus, nie die Anwendung.

**Ältere Anwendungen** funktionieren weiter: `window.print()` wird im
Sandkasten auf einen PDF-Export der ganzen Anwendung abgebildet. In der
exportierten HTML-Datei (ohne Host) druckt `window.print()` normal; ein
Word-Export meldet dort ehrlich, dass er nur in JOSHI verfügbar ist.

**Abnahme.** Verlangt ein Kriterium eine Datei („als PDF ausgeben“, „Word
herunterladen“), genügt kein Knopf: Die Bedienprobe löst den Export wirklich
aus, JOSHI erzeugt die Datei und prüft sie (PDF-Kopf, lesbares DOCX, Größe).
Erst dann gilt das Kriterium als erfüllt.

## KI-Sprachmodell in Anwendungen (`JOSHI.ki`)

Anlass (03.10.2026): Ein Holodeck mit Diskurs- und Adventure-Modus sprach Ollama und eine
OpenAI-kompatible API per `fetch` an und scheiterte im Export an `connect-src 'none'`. Die
Lösung öffnet das Netz **nicht** pauschal, sondern lässt Sicherheit und Anwendung miteinander sprechen:

| Wo | Was passiert |
|---|---|
| Vorschau in Mini LLM | `JOSHI.ki()` schickt die Anfrage per `postMessage` an Mini LLM. **Vor der ersten Anfrage fragt Mini LLM den Nutzer** (pro Produkt und Browser gemerkt). Der Server (`POST /api/joshi/produkte/{id}/ki`) nutzt dieselbe Modellschicht wie der Chat mit dem oben gewählten Modell. Die Anwendung sieht weder Ollama-Adresse noch Zugangsdaten. |
| Prüfung (WebKit) | feste Testantwort (`{}` bei JSON) — die Abnahme läuft ohne Modell und ohne Netz. |
| Export (HTML-Datei) | Richtlinie gibt **nur** `http://localhost:11434` frei, und nur wenn die Anwendung KI nutzt. Vor der ersten Anfrage fragt die Datei selbst nach. Hinweis: Browser melden geöffnete Dateien mit Herkunft `null`; Ollama erlaubt das nur mit `OLLAMA_ORIGINS="null"` — die Fehlermeldung nennt das. |

Vorhandener Code, der `…:11434/api/generate`, `/api/chat` oder `…/chat/completions` per `fetch`
aufruft, wird von der Laufzeit auf `JOSHI.ki()` umgeleitet und bekommt eine Antwort im jeweils
erwarteten Format (auch Streaming als ein Stück). API-Schlüssel aus dem Frontend werden nie
weitergeschickt. Grenzen pro Anfrage: 60 Nachrichten, 120.000 Zeichen, zwei gleichzeitig.

Bauregel 15 weist Modelle an, direkt `await window.JOSHI.ki({system, messages, format})` zu
nutzen und keine Provider-Einstellungen oder Schlüssel zu bauen. Die statische Prüfung meldet
reine KI-Aufrufe als Info, andere Netzwerkzugriffe weiter als Warnung. Tests: `tests/test_joshi_ki.py`.

## Laufzeit, Sandbox, Zustand

- **Vorschau:** `<iframe sandbox="allow-scripts">` ohne eigene Herkunft, mit
  `srcdoc`. Die CSP erlaubt nur Inline-Stil und -Skript und `data:`/`blob:`-
  Bilder und sperrt Netz, Frames, Objekte und Formularziele. Damit gibt es
  keinen Zugriff auf Mini LLM, Cookies oder das Dateisystem.
- **laufzeit.js** läuft vor jedem App-Code:
  - fängt `error`, `unhandledrejection` und `console.error`;
  - ersetzt im Sandkasten `localStorage`;
  - zeigt `alert` im Seiteninhalt;
  - verhindert Formular-Navigation.
- **Zustand** = `{felder: {"#id": wert}, speicher: {localStorage}}`, höchstens 256 KB:
  - Die Vorschau meldet Änderungen per `postMessage`. Joshi.js prüft den
    Absender-Rahmen und speichert sie per `PUT /zustand`.
  - Beim Öffnen setzt ein MutationObserver die Werte, sobald der Parser ein
    Feld anlegt, also bevor die App zum ersten Mal rechnet.
- Ein im Browser gemeldeter Fehler erscheint als Leiste mit „Von JOSHI beheben
  lassen“ und wird zu einem `reparieren`-Auftrag.

## Renderer (WebKit)

`app/joshi/renderer/joshi_render.swift`:
- wird beim ersten Start mit den Command Line Tools übersetzt (`swiftc`) und
  nach Quelltext-Hash in `~/Library/Caches/MiniLLM/` abgelegt;
- lädt die Seite unsichtbar mit fremder Herkunft (`https://produkt.joshi.invalid/`,
  nie erreicht) und führt ein Skript aus;
- erzeugt Vektor-PDF, daraus ein 2×-PNG der ganzen Seite, und eine A4-Druckfassung;
- ist so eingestellt, dass verborgene Seiten ihre Timer nicht drosseln
  (gemessen: sonst 1 s je `setTimeout`);
- lässt nach dem Laden keine Navigation mehr zu.

Ohne `swiftc` prüft JOSHI nur statisch und markiert die Version als
`needs_attention` — daraus wird niemals `ready`; Bild und PDF sind dann nicht
verfügbar. `JOSHI_RENDERER=aus` schaltet den Renderer ab (Tests),
`JOSHI_RENDERER=/pfad` nutzt ein eigenes Programm.

## Produkt und Versionen

| Tabelle | Inhalt |
| --- | --- |
| `joshi_products` | Titel, Auftrag, Status (`draft/building/ready/needs_attention/failed`), aktive Version, Verständnis, Zustand, Herkunft (Chat), behalten |
| `joshi_versions` | Nummer, HTML (zlib, rund 1/5 der Größe), Änderungswunsch, Prüfbericht, Modell |
| `joshi_jobs` | Auftrag mit Eingabe, Status, Fortschritt, Ereignissen, Ergebnis, Tokenverbrauch |
| `joshi_settings` | je Nutzer: Asset-/Eingabeordner (an/aus, Pfad, abgeschaltete Dateien) und Workspace (an/aus, Pfad) |
| `joshi_changes` | Änderungslinie: Root-Wunsch, Ergänzungen, Root-Vertrag, Versuche, Stufenplan, interner Checkpoint (zlib), Status `open/umgesetzt/verworfen` |
| `joshi_assets` | Bilder (gleiches Bild nur einmal), Datei unter `DATA_DIR/joshi/<produkt>/` |

- „Rückgängig“ aktiviert die nächstniedrigere *freigegebene* Version. Alle
  Versionen bleiben erhalten und lassen sich unter „Versionen“ zurückholen —
  abgelehnte Kandidaten nur ausdrücklich („Trotzdem verwenden …“).
- Nicht behaltene Produkte (☆) werden nach 30 Tagen entfernt.

## Export und Teilen

| Format | Weg |
| --- | --- |
| HTML | App + Laufzeit (Modus `export`) + Zustand + `<script id="joshi-daten">`-Metadaten, Bilder als Data-URI. Beim Empfänger zählt beim ersten Öffnen der mitgeschickte Stand. |
| PNG/JPG | WebKit, ganze Seite (nicht nur Viewport), 2× Auflösung, mit aktuellem Zustand |
| PDF | A4-Druckfassung mit echtem Text |
| DOCX | sichtbarer Inhalt (Überschriften, Texte, Tabellen, Feldwerte) → bestehender `build_docx` |
| E-Mail | `.eml`-Entwurf (X-Unsent) mit Betreff, Text und der HTML-Datei als Anhang; Vorlage zum Kopieren im Dialog |

## Chat-Brücke

- **Chat → JOSHI:** „Mit JOSHI umsetzen“ unter einer Chat-Antwort. Diese
  Antwort, die Frage davor und die zu dieser Frage hochgeladenen Dokumente
  (serverseitig über `user_contexts` autorisiert) reisen mit; der ganze Verlauf
  nicht.
  - Enthält die Antwort bereits eine vollständige HTML-Seite, wird sie
    übernommen und geprüft (`importieren`).
  - Begann der Chat mit „Im Chat besprechen“, werden die Vorschläge zur
    nächsten Version genau dieses Produkts (`aendern`).
- **JOSHI → Chat:** „Im Chat besprechen“ legt einen Chat an, der mit einer
  kompakten Übergabe beginnt (höchstens 4.500 Zeichen, nie HTML). Sie enthält:
  - Zweck, Auftrag und Funktionen;
  - Aufbau und Bedienelemente;
  - aktuelle Feldwerte, gemessen mit dem gespeicherten Zustand;
  - einen Inhaltsauszug und die Versionen.

## Seitenspalte: Tokenzähler, Cloud-Nutzung, Auslastung

Die drei Karten aus dem Chat („Diese Aufgabe“, „Ollama Cloud“, „Mac mini“)
stehen in JOSHI an derselben Stelle. Cloud-Nutzung und Auslastung werden
gespiegelt. Der Tokenzähler übernimmt nur die Darstellung; seine Werte
gehören ausschließlich zum ausgewählten JOSHI-Auftrag. Ein paralleler Chat
hat einen unabhängigen Zähler. Beide verwenden `renderTokenCounter()`.

Stand Hardening Patch 2 (21.09.2026):

- **Chat:** wie bisher — während des Stroms geschätzt, am Ende durch
  `eval_count` ersetzt, Tempo aus der Uhr des Browsers.
- **Zentrale Herkunft der JOSHI-Werte:** Nur `app/main.py` bucht Providerwerte
  in den gemeinsamen Verbrauch. Ein vorhandenes `prompt_eval_count` oder
  `eval_count` wird auch dann als echt behandelt, wenn sein Wert `0` ist. Für
  jede Richtung hält die Modellschicht zusätzlich fest, ob sie gemeldet wurde
  und für wie viele Aufrufe (`provider_input_usage_calls`,
  `provider_output_usage_calls`). Damit bedeutet ein fehlendes Feld nicht mehr
  fälschlich „0 Tokens“.
- **Getrennte Ausgabe-Usage:** `Lauf.tokenwerte()` liefert
  `output_tokens_actual` (bestätigte Ausgabetokens),
  `input_tokens_actual` (bestätigte Eingabetokens; `eingabetokens` bleibt der
  kompatible Name), `output_tokens_estimated` und
  `output_tokens_incomplete`. `tokens` ist nur die für die Anzeige bestimmte
  Summe aus bestätigter, geschätzter und unvollständiger **Ausgabe**; Eingabe
  ist davon getrennt. `tokens_actual` ist ein Alias für die bestätigte Ausgabe.
- **Bedeutung der Schätzungen:** Während eines Streams wird sichtbare Ausgabe
  und Denkstrom mit drei Zeichen je Token in `laufend_geschaetzt` angenähert.
  Endet ein Aufruf ordentlich, aber ohne Provider-Output-Usage, wandert seine
  Ausgabe nach `abgeschlossen_geschaetzt`. Bei Abbruch, Watchdog oder anderer
  Unterbrechung wandert bereits empfangene, nicht bestätigte Ausgabe nach
  `abgebrochen_geschaetzt` und `output_tokens_incomplete`; sie bleibt bewusst
  von normalen Schätzungen getrennt.
- **Usage-Status:** `actual` gibt es nur, wenn jeder Modellaufruf echte
  Output-Usage geliefert hat. `estimated` markiert eine ordentlich beendete,
  aber nicht vollständig vom Provider gemeldete Ausgabe. `incomplete` hat bei
  einer unterbrochenen Ausgabe Vorrang. Die Oberfläche setzt bei jedem Status
  außer `actual` ein `≈` vor den Gesamtwert und benennt bestätigte und
  geschätzte beziehungsweise unvollständige Anteile getrennt; ein gemischter
  Stand wird nie wie eine exakte Gesamtsumme dargestellt.
- **Tok/s:** `modellsekunden` zählt nur Modellzeit über alle JOSHI-Aufrufe;
  Browserprüfung, Rendern und Speichern zählen nicht mit. Bei vollständigen
  `eval_duration`-Werten ist die Rate gemessen. Fehlt eine Dauer oder enthält
  die Ausgabe eine Schätzung, bleibt die Rate ausdrücklich mit `≈` markiert.
- **Transport und Persistenz:** Die vollständige Tokenstruktur reist in
  `fortschritt` und `tokens`, wird im laufenden Job-Snapshot sowie in
  `joshi_jobs.usage.tokenstand` gespeichert und beim Produktwechsel oder
  Neuladen wiederhergestellt. `diagnose.stufen[].usage` bewahrt dieselbe
  Trennung pro Stufe einschließlich Aufrufe, Modellzeit und `finish_reason`.

## Tests

`tests/test_joshi.py` deckt ab:
- HTML-Werkstatt, Prüferregeln und Speicher;
- die Pipeline mit gespieltem Modell: beste Fassung behalten,
  Block-Nachbesserung, Fenstergrenze, Bildfähigkeit;
- Brücke und Architektur (keine eigene Ollama-Anbindung, Sandbox ohne
  `allow-same-origin`);
- echte WebKit-Prüfungen, die übersprungen werden, wenn der Renderer fehlt.

`tests/test_joshi_hardening.py` deckt die Fälle A–O des Hardening ab
(Retry mit allen Root-Kriterien, Ergänzung, `length`, Teil-Patch mit Nachtrag
und Konflikt, Speichern/Laden/Neu/Export ohne neues DOM, wirkungsloser Klick,
Modellurteil ohne Beleg, gestufter Modus mit genau einer Promotion,
fehlschlagender Schritt mit Fortsetzung, Abbruch, Wächter), dazu Altbestand,
Versionsschutz und — im echten WebKit — typisierte Klickwirkungen,
Aktionsproben, Szenarien mit echtem Neuladen und den realen Fehlerfall.

Hardening Patch 2 ergänzt dazu den deterministischen Router (viele einfache
UI-Wünsche bleiben schnell, schwere Systemverträge gehen direkt in Stufen),
abgeschnittene Stufen ohne Anwendung, Chunk-genaue Stage-Watchdogs und den
normalisierten Originalwunsch als Retry. `tests/test_joshi_stage_ui.py` und
`tests/joshi_stage_progress.cjs` prüfen, dass bestandene und gleichzeitig
aktive Stufen getrennt sichtbar bleiben. `tests/test_joshi_model_usage.py`,
`tests/test_joshi.py` und `tests/token_counter.cjs` prüfen echte Nullwerte,
fehlende Provider-Usage, gemischte bestätigte/geschätzte/unterbrochene Werte,
Persistenz und die `≈`-Kennzeichnung im Zähler.

`tests/test_joshi_mobil_belege.py` bildet den Fitness-Fall nach: Trennmarken im
Block, Code-Ausschnitt, Probe am falschen Knopf, Hälfte-der-Stichworte-Regel,
Aufklapper mit Zuklappen, Handybreite (Spalten, weißer Kasten) und im echten
WebKit HTML5-only-Ziehen (scheitert per Touch), Ziehen am Griff mit
Pointer-Capture (besteht), nur Antippen (belegt kein „schieben“), Info-Knöpfe
in einem eingeklappten Bereich (werden trotzdem geklickt) und ein allgemeiner
Aufklapper, der keinen genannten „Info-Knopf“ belegt. Dazu Denkbudget und
keine Neufassung großer Dateien nach einem Patch-Konflikt.

`tests/test_joshi_dateien.py` deckt Eingabeordner und Workspace ab (A–Q,
1–15): aus/an/abgeschaltet, neue Datei, Taschenrechner ohne Dateien, PDF als
Kontext, Icon eingebettet, Snapshot schützt die Version, kleine App ohne
Projektordner, Empfehlung ohne Schreiben, Projekt mit Dokumentation und
Kopien, Fortschreiben mit eigenen Notizen, Überführung, Pfadausbrüche,
Symlinks, Schreibschutz, Trennung beider Wurzeln.

`tests/test_joshi_projektdateien.py` und die Projektdatei-Fälle in
`tests/test_joshi_hardening.py` prüfen verlustfreies Zerlegen/Zusammensetzen,
Beschränkung auf dem Modell gezeigte Dateien, Pfadsicherheit, auftragsbezogene
Snapshots, Einsatz des vorhandenen Modell-Streams, abgeschnittene Antworten
und Konflikte ohne Rückfall auf eine HTML-Monster-Neufassung. Weitere
Vertragsfälle sichern Zurückstellen/Wiederaufnehmen und das Überspringen
zurückgestellter Stufen. Die Datenbanktests verwenden eine temporäre SQLite-
Datei, nicht die Datenbank des laufenden 24/7-Dienstes.

Für die Abnahme zusätzlich: Leer- und Regressionsregeln, Beweisauswertung,
Vertragsrobustheit, Kandidat/Promotion (Zustand, Export, Historie) sowie in
echtem WebKit die volle Kette aus leerem, unvollständigem und erfüllendem
Kandidaten.

Ende-zu-Ende gemessen am 19.09.2026 mit `glm-5.3-flash:cloud`:

| Lauf | Dauer | Ergebnis |
| --- | --- | --- |
| BMI-Rechner | 8,7 s | geprüft |
| Änderung „heller + Erklärung“ | 11,7 s | v2 |
| ROI-Rechner | 14,8 s | v1 |
| „Mach noch ein Diagramm dazu“ | 4,3 s | 3 Blöcke, v2 |
| Umfrage aus Chat-Konzept | 28,2 s | inklusive einer Ergänzung |
| Lokal mit einem 8B-Modell (16k) | rund 2,5 min | Bauen 118 s |
