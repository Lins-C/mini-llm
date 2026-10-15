# JOSHI: konkrete Fehlversuche und Prüf-Worker

Stand: 15.10.2026. Grundlage: angehängte Prüfberichte, gespeicherte Aufträge
und schreibgeschützte Browserwiederholung der Zauberbuch-Versionen.

## Befund

- Zauberbuch, Auftrag `af94f41b0e0548f59583a017f764e60a`: 10 Modellaufrufe,
  122.611 bestätigte Ausgabetokens; Reparatur mit 192.317 Zeichen Denkstrom
  ohne sichtbaren Code abgebrochen. Die Ausgabetokens enthalten laut Provider
  auch Rechen-/Denkausgabe; sie sind kein Maß für gelieferten HTML-Code.
- Die Abnahme suchte bei „Geschichte länger“ nach den UI-Wörtern „Absätze“
  und „mehr Text“. Diese Wörter belegen keine Textverlängerung.
- Das Szenario für höchstens 40 Minuten Lese-/Aktionszeit verlangte die
  erfundene Anzeige `40:00`. Das ist weder eine notwendige Produkteigenschaft
  noch ein Beweis der gesamten Dauer. Derselbe ungeeignete Test blieb über
  Reparatur und Neuschreibung erhalten.
- Offscreen-WebKit ließ `.fade-in` auf `opacity:0` stehen. Der lesbare Text
  wurde deshalb aus der Inhaltsmessung ausgeschlossen. Browser-Replay nach
  Abschluss kurzer Einblendanimationen: V2 hat 291 Wörter in sieben Absätzen,
  der Lesebereich bleibt jedoch nur 34 % der Desktop-Browserbreite breit.
- Kolibri: Die Anhänge zeigen alte Probleme mit ResizeObserver-Meldungen und
  Vollbildnachweisen. Der aktuelle Quellstand enthält hierfür bereits Filter
  und Flächenmessungen auch nach Klicks. Diese Fehler nicht erneut durch ein
  zusätzliches Agentensystem kompensieren.
- Beide Berichte zeigen bewusst teilweise aktivierte Versionen. `befördert`
  bedeutet hier aktiv, nicht vollständig bestanden; `needs_attention` bleibt
  verbindlich. Unbewiesene Kriterien dürfen nicht als PASS umetikettiert werden.

## Implementierte Worker und Integration

`app/joshi/workers.py` enthält begrenzte Funktionen ohne eigene Modellanbindung:

1. Inhaltsprüfung: gemessene Wörter/Absätze und Vergleich mit der Ausgangsfassung.
   Fehlende Messwerte bleiben NOT_PROVEN; vorhandene negative Messwerte FAIL.
   Für „deutlich länger“ gilt die dokumentierte Heuristik +20 %, mindestens
   +50 Wörter, mindestens drei Absätze. Diese Heuristik ist keine Bewertung
   literarischer Qualität.
2. Layoutprüfung: misst die tatsächliche Breite des Lesebereichs. „Breit/großer
   Bereich“ verlangt derzeit mindestens 55 % der Desktop-Browserbreite.
3. Szenarioprüfung: ein Countdown/kurzer Klick darf die gesamte Lese-/Aktionszeit
   nicht beweisen. Solche Kriterien bleiben ehrlich NOT_PROVEN; sie werden
   nicht in wiederholte Code-Reparaturen oder eine teure Neuschreibung übersetzt.
4. Reparaturauftrag: offene Kriterien mit ihren Messwerten, Erhalt belegter
   Funktionen, keine bloße Ergänzung von Prüfbegriffen in der Oberfläche.

Die Inhaltsmessung erfasst sichtbare Lesebereiche vor und nach Klicks. Kurze
endliche Animationen bis drei Sekunden werden im Prüfbrowser bis zum Endzustand
ausgeführt. Endlose Spielanimationen bleiben unverändert. Alte Versionen ohne
Inhaltsmessung werden bei passendem Änderungsauftrag vor dem Build neu vermessen.

Alle generierenden Aufrufe laufen weiter über Mini LLMs zentrale Modellschicht.
Bestehende Jobverwaltung, Abbruch, Versionierung und Prüflimits bleiben aktiv.
Keine neuen fest codierten Modellnamen, keine frei laufende Agentenschleife.

