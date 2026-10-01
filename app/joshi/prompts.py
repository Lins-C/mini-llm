# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die Anweisungen an das Modell — kurz, eindeutig, modellunabhängig.

Jede Phase bekommt nur, was sie braucht: Verstehen sieht den Auftrag, Bauen
das Verständnis, Ändern das aktuelle HTML und den Wunsch, Reparieren zusätzlich
die Befunde des Prüfers. Kein Chatverlauf, keine Werkzeugregeln.
"""
from __future__ import annotations

import json
from typing import Any

VERSTAENDNIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "zweck": {"type": "string"},
        "art": {"type": "string", "enum": [
            "rechner", "formular", "umfrage", "dashboard", "vergleich", "liste",
            "planer", "spiel", "praesentation", "werkzeug", "seite",
        ]},
        "funktionen": {"type": "array", "items": {"type": "string"}},
        "bedienelemente": {"type": "array", "items": {"type": "string"}},
        "daten": {"type": "array", "items": {"type": "string"}},
        "gestaltung": {"type": "string"},
    },
    "required": ["titel", "zweck", "art", "funktionen", "bedienelemente", "gestaltung"],
}

VERSTEHEN_SYSTEM = """Du bist JOSHI. Menschen beschreiben dir, was sie gerade brauchen — du planst daraus eine kleine, sofort benutzbare Anwendung, die als eine einzige HTML-Datei im Browser läuft.

Antworte nur mit JSON:
- titel: kurzer Produktname (2–5 Wörter), in der Sprache des Nutzers
- zweck: ein Satz, wofür die Anwendung da ist
- art: rechner | formular | umfrage | dashboard | vergleich | liste | planer | spiel | praesentation | werkzeug | seite
- funktionen: 3–8 konkrete Funktionen, die die Anwendung haben muss (Eingaben, Berechnungen, Auswertungen, Anzeigen)
- bedienelemente: nur Knöpfe und Eingabefelder, jeweils nur ihre genaue Beschriftung (1–4 Wörter, keine Beschreibung), z. B. „Berechnen“, „Zurücksetzen“, „Gewicht (kg)“ (höchstens 8)
- daten: welche Werte die Anwendung sich merkt oder anzeigt (Startwerte, Beispielwerte)
- gestaltung: ein Satz zu Aufbau und Stil (hell/dunkel, Karten, Tabellen, Diagramm …)

Plane nur, was der Auftrag verlangt oder offensichtlich braucht. Keine Anmeldung, kein Server, keine Datenbank."""

BAU_REGELN = """Regeln für die Datei:
1. Gib ausschließlich das HTML-Dokument aus: Es beginnt mit <!DOCTYPE html> und endet mit </html>. Kein Text davor oder danach, kein Markdown.
2. Alles steckt in dieser einen Datei: CSS in <style>, JavaScript in einem <script> am Ende von <body>. Keine externen Dateien, keine CDNs, keine Webfonts, keine Frameworks, kein fetch oder sonstiger Netzwerkzugriff.
3. Responsive: <meta name="viewport" content="width=device-width, initial-scale=1">, flexible Layouts mit max-width, Flexbox oder Grid mit Umbruch. Funktioniert ab 360 px Breite; keine festen Breiten über 100 %.
4. Jedes Eingabefeld und jede Auswahl hat eine eindeutige id und ein sichtbares <label for="…">. Knöpfe sind <button type="button"> mit sichtbarer Beschriftung.
5. Die Anwendung startet sofort sinnvoll: Startwerte oder Beispielwerte vorbelegen und das Ergebnis gleich beim Laden berechnen und anzeigen. Ergebnisse aktualisieren sich bei jeder Eingabe (input-Ereignis) oder per Knopf.
6. Zahlen robust lesen (parseFloat, leere oder ungültige Eingaben abfangen) — niemals „NaN“ oder „undefined“ anzeigen, stattdessen einen verständlichen Hinweis.
7. Kein alert(), confirm() oder prompt(): Meldungen, Hinweise und Ergebnisse erscheinen im Seiteninhalt.
8. Diagramme zeichnest du selbst mit <svg> oder <canvas> (Achsen, Beschriftungen, Werte), ohne Bibliothek.
9. Zustand: Formularwerte merkt sich JOSHI automatisch (dafür die ids). Listen und Einträge, die der Nutzer anlegt, speicherst du als JSON in localStorage unter einem festen Schlüssel und lädst sie beim Start.
10. Klare Sprache in der Sprache des Nutzers, ruhiges modernes Design, gute Kontraste, großzügige Abstände, gut lesbare Schrift (system-ui). Zahlen im deutschen Format, wenn der Nutzer Deutsch schreibt (toLocaleString("de-DE")).
11. Druckfreundlich: Eine @media-print-Regel sorgt für hellen Hintergrund, dunkle Schrift und break-inside: avoid bei Karten.
12. PDF oder Word erzeugt JOSHI für dich — nicht window.print() und keine eigenen Download-Tricks:
    await window.JOSHI.export({ type: "pdf", target: "#ergebnis", filename: "ergebnis.pdf", title: "Ergebnis" })
    type ist "pdf", "docx", "png" oder "jpg"; target ist der CSS-Selektor des Bereichs, der ins Dokument soll.
    Die Antwort ist {ok: true, filename} oder {ok: false, error}; zeige danach kurz „PDF wurde erstellt“ bzw. den Fehler an.
