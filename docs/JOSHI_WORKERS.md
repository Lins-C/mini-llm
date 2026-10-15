# JOSHI: Worker und begrenzte Modellrollen

Die Qualitätskontrolle hängt möglichst wenig vom Ausgabeformat und der
Selbsteinschätzung des gewählten Modells ab. Die Codequalität bleibt von dessen
Fähigkeiten beeinflusst. Es wird kein anderes Modell heimlich verwendet.

## Ablauf

1. Root-Vertrag und Plan: vorhandene Planung, nur offene gültige Kriterien.
2. Kontext-Worker: nach der Aufgabenrelevanz werden direkte Referenzen auf
   Definitionen in anderen JS-Dateien berücksichtigt. Die Auswahl bleibt auf
   vier Dateien / 30.000 Zeichen begrenzt. Das ist eine heuristische
   Quelltextanalyse, kein vollständiger JavaScript-Abhängigkeitsparser.
3. Builder: vorhandenes Streaming über die zentrale Mini-LLM-Modellschicht.
   Er kann einmal bekannte Produktdateien gezielt nachlesen.
   Die bisherige pauschale Sperre unter 12.000 Kontexttokens entfällt;
   ab 4.096 Tokens entscheidet die tatsächliche Eingabe-/Ausgabereserve,
   welche Dateien passen. Passt selbst eine sichere Teilaufgabe nicht,
   bleibt die Kontextfehlermeldung erhalten.
4. Antwort-Worker: neben Dateiabschnitten wird ein eindeutiges JSON-Objekt mit
   `dateien: [{pfad, inhalt}]` oder `path/content` gelesen. Inhalt bleibt
   unverändert. Unbekannte Pfade, ungesehene Bestandsdateien und unsichere
   Änderungen prüft weiterhin der bestehende Patch-Worker. Mehrdeutige oder
   zu große Dateilisten werden nicht teilweise akzeptiert.
5. Syntax-Worker: `node --check` parst ausführbare Inline-Skripte, ohne sie
   auszuführen. Fehler werden vor dem teureren Browserlauf an die Reparatur
   gegeben. JSON-Skripte werden nicht als JavaScript behandelt. Es gelten
   begrenzte Skriptzahl und Laufzeit; Child-Prozesse werden bei Timeout und
   Abbruch beendet. Die Umgebung enthält keine Provider-Zugangsdaten oder
   `NODE_OPTIONS`. Fehlt Node, bleibt die verpflichtende WebKit-Prüfung aktiv.
6. Browser-/Szenario-/Inhalts-Worker: vorhandene Desktop-/Mobil-, Bedien-,
   Persistenz-, Export- und Vertragsprüfung. Sie liefern den Funktionsnachweis.
7. RepairReviewAgent: bei technischen Fehlern oder Stillstand einmal je Job,
   sofern eine weitere Reparatur erlaubt ist und Builder-Budget bleibt.
   Separater strukturierter Aufruf mit dem ausgewählten Modell, höchstens
   18.000 Zeichen Quellkontext und drei Hinweise. Jeder Hinweis braucht einen
   wörtlichen Codeanker im tatsächlich mitgelieferten Ausschnitt. Fehlt dieser,
   wird er verworfen. Review ist eine Reparaturhypothese, keine Freigabe.
8. Reparatur-Builder und erneute technische Prüfung. Schlechtere Kandidaten
   ersetzen den besten geprüften Stand nicht. Stillstand nach einer erfolglosen
   Reparatur bleibt ein Abbruchgrund; es gibt keine offene Agentenschleife.

## Grenzen und Nachvollziehbarkeit

Alle Modellrollen erhalten ausschließlich den injizierten `Modellzugang` und
das vom Nutzer gewählte Modell. Keine zusätzliche Anbieteranbindung, keine
hart codierten Modellnamen, keine Shell-Fähigkeit für Modelle. Review benutzt
die bestehende Token-/Zeitmessung und das Zeitlimit strukturierter Aufrufe.
Builder-/Reparaturaufrufe unterliegen weiterhin dem gemeinsamen Auftragsbudget.

Die bestehenden technischen Ereignisse protokollieren Dateianforderungen und
Review-Einsatz. Fehlerhafte, unbewiesene und teilweise Ergebnisse behalten ihre
bisherigen Zustände und Versions-/Checkpoint-Historie. Normaler Chat,
Abbruchmöglichkeiten, persistierte Nutzerzustände und Runtime-Sandbox bleiben
in der vorhandenen Infrastruktur.

## Verifikation

`tests/test_joshi_agenten.py` prüft Abhängigkeitsauswahl, JSON-Formatadaption mit
Zugriffsprüfung, echten Syntaxcheck ohne Ausführen einer Endlosschleife,
Überspringen von JSON-Skripten, Compilerfehler vor Browserstart, Verwerfen
erfundener Reviewanker und das einmalige Review mit weiterhin negativem
Browserurteil. Unterschiedliche reale Modelle wurden für diesen Patch nicht
vergleichend ausgeführt; eine modellübergreifende Erfolgsquote ist deshalb
noch nicht belegt.

Prüfstand: vollständige JOSHI-Suite mit 300 Tests erfolgreich, zusätzlich acht
gezielte Agenten-Tests einschließlich Prozessabbruch erfolgreich. Gespeicherte
Zauberbuch- und Kolibri-Versionen wurden schreibgeschützt ohne Syntaxbefund
geprüft. Es wurden keine Nutzerprodukte nachträglich freigegeben.