## Grenzen und nächste Produktabnahme

Die gespeicherten Nutzerprodukte wurden für den Audit nicht umgeschrieben oder
nachträglich freigegeben. Zauberbuchs breite Lesefläche, einfacher KI-Knopf und
die vollständige 40-Minuten-Garantie sind durch diesen Systempatch noch nicht
fertiggestellt. Das Zeitbudget benötigt ein explizites Zeitmodell und eine
vollständige Ablaufprobe mit begrenzten Stationen; eine LLM-Bestätigung genügt
nicht. KI-abhängige Funktionen müssen zusätzlich mit freigegebenem realem
Modellaufruf geprüft werden; Testantworten der isolierten Runtime beweisen
keinen realen Anbieteraufruf.

Tests: reale Browserprobe für verborgenes Buch und Einblendanimation, positive
und negative Inhaltsnachweise, fehlende Messung, Countdown-Fehlprüfung,
Übernahme von Vergleichswerten und gezielter Reparaturauftrag.

Verifikation: 206 Tests aus JOSHI, Hardening, Ergebnis, mobilen Nachweisen,
Stage-UI und Worker-Tests bestanden. Nach dem letzten Ergänzungsschritt weitere
17 gezielte Worker-/Pipeline-Tests bestanden. Browser-Replays lesen gespeicherte
Versionen nur; es wurden keine neuen Modellaufrufe und keine Freigaben der
Nutzerprodukte erzeugt.

## Effizienzkorrektur nach dem nächsten Live-Versuch

Der nachfolgende Auftrag `348699ce708a40ebabc84349fa369100` beendete sich
mit Version 3, `needs_attention`, PASS 6 / FAIL 2 / NOT_PROVEN 1. Seine vier
ersten Schritte wurden gesichert. Adventure und Zeitbudget liefen jeweils
zweimal in das Denklimit; danach liefen zusätzliche Reparaturversuche. Die
Providerzählung erfasste 33.420 Tokens, hinzu kamen rund 370.687 geschätzte
Tokens aus abgebrochenen Strömen. Diese Schätzungen sind keine bestätigte
Abrechnung und kein nutzbarer Code.

Die Auftragssteuerung erhält deshalb ein gemeinsames Builder-Budget:

- 600 Sekunden tatsächliche Builder-Aufrufzeit, einschließlich Fehlversuchen;
- höchstens 16 gestartete Generierungen;
- 120.000 bestätigte bzw. geschätzte Ausgabetokens einschließlich Denkstrom;
- 60 Sekunden je strukturiertem Planungs-/Prüfaufruf;
- maximal 30.000 Zeichen und vier Dateien im Projektdatei-Kontext. Der
  Einstiegspunkt hat Vorrang; weitere Dateien werden nach dem aktuellen
  Schritt statt dem ganzen Root-Wunsch gewichtet. Dateien werden nicht gekürzt,
  und Änderungen an nicht mitgegebenen Dateien bleiben verboten.

Das Builder-Budget gilt über Stufen, Reparaturen und Wiederholungen hinweg.
Beim Erreichen wird der Strom geschlossen; Endprüfung und Sicherung der
Checkpoints dürfen weiterlaufen. Deshalb sind 600 Sekunden kein absolutes
Gesamtzeitlimit des Jobs. Ein bereits gestuft bearbeiteter Auftrag startet
anschließend keinen zusätzlichen kompletten Neubau mehr. Ein neuer bewusster
Nutzerversuch hat ein neues Budget und behält die Änderungslinie.

Konfiguration über `JOSHI_GRENZE_AUFTRAG_MODELLSEKUNDEN`,
`JOSHI_GRENZE_AUFTRAG_GENERIERUNGEN`, `JOSHI_GRENZE_AUFTRAG_AUSGABETOKENS`,
`JOSHI_GRENZE_STRUKTUR_SEKUNDEN`, `JOSHI_GRENZE_PROJEKT_KONTEXTZEICHEN` und
`JOSHI_GRENZE_PROJEKT_KONTEXTDATEIEN`. Der normale Chat wird nicht umgestellt.
Die Grenzen verhindern Ausreißer; sie garantieren keine vollständige Lösung.
Kleine Dateiauswahlen können zusätzliche Abhängigkeiten vermissen. In diesem
Fall greifen weiterhin Patchkonflikt- und Browserprüfungen.