13. Mobile first: zuerst für 390 px gestalten (eine Spalte, volle Breite), größere Ansichten mit @media (min-width: …). Drag & Drop muss auch per Finger gehen: Pointer-Events (pointerdown/pointermove/pointerup, touch-action: none am Griff) statt nur HTML5-draggable — oder zusätzlich „Element antippen, dann Ziel antippen“.
14. Auf- und zuklappbare Bereiche mit <details>/<summary> oder einem <button aria-expanded>; Knöpfe mit Symbol („i“, „×“) bekommen ein aria-label."""

BAUEN_SYSTEM = f"""Du bist JOSHI und baust aus einem Auftrag eine fertige, benutzbare Anwendung als EINE eigenständige HTML-Datei. Das Ergebnis wird sofort im Browser geöffnet, automatisch bedient und geprüft — es muss ohne Nacharbeit funktionieren.

{BAU_REGELN}"""

AENDERN_SYSTEM = f"""Du bist JOSHI. Du änderst eine bestehende, funktionierende Anwendung (eine HTML-Datei) gezielt nach dem Wunsch des Nutzers. Alles, was nicht betroffen ist, bleibt exakt erhalten.

Antworte mit Änderungsblöcken in genau diesem Format:

<<<<<<< SUCHEN
(ein Ausschnitt, der Zeichen für Zeichen in der aktuellen Datei vorkommt)
=======
(der neue Ausschnitt, der ihn ersetzt)
>>>>>>> ERSETZEN

- Beliebig viele Blöcke, in der Reihenfolge der Datei. Jeder SUCHEN-Teil ist eindeutig, genau kopiert und kurz (einige Zeilen).
- Um etwas einzufügen, nimm eine vorhandene Zeile als SUCHEN-Teil und gib sie im ERSETZEN-Teil zusammen mit dem Neuen aus.
- Achte darauf, dass HTML, CSS und JavaScript zusammenpassen (ids, Funktionsnamen, Ereignisse).
- Nur wenn sich fast die ganze Datei ändert, gib stattdessen das vollständige neue HTML-Dokument aus (<!DOCTYPE html> … </html>).
- Kein weiterer Text.

Für alles, was du neu schreibst, gelten diese Regeln:
{BAU_REGELN}"""

PROJEKTDATEIEN_SYSTEM = """Du bist JOSHI und änderst eine bestehende HTML-Anwendung, die intern in Dateien aufgeteilt ist.
JOSHI setzt deine Antwort anschließend wieder zu genau einer HTML-Datei zusammen, lädt sie in einem Browser und prüft sie technisch. Du entscheidest nicht selbst, ob sie funktioniert.

Antworte ausschließlich in Dateiabschnitten mit diesem Format:
=== ÄNDERN: pfad/der/datei.js ===
<<<<<<< SUCHEN
(kurzer, zeichengetreu kopierter Ausschnitt aus genau dieser Datei)
=======
(Ersatz)
>>>>>>> ERSETZEN
=== ENDE ===

Wenn sich fast die ganze Datei ändert, darfst du stattdessen ihren vollständigen Inhalt ausgeben:
=== DATEI: pfad/der/datei.js ===
(vollständiger Dateiinhalt, kein Markdown)
=== ENDE ===

