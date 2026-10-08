# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Skills auf markierten Inhalten: verstehen und in die Form des Skills bringen.

Zwei beobachtete Fehlbilder aus dem Chat:

1. „Erklärung" auf eine markierte HTML-Lernseite kam als leicht umformulierte
   HTML-Seite zurück, „Analyse" als abgeschnittener Seitenkopf. Der Auftrag
   lautete „gib das fertige bearbeitete Ergebnis aus" — bei Code heißt das für
   ein Modell: Code zurückgeben.
2. Jeder Brief war wortgleich eine „Bitte um schriftliche Stellungnahme" mit
   Betreff [Betreff] — auch nach „Brief an Erika Musterfrau, Muster Straße 2".
   glm-5.3-flash antwortete mit {"betreff", "anrede", "text"}; der Brief-Code
   fand keine Absätze und setzte einen eingebauten Ersatzbrief ein.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from app.auswahl import html_auszug, ist_html, markierten_inhalt_aufbereiten
from app.task_skills import (
    brief_aus_text,
    brief_felder_angleichen,
    letter_skill_system_prompt,
    letter_text_system_prompt,
    normalize_letter_artifact,
)

WURZEL = Path(__file__).resolve().parents[1]

SEITE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>KI-Skills – Glas Edition</title>
<style>
.card{background:rgba(255,255,255,.08);backdrop-filter:blur(18px);color:#e8f0ec}
h1{background:linear-gradient(90deg,#7fe8c9,#4fd1c5)}
@keyframes pop{0%{transform:scale(0)}100%{transform:scale(1)}}
@media(max-width:700px){.card{padding:12px}}
</style></head><body>
<header><h1>KI-Skills</h1><p class="sub">Was sie sind – und wie Modelle damit umgehen</p></header>
<section class="card"><h2><span>🧠</span>Was sind KI-Skills?</h2>
<p><b>KI-Skills sind Fähigkeiten</b> eines Modells.</p>
<div class="flow"><div class="step">1. Trainierte Fähigkeiten</div><span class="arrow">＋</span>
<div class="step">2. Anbindbare Tools</div></div>
<ul><li><b>Reasoning</b> – logische Schlussfolgerungen</li><li>RAG – externes Wissen</li></ul>
</section>
<section id="result"><button id="btnRestart">🔁 Erneut versuchen</button></section>
<script>
const QS=[
 {f:"Was sind KI-Skills?",o:["Programmiersprachen","Fähigkeiten eines Modells","Hardware"],a:1},
 {f:"Wofür steht RAG?",o:["Retrieval-Augmented Generation","Random Access Gateway","Rapid AI Growth"],a:0}
];
function build(){document.getElementById('qcontainer').innerHTML='';}
function showResult(){alert('Du brauchst mindestens 12 Punkte.');}
document.getElementById('btnRestart').addEventListener('pointerdown',build);
</script></body></html>"""


def auftrag(inhalt: str) -> str:
    return (
        "Wende die aktiven Skills ausschließlich auf den nachfolgend markierten Inhalt an.\n\n"
        "--- START MARKIERTER INHALT (KI-Ausgabe) ---\n"
        + inhalt
        + "\n--- ENDE MARKIERTER INHALT ---"
    )


class HtmlAuszugTests(unittest.TestCase):
    """Was eine Seite zeigt und tut — ohne Code, von oben nach unten."""

    def setUp(self) -> None:
        self.auszug = html_auszug(SEITE)

    def test_the_title_and_headings_keep_their_order(self):
        import re

        self.assertIn("„KI-Skills – Glas Edition“", self.auszug)
        # Das Symbol gehört zur sichtbaren Überschrift und bleibt — mit Abstand.
        zweite = re.search(r"^## 🧠 Was sind KI-Skills\?$", self.auszug, re.M)
        self.assertIsNotNone(zweite, self.auszug)
        self.assertLess(self.auszug.index("# KI-Skills"), zweite.start())

    def test_paragraphs_lists_and_buttons_are_kept(self):
        self.assertIn("KI-Skills sind Fähigkeiten eines Modells.", self.auszug)
        self.assertIn("- Reasoning – logische Schlussfolgerungen", self.auszug)
        self.assertIn("[Schaltfläche: 🔁 Erneut versuchen]", self.auszug)

    def test_quiz_data_comes_out_with_the_right_answer(self):
        self.assertIn("DATEN IM SKRIPT (2 Einträge)", self.auszug)
        self.assertIn("Wofür steht RAG?", self.auszug)
        self.assertIn("(richtig: Retrieval-Augmented Generation)", self.auszug)
        self.assertIn("(richtig: Fähigkeiten eines Modells)", self.auszug)

    def test_design_and_behaviour_are_described_not_copied(self):
        self.assertIn("Glas-Effekt", self.auszug)
        self.assertIn("Animationen: pop", self.auszug)
        self.assertIn("Skriptfunktionen: build, showResult", self.auszug)
        self.assertIn("Reagiert auf: pointerdown", self.auszug)

    def test_no_code_survives(self):
        for rest in ("<div", "<style", "<script", "backdrop-filter:", "function build", "{f:"):
            self.assertNotIn(rest, self.auszug, rest)

    def test_symbol_only_lines_are_dropped(self):
        self.assertNotIn("\n＋\n", "\n" + self.auszug + "\n")

    def test_html_is_recognised_with_or_without_doctype(self):
        self.assertTrue(ist_html(SEITE))
        self.assertTrue(ist_html("<div><p>a</p><p>b</p><p>c</p><p>d</p><p>e</p><p>f</p></div>"))
        self.assertFalse(ist_html("Ein ganz normaler Satz über <b>fett</b> Gedrucktes."))


class AufbereitungTests(unittest.TestCase):
    """Nur der markierte Block wird aufbereitet — und nur, wenn es sinnvoll ist."""

    def test_a_fenced_html_page_becomes_its_content(self):
        nachricht = "Hier die Seite:\n```html\n" + SEITE + "\n```\nViel Spaß!"
        neu, hinweis = markierten_inhalt_aufbereiten(auftrag(nachricht), ["letter"])
        self.assertIn("INHALT DER SEITE", neu)
        self.assertIn("Hier die Seite:", neu)
        self.assertIn("Viel Spaß!", neu)
        self.assertNotIn("<style", neu)
        self.assertIn("Gib keinen HTML-", hinweis)

    def test_raw_html_without_a_fence_is_recognised(self):
        neu, hinweis = markierten_inhalt_aufbereiten(auftrag(SEITE), ["explanation"])
        self.assertIn("INHALT DER SEITE", neu)
        self.assertTrue(hinweis)

    def test_the_instruction_outside_the_block_stays(self):
        neu, _ = markierten_inhalt_aufbereiten(auftrag(SEITE), ["report"])
        self.assertTrue(neu.startswith("Wende die aktiven Skills"))
        self.assertTrue(neu.endswith("--- ENDE MARKIERTER INHALT ---"))

    def test_a_translation_keeps_the_code(self):
        original = auftrag(SEITE)
        neu, hinweis = markierten_inhalt_aufbereiten(original, ["translation"])
        self.assertEqual(neu, original)
        self.assertEqual(hinweis, "")

    def test_prose_stays_untouched(self):
        original = auftrag("Ein Skill ist eine abgegrenzte, wiederverwendbare Fähigkeit.")
        neu, hinweis = markierten_inhalt_aufbereiten(original, ["letter"])
        self.assertEqual(neu, original)
        self.assertEqual(hinweis, "")

    def test_other_code_is_kept_but_must_not_be_echoed(self):
        code = "```python\ndef a():\n    return 1\n\ndef b():\n    return 2\n```"
        neu, hinweis = markierten_inhalt_aufbereiten(auftrag(code), ["explanation"])
        self.assertIn("def a():", neu)
        self.assertIn("python", hinweis)
        self.assertIn("nicht unverändert", hinweis)

    def test_without_a_marked_block_nothing_happens(self):
        neu, hinweis = markierten_inhalt_aufbereiten("Schreib mir einen Brief.", ["letter"])
        self.assertEqual(neu, "Schreib mir einen Brief.")
        self.assertEqual(hinweis, "")


class BrieffelderTests(unittest.TestCase):
    """Fremde Feldnamen dürfen einen Brief nicht in einen Ersatzbrief verwandeln."""

    def test_the_observed_german_answer_is_understood(self):
        """Wörtlich die Antwortform von glm-5.3-flash, die jeden Brief zerstörte."""
        roh = {
            "betreff": "Erläuterung: KI-Skills",
            "anrede": "Sehr geehrter Herr Musterfrau,",
            "text": "ein Skill ist eine Fähigkeit.\n\nTechnisch meist Tool Calling.",
        }
        brief = normalize_letter_artifact(roh, {}, False, "11.09.2026", "Brief über KI-Skills")
        self.assertEqual(brief["subject"], "Erläuterung: KI-Skills")
        self.assertEqual(brief["salutation"], "Sehr geehrter Herr Musterfrau,")
        self.assertEqual(len(brief["paragraphs"]), 2)

    def test_the_fenced_json_string_is_understood_too(self):
        roh = '```json\n{"betreff": "Thema", "text": "Erster Absatz."}\n```'
        brief = normalize_letter_artifact(roh, {}, False, "11.09.2026", "")
        self.assertEqual(brief["subject"], "Thema")
        self.assertEqual(brief["paragraphs"], ["Erster Absatz."])

    def test_no_invented_statement_letter_ever(self):
        brief = normalize_letter_artifact({}, {}, False, "11.09.2026", "Brief über KI-Skills")
        self.assertEqual(brief["paragraphs"], [])
        self.assertNotIn("Stellungnahme", " ".join(brief["paragraphs"]))

    def test_a_recipient_written_as_one_line_is_split(self):
        roh = brief_felder_angleichen(
            {"empfänger": "Erika Musterfrau, Muster Straße 2, 12345 Musterstadt", "text": "Hallo."}
        )
        self.assertEqual(roh["recipient"]["name"], "Erika Musterfrau")
        self.assertEqual(roh["recipient"]["street"], "Muster Straße 2")
        self.assertEqual(roh["recipient"]["postal_code"], "12345")
        self.assertEqual(roh["recipient"]["city"], "Musterstadt")

    def test_german_recipient_keys_are_mapped(self):
        roh = brief_felder_angleichen(
            {"empfaenger": {"name": "Musterfrau", "strasse": "Muster Straße 2", "plz": "12345", "ort": "Musterstadt"}}
        )
        self.assertEqual(roh["recipient"]["street"], "Muster Straße 2")
        self.assertEqual(roh["recipient"]["city"], "Musterstadt")

    def test_salutation_and_closing_leave_the_body(self):
        roh = brief_felder_angleichen({"text": (
            "Sehr geehrte Damen und Herren,\n\nErster Absatz.\n\nZweiter Absatz.\n\n"
            "Mit freundlichen Grüßen\n\nMax Mustermann"
        )})
        self.assertEqual(roh["paragraphs"], ["Erster Absatz.", "Zweiter Absatz."])
        self.assertEqual(roh["salutation"], "Sehr geehrte Damen und Herren,")

    def test_bullets_become_separate_paragraphs(self):
        roh = brief_felder_angleichen({"text": "Umsetzung:\n* Tool Calling\n* RAG-Anbindung"})
        self.assertEqual(roh["paragraphs"], ["Umsetzung:", "– Tool Calling", "– RAG-Anbindung"])

    def test_a_wrapped_letter_is_unwrapped(self):
        roh = brief_felder_angleichen({"brief": {"betreff": "Thema", "absätze": ["Eins.", "Zwei."]}})
        self.assertEqual(roh["subject"], "Thema")
        self.assertEqual(roh["paragraphs"], ["Eins.", "Zwei."])


class BriefAusTextTests(unittest.TestCase):
    """Der zweite Weg: ein als Text geschriebener Brief wird eingelesen."""

    TEXT = (
        "Empfänger: Erika Musterfrau, Muster Straße 2, 12345 Musterstadt\n\n"
        "Betreff: Erläuterung: KI-Skills\n\n"
        "Sehr geehrter Herr Musterfrau,\n\n"
        "gerne erkläre ich Ihnen, was KI-Skills sind.\n\n"
        "Technisch werden sie so umgesetzt:\n- Tool Calling\n- RAG\n\n"
        "Mit freundlichen Grüßen\n\nMax Mustermann"
    )

    def test_all_parts_are_found(self):
        brief = brief_aus_text(self.TEXT)
        self.assertEqual(brief["subject"], "Erläuterung: KI-Skills")
        self.assertEqual(brief["salutation"], "Sehr geehrter Herr Musterfrau,")
        self.assertEqual(brief["recipient"]["name"], "Erika Musterfrau")
        self.assertEqual(brief["recipient"]["city"], "Musterstadt")
        self.assertEqual(brief["paragraphs"][0], "gerne erkläre ich Ihnen, was KI-Skills sind.")
        self.assertIn("– Tool Calling", brief["paragraphs"])
        self.assertNotIn("Max Mustermann", brief["paragraphs"])

    def test_nothing_usable_gives_nothing(self):
        self.assertEqual(brief_aus_text("")["paragraphs"], [])


class BriefAuftragTests(unittest.TestCase):
    """Die Anweisung an das Modell selbst."""

    def test_the_english_keys_are_named_explicitly(self):
        prompt = letter_skill_system_prompt({}, False, "11.09.2026")
        for schluessel in ("recipient", "subject", "salutation", "paragraphs", "closing"):
            self.assertIn(schluessel, prompt)
        self.assertIn("englischen Schlüsseln", prompt)

    def test_the_marked_content_is_the_letters_subject_matter(self):
        prompt = letter_skill_system_prompt({}, False, "11.09.2026")
        self.assertIn("ist er der Stoff des Briefs", prompt)
        self.assertIn("Der Betreff benennt das Thema", prompt)

    def test_the_text_route_asks_for_a_plain_letter(self):
        prompt = letter_text_system_prompt("11.09.2026")
        self.assertIn("kein JSON", prompt)
        self.assertIn("Betreff:", prompt)
        self.assertIn("11.09.2026", prompt)


class VerdrahtungTests(unittest.TestCase):
    """Die Bausteine müssen im Chat-Endpunkt und in der Oberfläche ankommen."""

    def test_the_endpoint_prepares_marked_code(self):
        quelltext = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertRegex(quelltext, r"from app\.auswahl import [^\n]*markierten_inhalt_aufbereiten")
        self.assertIn("prompt, auswahl_hinweis = markierten_inhalt_aufbereiten(prompt, selected_skills)",
                      quelltext)
        self.assertIn('messages.insert(0, {"role": "system", "content": auswahl_hinweis})', quelltext)

    def test_switches_read_the_instruction_not_the_marked_content(self):
        quelltext = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("anweisung = auftragstext(prompt) if skill_action else prompt", quelltext)
        self.assertIn(
            "if not skill_action and (is_html_artifact_request(prompt) or html_ueberarbeitung):",
            quelltext,
        )
        self.assertIn("is_email_draft_request(anweisung)", quelltext)
        self.assertIn("resolve_task_skill(\n            anweisung,", quelltext)

    def test_the_letter_has_a_second_route_and_an_honest_error(self):
        quelltext = (WURZEL / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("letter_text_system_prompt(current_date_label())", quelltext)
        self.assertIn("brief_aus_text(brieftext)", quelltext)
        self.assertIn("keinen verwertbaren Brieftext geliefert", quelltext)

    def test_the_frontend_no_longer_asks_for_an_edited_result(self):
        javascript = (WURZEL / "static/app.js").read_text(encoding="utf-8")
        self.assertNotIn('"Gib nur das fertige bearbeitete Ergebnis aus', javascript)
        self.assertIn("in der Form der aktiven Skills", javascript)
        self.assertIn("app.js?v=65", (WURZEL / "static/index.html").read_text(encoding="utf-8"))


# Eine Programmseite nach dem Muster des Dienstplan-Generators: Das Wesentliche
# steckt im Skript — Mitarbeitende, Regeln, Gewichtung.
PROGRAMM = """<!DOCTYPE html>
<html lang="de"><head><title>Dienstplan-Generator</title><style>
.grid{display:grid;grid-template-columns:340px 1fr;gap:14px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
body{background:#0f1419;color:#e6edf3}
</style></head><body><h1>Dienstplan-Generator</h1>
<button id="btnGen">Plan generieren</button><button id="btnFix">Konflikte lösen</button>
<table id="plan"></table><ul id="issues"></ul>
<script>
"use strict";
// ---------- Datenmodell ----------
const GROUPS = ["WG 1","WG 2","WG 3"];
let staff = [
  {n:"Müller",   fk:true,  wg:0, pct:100, soll:40, plus:12},
  {n:"Schmidt",  fk:true,  wg:0, pct:100, soll:40, plus:30},
  {n:"Weber",    fk:true,  wg:1, pct:80,  soll:32, plus:5},
  {n:"Schulz",   fk:false, wg:0, pct:100, soll:40, plus:10},
  {n:"Koch",     fk:false, wg:1, pct:75,  soll:30, plus:0}
];
let plan = null, sick = new Set();
/* Ziel: 7 Tage, je WG Früh+Spät+Nacht. Allein arbeiten dürfen nur Fachkräfte. */
function isSick(d, i){ return sick.has(d + "|" + i); }
function assigned(d, i){
  if (!plan) return null;
  for (let g = 0; g < 3; g++) { for (const e of plan[d][g]) if (e.s === i) return {g, sh: e.sh}; }
  return null;
}
function score(c, slot, load){
  let s = 0;
  s += (c.p.wg === slot.g ? 0 : 100);          // Heimat-WG bevorzugt
  s += load[c.i] * 3;                             // Stundenlast ausgleichen
  s += c.p.plus * 0.5;                            // Überstunden abbauen
  if (slot.sh === "N" && !c.p.fk) s += 50;        // Nacht: Fachkraft bevorzugt
  return s;
}
function generate(){
  plan = Array.from({length: 7}, () => Array.from({length: 3}, () => []));
  const load = staff.map(() => 0);
  for (let d = 0; d < 7; d++) for (let g = 0; g < 3; g++) for (const sh of ["N", "F", "S"]) {
    const cands = staff.map((p, i) => ({p, i})).filter(c => !isSick(d, c.i) && !assigned(d, c.i));
    if (!cands.length) continue;
    cands.sort((a, b) => score(a, {d, g, sh}, load) - score(b, {d, g, sh}, load));
    plan[d][g].push({s: cands[0].i, sh});
    load[cands[0].i] += 8;
  }
  renderPlan(); validate();
}
function validate(){
  const list = document.getElementById("issues");
  list.innerHTML = "";
  for (let d = 0; d < 7; d++) for (let g = 0; g < 3; g++) {
    const active = plan[d][g].filter(e => !isSick(d, e.s));
    if (!active.some(e => staff[e.s].fk)) {
      const li = document.createElement("li");
      li.textContent = "Tag " + (d + 1) + " · " + GROUPS[g] + ": keine Fachkraft vertreten";
      list.appendChild(li);
    }
  }
}
function renderPlan(){
  document.getElementById("plan").innerHTML = "<tr><th>Mitarbeiter</th></tr>"
    + staff.map(p => `<tr><td>${p.n}</td></tr>`).join("");
}
document.getElementById("btnGen").addEventListener("pointerdown", generate);
</script></body></html>"""


class ProgrammseitenTests(unittest.TestCase):
    """Beim Dienstplan steckt das Wesentliche im Skript — es muss mit."""

    def setUp(self) -> None:
        self.auszug = html_auszug(PROGRAMM)

    def test_data_arrays_become_tables_with_counts(self):
        self.assertIn("DATEN IM SKRIPT – staff (5 Einträge)", self.auszug)
        self.assertIn("1. n: Müller · fk: true · wg: 0", self.auszug)
        self.assertIn("fk: true ×3, false ×2", self.auszug)
        self.assertIn("DATEN IM SKRIPT – GROUPS: WG 1 | WG 2 | WG 3", self.auszug)

    def test_the_authors_comments_carry_the_rules(self):
        self.assertIn("Allein arbeiten dürfen nur Fachkräfte", self.auszug)
        self.assertIn("- Heimat-WG bevorzugt", self.auszug)
        self.assertIn("- Datenmodell", self.auszug)

    def test_the_logic_comes_without_markup_styles_or_data(self):
        self.assertIn("PROGRAMMLOGIK", self.auszug)
        logik = self.auszug.split("PROGRAMMLOGIK", 1)[1]
        self.assertIn("function score", logik)
        self.assertIn("100", logik)
        for rest in ("<tr>", "<td>", "grid-template-columns:", '{n:"Müller"', "<style"):
            self.assertNotIn(rest, self.auszug, rest)

    def test_layout_facts_are_described(self):
        self.assertIn("Umbruch für schmale Bildschirme bei: 900 px", self.auszug)
        self.assertIn("Raster (Spalten): 340px 1fr", self.auszug)

    def test_directives_are_not_texts(self):
        self.assertNotIn("- use strict", self.auszug)

    def test_a_small_script_gets_no_logic_section(self):
        self.assertNotIn("PROGRAMMLOGIK", html_auszug(SEITE))


class WeichenTests(unittest.TestCase):
    """Weichen lesen den Auftrag, nicht den markierten Inhalt."""

    def test_the_marked_page_itself_looked_like_an_html_request(self):
        from app.auswahl import auftragstext
        from app.main import is_html_artifact_request

        skill_auftrag = auftrag("```html\n" + PROGRAMM + "\n```")
        # So kam es zur Fehlweiche: „HTML" und „generieren" standen im Inhalt.
        self.assertTrue(is_html_artifact_request(skill_auftrag))
        self.assertFalse(is_html_artifact_request(auftragstext(skill_auftrag)))

    def test_the_instruction_stays_without_the_block(self):
        from app.auswahl import auftragstext

        text = auftragstext(auftrag("Inhalt"))
        self.assertTrue(text.startswith("Wende die aktiven Skills"))
        self.assertNotIn("MARKIERTER", text)

    def test_code_at_the_start_is_an_echo(self):
        from app.auswahl import ist_codeecho

        self.assertTrue(ist_codeecho("```html\n<!DOCTYPE html>\n<html>"))
        self.assertTrue(ist_codeecho("Hier das Protokoll:\n\n```html\n<!doctype html>"))
        self.assertTrue(ist_codeecho("<!DOCTYPE html><html>"))
        self.assertFalse(ist_codeecho("# Protokoll: Dienstplan-Generator\n\n| Aufgabe | Frist |"))
        self.assertFalse(ist_codeecho("Die Seite nutzt `<button>`-Elemente für die Bedienung."))


class UeberarbeitungTests(unittest.TestCase):
    """Folgewünsche an eine HTML-Seite verlangen die ganze überarbeitete Seite."""

    VERLAUF = [
        {"role": "user", "content": "Baue eine Arztsuche als HTML"},
        {"role": "assistant", "content": "```html\n<!DOCTYPE html><html></html>\n```"},
    ]

    def test_the_observed_follow_ups_are_revisions(self):
        from app.main import is_html_revision_request

        for bitte in (
            "ok übertrage das nun aus deiner ersten html Version und mach nun die Buttons lebendig",
            "sehr gut bau das in die vorhandene html ein. und gebe die gesamte samt Änderung ein.",
            "nimm das: anlage 1 und Anlage 2 zusammen. optisch wie anläge 2",
        ):
            self.assertTrue(is_html_revision_request(bitte, self.VERLAUF), bitte)

    def test_a_question_is_not_a_revision(self):
        from app.main import is_html_revision_request

        self.assertFalse(is_html_revision_request(
            "warum ändert sich die Farbe beim Klick?", self.VERLAUF,
        ))

    def test_without_a_page_nothing_is_forced(self):
        from app.main import is_html_revision_request

        self.assertFalse(is_html_revision_request(
            "ergänze bitte noch einen Absatz", [{"role": "assistant", "content": "Ein Text."}],
        ))


if __name__ == "__main__":
    unittest.main()