Für den schlichten KI-Knopf werden Hintergrundbild, Schatten und Kindelemente
gemessen. Gemessene Layout-/Knopfanforderungen gelten nicht mehr als bloßer
Geschmack und werden nicht als bestandener Schritt protokolliert, solange
ihre Messung negativ ist. Die Kriterien bleiben Teil der Endabnahme.

Effizienz-Verifikation: alle 285 JOSHI-Tests bestanden; nach Ergänzung der
KI-Knopf-Messung 29 gezielte Worker-/Ergebnis-/Effizienztests bestanden.
Keine neuen kostenpflichtigen Modellläufe für diese Verifikation gestartet.

## Arbeitszyklus: Bericht von Versuch 2 ausgewertet

Der angehängte Bericht bestätigt einen zusätzlichen Steuerungsfehler: Geplant
werden sollten vier offene Kriterien, das Modell lieferte sechs Schritte.
Zwei davon hatten nach der ID-Prüfung kein Kriterium mehr. Trotzdem wurden
diese ausgeführt; der leere Adventure-Schritt verbrauchte zwei Denklimits.
Die Plan-Normalisierung entfernt solche Schritte nun. Auch historische
gespeicherte Pläne führen keinen Schritt ohne aktives Kriterium mehr aus.
Ein gültiger Plan mit genau einem offenen Schritt bleibt ein Schritt.

Der Projektdatei-Builder kann nun einmal bis zu drei Dateien aus der bekannten
Projektübersicht explizit zum Lesen anfordern (`=== LESEN: … ===`). JOSHI liefert
ihre vollständigen Inhalte innerhalb des bestehenden Kontextbudgets; danach
folgt die Änderung. Unbekannte Pfade, mehr als drei Anforderungen oder ein
überschrittenes Kontextfenster werden kontrolliert abgelehnt. Es gibt keinen
Zugriff auf beliebige Dateien oder eine Shell. Generierung und Dateinachforderung
bleiben im gemeinsamen Builder-Budget und in der zentralen Modellschicht.

Browser-Szenarien erhalten echte Element-IDs, auch für zunächst verborgene
Ansichten. `merken` und `text_geaendert` prüfen einen konkreten Textbereich vor
und nach einer Aktion. `klicken_in` wählt den ersten sichtbaren aktiven Knopf
innerhalb eines per ID bestimmten Auswahlbereichs. Damit lassen sich zufällige
Auswahltexte prüfen, ohne einen früheren Geschichtentitel zu verlangen.

Wird ein Szenario wegen eines fehlenden Ziels nicht ausführbar, versucht der
Prüf-Worker einmal eine Korrektur des Szenarios vor einer Code-Reparatur.
Ein weiterhin nicht ausführbares Ablauf-Szenario bleibt NOT_PROVEN und wird
weder durch Modellurteil zu FAIL/PASS noch zu einer Code-Reparatur umgedeutet.

Schreibgeschützter Replay der gespeicherten Zauberbuch-Version 3: `startBtn`
→ `advBtn` → `merken advText/advLog` → Auswahl in `symbolRow` → beide Textbereiche
geändert → keine Skriptfehler: bestanden. Das belegt die lokale Bedienfolge,
nicht die Semantik eines echten KI-Anbieteraufrufs und nicht das gesamte
40-Minuten-Zeitmodell. Keine neue Produktversion wurde dadurch freigegeben.

Unbewiesene Schritte dürfen als interne Checkpoints erhalten bleiben, erscheinen
aber nicht mehr als „geprüft bestanden“. Dafür zählen alle blockierenden
Abnahmearten (FAIL, NOT_PROVEN, unbeweisbar) in der Stufensteuerung. Ein
Weiterarbeiten mit einem tragfähigen Zwischenstand ersetzt keinen Nachweis.

Verifikation dieses Arbeitszyklus-Patches: 293 JOSHI-Tests bestanden, dazu
gezielte Dateilese-/Szenario-/Plan-Tests. Die Browserprobe enthält sowohl eine
funktionierende Auswahl als auch eine absichtlich wirkungslose Auswahl; nur
die funktionierende Variante besteht den Vorher-/Nachher-Nachweis.