Regeln:
- Ändere ausschließlich Dateien, deren Inhalt im Auftrag vollständig enthalten ist. Dateinamen und Übersicht sind keine Erlaubnis, ungesehene Dateien zu ändern.
- Gib nur tatsächlich geänderte Dateien aus. Für eine neue Datei verwende DATEI und einen neuen Pfad unter css/ oder js/.
- index.html enthält feste Einbindungsmarken `<!-- JOSHI-DATEI … -->`. Lass sie stehen, außer der Auftrag verlangt ausdrücklich eine neue/entfernte Datei.
- Ein SUCHEN-Teil muss exakt und eindeutig in der jeweiligen Datei vorkommen. Erfinde keine Zeilennummern und keine Anker.
- Keine Auslassungen wie „Rest unverändert“, keine Platzhalter und keine Erklärungen außerhalb der Dateiabschnitte.
- Erhalte Verhalten und Nutzerdaten, die nicht zum Änderungswunsch gehören. Änderungen an JavaScript, CSS und Markup müssen zusammenpassen.
- Schreibe nur vollständigen, syntaktisch gültigen Code; JOSHI prüft anschließend das zusammengesetzte HTML im Browser."""

NEU_SCHREIBEN_SYSTEM = f"""Du bist JOSHI. Du bekommst eine bestehende Anwendung (eine HTML-Datei) und einen Änderungswunsch. Gib die vollständige, geänderte Datei aus. Alles, was nicht betroffen ist, bleibt inhaltlich und funktional erhalten.

{BAU_REGELN}"""

FORTSETZEN = (
    "Deine Ausgabe wurde abgeschnitten. Setze exakt an der Stelle fort, an der sie endet — "
    "ohne Wiederholung, ohne Erklärung, ohne Markdown — und schließe die Datei mit </html> ab."
)


def verstaendnis_text(verstaendnis: dict[str, Any]) -> str:
    teile = []
    for schluessel, name in (("titel", "Titel"), ("zweck", "Zweck"), ("gestaltung", "Gestaltung")):
        if verstaendnis.get(schluessel):
            teile.append(f"{name}: {verstaendnis[schluessel]}")
    for schluessel, name in (("funktionen", "Funktionen"), ("bedienelemente", "Bedienelemente (genau so beschriften)"),
                             ("daten", "Daten und Startwerte")):
        werte = [str(w) for w in verstaendnis.get(schluessel) or [] if str(w).strip()]
        if werte:
            teile.append(f"{name}:\n" + "\n".join(f"- {w}" for w in werte[:10]))
    return "\n".join(teile)


def bilder_text(bilder: list[dict[str, Any]], sieht_bilder: bool) -> str:
    if not bilder:
        return ""
    zeilen = ["Bereitgestellte Bilder — einbinden mit genau dieser Adresse:"]
    for bild in bilder:
        zeilen.append(f'- <img src="joshi:{bild["name"]}" alt="…">  ({bild.get("datei") or bild["name"]})')
    if sieht_bilder:
        zeilen.append("Die Bilder sind dieser Nachricht angehängt. Nutze sie als Inhalt oder als Vorlage für Gestaltung und Aufbau, je nach Auftrag.")
    else:
        zeilen.append("Du kannst die Bilder nicht sehen; binde sie dort ein, wo es der Auftrag verlangt (z. B. Logo oben).")
    return "\n".join(zeilen)


def verstehen_nachrichten(auftrag: str, material: str, chat: str, bilder: str) -> list[dict[str, Any]]:
    inhalt = f"Auftrag:\n{auftrag.strip()}"
    if chat:
        inhalt += f"\n\nHintergrund aus dem Chat:\n{chat[:6000]}"
    if material:
        inhalt += f"\n\nMaterial (Auszug):\n{material[:6000]}"
    if bilder:
        inhalt += f"\n\n{bilder}"
    return [{"role": "system", "content": VERSTEHEN_SYSTEM}, {"role": "user", "content": inhalt}]


def bauen_nachrichten(auftrag: str, verstaendnis: dict[str, Any], material: str, chat: str,
                      bilder: str) -> list[dict[str, Any]]:
    inhalt = f"Auftrag des Nutzers:\n{auftrag.strip()}\n\nSo ist die Anwendung geplant:\n{verstaendnis_text(verstaendnis)}"
    if chat:
        inhalt += f"\n\nHintergrund aus dem Chat (Konzept, auf dem der Auftrag beruht):\n{chat}"
    if material:
        inhalt += f"\n\nMaterial des Nutzers (Inhalte übernehmen, wo sinnvoll):\n{material}"
    if bilder:
        inhalt += f"\n\n{bilder}"
    inhalt += "\n\nGib jetzt die vollständige HTML-Datei aus."
    return [{"role": "system", "content": BAUEN_SYSTEM}, {"role": "user", "content": inhalt}]


def _zustand_text(zustand: dict[str, Any] | None) -> str:
    if not zustand:
        return ""
    felder = zustand.get("felder") or {}
    if not felder and not zustand.get("speicher"):
        return ""
    return "Aktueller Zustand beim Nutzer (bleibt nach der Änderung erhalten, ids also nicht umbenennen):\n" + json.dumps(
        {"felder": felder, "speicher": zustand.get("speicher") or {}}, ensure_ascii=False)[:2500]


def aendern_nachrichten(dokument: str, wunsch: str, *, zustand: dict[str, Any] | None, material: str,
                        bilder: str, vollstaendig: bool) -> list[dict[str, Any]]:
    inhalt = f"Aktuelle Datei:\n<datei>\n{dokument}\n</datei>"
    zustandstext = _zustand_text(zustand)
    if zustandstext:
        inhalt += f"\n\n{zustandstext}"
    if material:
        inhalt += f"\n\nNeues Material des Nutzers:\n{material}"
    if bilder:
        inhalt += f"\n\n{bilder}"
    inhalt += f"\n\nÄnderungswunsch:\n{wunsch.strip()}"
    inhalt += ("\n\nGib jetzt die vollständige geänderte HTML-Datei aus." if vollstaendig
               else "\n\nGib jetzt die Änderungsblöcke aus.")
    return [{"role": "system", "content": NEU_SCHREIBEN_SYSTEM if vollstaendig else AENDERN_SYSTEM},
            {"role": "user", "content": inhalt}]


def projektdateien_nachrichten(uebersicht: str, dateien: dict[str, str], wunsch: str, *,
                               zustand: dict[str, Any] | None = None, material: str = "",
                               bilder: str = "") -> list[dict[str, Any]]:
    """Ein Änderungsaufruf bekommt die Projektübersicht und nur ausgewählte Dateien."""
    inhalt = "Projektübersicht (Dateiinhalt ist nur für unten aufgeführte Dateien vorhanden):\n" + uebersicht
    zustandstext = _zustand_text(zustand)
    if zustandstext:
        inhalt += f"\n\n{zustandstext}"
    if material:
        inhalt += f"\n\nNeues Material des Nutzers:\n{material}"
    if bilder:
        inhalt += f"\n\n{bilder}"
    for name, text in dateien.items():
        inhalt += f"\n\nDatei {name}:\n<joshi-datei pfad=\"{name}\">\n{text}\n</joshi-datei>"
    inhalt += f"\n\nÄnderungswunsch:\n{wunsch.strip()}\n\nGib jetzt nur die nötigen Dateiabschnitte aus."
    return [{"role": "system", "content": PROJEKTDATEIEN_SYSTEM}, {"role": "user", "content": inhalt}]


def projektdateien_nachtrag(projektdateien: dict[str, str], offen: dict[str, list[tuple[str, str]]],
                            wunsch: str) -> list[dict[str, Any]]:
    """Gezielter Folgeaufruf nur für Projekt-Patches, deren Anker nicht passten."""
    teile = []
    for name, bloecke in offen.items():
        datei = projektdateien.get(name)
        if datei is None:
            continue
        probleme = "\n\n".join(
            f"<<<<<<< SUCHEN\n{alt}\n=======\n{neu}\n>>>>>>> ERSETZEN" for alt, neu in bloecke)
        teile.append(f"Datei {name}:\n<joshi-datei pfad=\"{name}\">\n{datei}\n</joshi-datei>\n"
                     f"Nicht passende Änderungen:\n{probleme}")
    inhalt = ("Aktueller Projektstand (andere Änderungen sind bereits eingearbeitet):\n\n"
              + "\n\n".join(teile) + f"\n\nUrsprünglicher Wunsch:\n{wunsch.strip()[:2000]}\n\n"
              "Gib ausschließlich neue ÄNDERUNGS-Blöcke für diese fehlenden Stellen aus. "
              "Kopiere jeden SUCHEN-Teil exakt aus der aktuellen Datei. Keine vollständigen Dateien.")
    return [{"role": "system", "content": PROJEKTDATEIEN_SYSTEM}, {"role": "user", "content": inhalt}]


def reparieren_nachrichten(dokument: str, befunde: str, *, auftrag: str, vollstaendig: bool) -> list[dict[str, Any]]:
    wunsch = (
        "Die automatische Prüfung im Browser hat diese Probleme gefunden. Behebe genau diese Ursachen, "
        "ohne Funktionen zu entfernen:\n" + befunde
        + (f"\n\nZur Erinnerung, der ursprüngliche Auftrag:\n{auftrag.strip()[:1500]}" if auftrag else "")
    )
    return aendern_nachrichten(dokument, wunsch, zustand=None, material="", bilder="", vollstaendig=vollstaendig)


def nachtrag_nachrichten(dokument: str, offen: list[tuple[str, str]], wunsch: str) -> list[dict[str, Any]]:
    """Nur die Blöcke, die nicht passten — bezogen auf den teilweise geänderten Stand.

    Gefunden am 21.09.2026: Die frühere Nachforderung („gib alle Blöcke erneut
    aus, bezogen auf die ursprüngliche Datei“) beantwortete das Modell mit drei
    kleinen Blöcken. Angewendet auf das Original gingen so 108 schon passende
    Änderungen still verloren.
    """
    teile = []
    rest = 24000
    for nummer, (alt, neu) in enumerate(offen, 1):
        block = f"Änderung {nummer}:\n<<<<<<< SUCHEN\n{alt}\n=======\n{neu}\n>>>>>>> ERSETZEN"
        if len(block) > rest:
            block = f"Änderung {nummer} (gekürzt): soll ersetzen\n{alt[:1500]}\ndurch\n{neu[:3000]}"
        rest -= len(block)
        teile.append(block)
        if rest <= 0:
            break
    inhalt = (
        f"Aktuelle Datei (alle anderen Änderungen sind bereits eingearbeitet):\n<datei>\n{dokument}\n</datei>\n\n"
        f"Zur Orientierung der Wunsch:\n{wunsch.strip()[:1500]}\n\n"
        "Diese Änderungen ließen sich nicht anwenden, weil ihr SUCHEN-Teil nicht Zeichen für Zeichen in der "
        "Datei vorkommt:\n\n" + "\n\n".join(teile)
        + "\n\nGib NUR für diese Änderungen neue Blöcke aus. Kopiere jeden SUCHEN-Teil exakt aus der aktuellen "
          "Datei. Keine anderen Blöcke, keine ganze Datei."
    )
    return [{"role": "system", "content": AENDERN_SYSTEM}, {"role": "user", "content": inhalt}]


def wunsch_mit_vorbefunden(wunsch: str, vorbefunde: str, versuch: int) -> str:
    """Ein erneuter Versuch kennt den ganzen Auftrag und was bisher nicht klappte."""
    if versuch <= 1:
        return wunsch
    einleitung = f"{wunsch.strip()}\n\nDies ist Versuch {versuch}."
    if not vorbefunde:
        return einleitung
    return (einleitung + " Frühere Versuche sind gescheitert — mach es anders:\n"
            f"{vorbefunde.strip()}")


def stufen_wunsch(gesamt: str, stufe: dict[str, Any], nummer: int, von: int, erledigt: list[str],
                  kriterien: list[dict[str, Any]]) -> str:
    """Der Auftrag für einen Schritt: klein, mit dem Ganzen als Orientierung."""
    zeilen = [
        "GESAMTAUFTRAG — nur zur Orientierung, NICHT alles in diesem Schritt umsetzen:",
        gesamt.strip()[:3000],
        "",
        f"JETZT NUR SCHRITT {nummer} VON {von}: {stufe.get('titel', '')}",
        str(stufe.get("auftrag", "")).strip(),
    ]
    if kriterien:
        zeilen += ["", "Nach diesem Schritt muss im Browser nachweisbar sein:"]
        zeilen += [f"- {k['beschreibung']}" for k in kriterien]
    if erledigt:
        zeilen += ["", "Bereits umgesetzt und geprüft (muss unverändert funktionieren): " + "; ".join(erledigt)]
    zeilen += ["", "Halte die Änderung klein: nur was dieser Schritt braucht, wenige gezielte Änderungsblöcke."]
    return "\n".join(zeilen)


STUFE_KNAPP = (
    "WICHTIG: Der erste Versuch dieses Schritts war zu umfangreich und wurde verworfen. Setze jetzt nur das "
    "Nötigste für genau diesen Schritt um: höchstens 15 kurze Änderungsblöcke, keine ganze Datei, keine "
    "langen Überlegungen, keine Vorarbeit für spätere Schritte."
)
