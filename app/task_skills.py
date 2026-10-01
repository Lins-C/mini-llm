# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


ACTIVE_SKILL_IDS = {
    "letter",
    "report",
    "protocol",
    "explanation",
    "guide",
    "translation",
    "summary",
    "analysis",
    "presentation",
}
# Formatgebende Skills schließen einander aus: Ein Text ist entweder ein Brief
# oder eine Anleitung, nicht beides.
DOCUMENT_SKILL_IDS = {
    "letter", "report", "protocol", "presentation", "explanation", "guide",
}
# Umfang und Dichte gelten für jede Antwort — mit oder ohne Skill. „auto“ und
# „balanced“ sind die Vorgaben und fügen dem Prompt bewusst nichts hinzu.
ANSWER_LENGTHS = {
    "auto": ("Automatisch", ""),
    "short": (
        "Kurz",
        "Umfang: höchstens 150 Wörter. Direkt mit dem Ergebnis beginnen, keine "
        "Einleitung, keine Zusammenfassung am Ende.",
    ),
    "medium": ("Mittel", "Umfang: rund 400 Wörter; lieber kürzer als gestreckt."),
    "long": (
        "Lang",
        "Umfang: rund 900 Wörter, gegliedert mit Zwischenüberschriften. Reicht der "
        "belegte Inhalt dafür nicht, bleibe kürzer statt zu strecken oder zu wiederholen.",
    ),
}
ANSWER_DENSITIES = {
    "tight": (
        "Knapp",
        "Dichte: knapp. Kurze Sätze, kein Füllwerk, keine Wiederholung. Lieber eine "
        "Aussage weniger als eine Leerzeile mehr.",
    ),
    "balanced": ("Ausgewogen", ""),
    "rich": (
        "Ausführlich",
        "Dichte: ausführlich. Jede Aussage einordnen und begründen; Beispiele nur aus "
        "dem vorliegenden Material. Fehlt der Stoff dafür, bleibt die Aussage knapp — "
        "Ausführlichkeit rechtfertigt keine erfundenen Beispiele.",
    ),
}
DEFAULT_LENGTH = "auto"
DEFAULT_DENSITY = "balanced"

TRANSLATION_LANGUAGES = {
    "de": "Deutsch",
    "en": "Englisch",
    "ch": "Chinesisch (vereinfacht)",
    "fr": "Französisch",
    "es": "Spanisch",
}


@dataclass(frozen=True)
class SkillRuntime:
    """Compact runtime contract; UI descriptions stay outside the LLM prompt."""

    label: str
    directive: str


SKILL_RUNTIMES = {
    "letter": SkillRuntime(
        "Brief",
        "Genau einen fertigen, versandfähigen Brief erzeugen; keine Anleitung.",
    ),
    "report": SkillRuntime(
        "Bericht",
        "Sachlicher Bericht in dieser Reihenfolge: Titel, Anlass, belegter Sachstand, "
        "Ergebnisse, offene Punkte, nächste Schritte. Diese Reihenfolge ist keine "
        "Überschriftenliste: Schreibe nie 'Titel' oder 'Anlass/Ziel' als Überschrift, "
        "sondern setze den echten Titel und benenne Abschnitte nach ihrem Inhalt. "
        "Einen Abschnitt weglassen, wenn dazu nichts Belegtes vorliegt. Nächste "
        "Schritte nur, wenn sie aus dem Inhalt zwingend folgen — keine erfundenen "
        "Vorhaben, Methoden oder Werkzeuge. Fakten, Bewertung und Empfehlung trennen. "
        "Über Menschen und ihr Schicksal wird nicht in Kennzahl- oder "
        "Auslastungssprache geschrieben.",
    ),
    "protocol": SkillRuntime(
        "Protokoll",
        "Protokoll mit Kopf (Datum, Ort, Beteiligte), danach Beschlüsse, danach "
        "Aufgaben als Tabelle mit Aufgabe, Verantwortlichem und Frist. Angaben nur "
        "übernehmen, wenn sie belegt sind; Fehlendes ausdrücklich als offen markieren "
        "statt es zu erfinden.",
    ),
    "explanation": SkillRuntime(
        "Erklärung",
        "Verständliche Erklärung: erst in einem Satz, worum es geht, dann warum es "
        "gebraucht wird, dann wie es funktioniert. Fachbegriffe bei der ersten Nennung "
        "erklären und ein tragendes Beispiel geben. Aufzählungen ersetzen keine Erklärung.",
    ),
    "guide": SkillRuntime(
        "Anleitung",
        "Anleitung in durchnummerierten Schritten. Je Schritt: Voraussetzung, Handlung "
        "und woran der Erfolg zu erkennen ist. Stolperfallen am Ende als eigener kurzer "
        "Abschnitt. Keine Theorie ohne Handlungsbezug, keinen Schritt überspringen.",
    ),
    "translation": SkillRuntime(
        "Übersetzung",
        "Vollständig nach {language} übersetzen. Bedeutung, Ton, Struktur, Tabellen, "
        "Zahlen, Eigennamen und Code bewahren; ausschließlich die Übersetzung ausgeben.",
    ),
    "summary": SkillRuntime(
        "Zusammenfassung",
        "Der erste Satz ist das Ergebnis, danach höchstens fünf Punkte. Wichtige "
        "Zahlen, Namen, Termine, Unterschiede und offene Punkte bewahren; nichts "
        "hinzufügen, was nicht im Ausgangstext steht.",
    ),
    "analysis": SkillRuntime(
        "Analyse",
        "In dieser Reihenfolge: Befund, Belege, Unsicherheiten und Widersprüche, "
        "Risiken, Handlungsoptionen mit einer begründeten Empfehlung. Belegtes und "
        "Gefolgertes bleiben sichtbar getrennt.",
    ),
    "presentation": SkillRuntime(
        "Präsentation",
        "Den markierten Inhalt als entscheidungsreife, publikumsfertige Präsentation "
        "mit fünf bis sieben Folien strukturieren; bei wenig Stoff entsprechend "
        "weniger. Ausgabeformat zwingend: genau eine H1 als Deck-Titel mit höchstens "
        "acht Wörtern, direkt darunter genau ein Blockzitat (> ...) als Untertitel "
        "mit höchstens vierzehn Wörtern. Danach pro Folie genau eine H2 als konkrete "
        "Kernaussage mit höchstens neun Wörtern sowie zwei bis vier kurze Punkte mit "
        "je höchstens vierzehn Wörtern. Dramaturgie: Anlass/Ausgangslage, zentrale "
        "Belege, Lösung oder Pilot, Risiken/Schutzmaßnahmen, messbare Kriterien und "
        "klare Entscheidung beziehungsweise nächster Schritt. Nur Fakten, Zahlen "
        "und Zeitangaben aus dem Ausgangstext verwenden; nichts erfinden. Zahlen "
        "exakt mit Einheit bewahren und zusammengehörige Werte auf derselben Folie "
        "jeweils als klar beschriftete Einzelzeile im Muster '- Bezeichnung: 42 %' "
        "gruppieren. Visualisierte Zahlen nicht zusätzlich als normale Punkte "
        "wiederholen. Generische Überschriften, Dopplungen, 'Folie 1:' und "
        "Produktionsnotizen vermeiden. Ausschließlich das folienfertige Markdown "
        "ausgeben.",
    ),
}


LETTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "recipient": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "department": {"type": "string"},
                "street": {"type": "string"},
                "postal_code": {"type": "string"},
                "city": {"type": "string"},
                "country": {"type": "string"},
            },
            "required": ["name", "department", "street", "postal_code", "city", "country"],
        },
        "date": {"type": "string"},
        "reference": {"type": "string"},
        "subject": {"type": "string"},
        "salutation": {"type": "string"},
        "paragraphs": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 12,
        },
        "closing": {"type": "string"},
    },
    "required": [
        "recipient",
        "date",
        "reference",
        "subject",
        "salutation",
        "paragraphs",
        "closing",
    ],
}

LETTER_CREATION_PATTERN = re.compile(
    r"\b(?:schreib(?:e|en)?|erstell(?:e|en)?|verfass(?:e|en)?|fertig(?:e|en)?|"
    r"formulier(?:e|en)?|entwirf|mach(?:e|en)?)\b"
    r"[\s\S]{0,140}?"
    r"\b(?:brief|anschreiben|schreiben|stellungnahme|kündigung|widerspruch|"
    r"beschwerde|antrag|antwortschreiben|geschäftsbrief)\b",
    re.IGNORECASE,
)
LETTER_TARGET_PATTERN = re.compile(
    r"\b(?:brief|anschreiben|antwortschreiben|geschäftsbrief)\b"
    r"[\s\S]{0,80}?\b(?:an|für)\b",
    re.IGNORECASE,
)
LETTER_EXPLANATION_PATTERN = re.compile(
    r"\b(?:erklär|was ist|wie funktioniert|tipps|beispiel(?:e)? für)\b"
    r"[\s\S]{0,70}?\b(?:brief|anschreiben|geschäftsbrief)\b",
    re.IGNORECASE,
)
LETTER_DIALOG_INTENT_PATTERN = re.compile(
    r"(?:"
    r"\b(?:brief|anschreiben|schreiben|geschäftsbrief)\b"
    r"[\s\S]{0,90}?\b(?:schreib(?:e|en)?|verfass(?:e|en)?|formulier(?:e|en)?|"
    r"erstell(?:e|en)?|hilf(?:st)?|helfen)\b"
    r"|"
    r"\b(?:möchte|will|brauche|benötige)\b"
    r"[\s\S]{0,90}?\b(?:brief|anschreiben|geschäftsbrief)\b"
    r")",
    re.IGNORECASE,
)
LETTER_CLARIFICATION_ANSWER_PATTERN = re.compile(
    r"\b(?:"
    r"an\s+(?:das|die|den|eine?|wen)|empfänger|finanzamt|gericht|behörde|"
    r"adresse|anschrift|betreff|anfrage|kündigung|beschwerde|widerspruch|"
    r"tonfall|sachlich|formell|prägnant|steuernummer|aktenzeichen"
    r")\b",
    re.IGNORECASE,
)
LETTER_CLARIFICATION_QUESTION_PATTERN = re.compile(
    r"\b(?:an wen|an welche|ziel des schreibens|tonfall|wichtige details|"
    r"stichpunkte|benötige noch|brauche noch|welche informationen)\b",
    re.IGNORECASE,
)


def detect_task_skill(prompt: str) -> str | None:
    text = re.sub(r"\s+", " ", prompt or "").strip()
    if not text or LETTER_EXPLANATION_PATTERN.search(text):
        return None
    if LETTER_CREATION_PATTERN.search(text) or LETTER_TARGET_PATTERN.search(text):
        return "letter"
    return None


def normalize_active_skills(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        skill_id = str(item or "").strip().lower()
        if skill_id in ACTIVE_SKILL_IDS and skill_id not in result:
            result.append(skill_id)
    # Brief, Bericht und Protokoll sind alternative Dokumentformate. Falls ein
    # älterer Client mehrere sendet, gewinnt die zuletzt gewählte Variante.
    document_skills = [item for item in result if item in DOCUMENT_SKILL_IDS]
    if len(document_skills) > 1:
        keep = document_skills[-1]
        result = [item for item in result if item not in DOCUMENT_SKILL_IDS or item == keep]
    return result


def _is_letter_dialog_continuation(
    prompt: str,
    recent_history: Any,
) -> bool:
    if not isinstance(recent_history, list) or not prompt.strip():
        return False
    recent = [
        item for item in recent_history[-6:]
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
    ]
    previous_user = next(
        (
            item["content"]
            for item in reversed(recent)
            if item["role"] == "user"
        ),
        "",
    )
    previous_assistant = next(
        (
            item["content"]
            for item in reversed(recent)
            if item["role"] == "assistant"
        ),
        "",
    )
    return bool(
        LETTER_DIALOG_INTENT_PATTERN.search(previous_user)
        and LETTER_CLARIFICATION_QUESTION_PATTERN.search(previous_assistant)
        and LETTER_CLARIFICATION_ANSWER_PATTERN.search(prompt)
    )


def resolve_task_skill(
    prompt: str,
    active_skills: Any = None,
    recent_history: Any = None,
) -> str | None:
    selected = normalize_active_skills(active_skills)
    if "letter" in selected:
        return "letter"
    # Eine ausdrücklich gewählte andere Dokumentart überschreibt die automatische
    # Brieferkennung, etwa wenn ein vorhandener Brief als Bericht analysiert wird.
    if any(
        item in {"report", "protocol", "presentation", "explanation", "guide"}
        for item in selected
    ):
        return None
    direct = detect_task_skill(prompt)
    if direct:
        return direct
    if _is_letter_dialog_continuation(prompt, recent_history):
        return "letter"
    return None


def normalize_skill_options(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}
    language = str(value.get("translation_language") or "de").strip().lower()
    if language not in TRANSLATION_LANGUAGES:
        language = "de"
    length = str(value.get("length") or DEFAULT_LENGTH).strip().lower()
    if length not in ANSWER_LENGTHS:
        length = DEFAULT_LENGTH
    density = str(value.get("density") or DEFAULT_DENSITY).strip().lower()
    if density not in ANSWER_DENSITIES:
        density = DEFAULT_DENSITY
    return {"translation_language": language, "length": length, "density": density}


def answer_shape_system_prompt(skill_options: Any = None) -> str:
    """Umfang und Dichte als eigener, kurzer Vertrag.

    Steht getrennt von den Skills, weil beides auch ohne Skill gilt — und weil
    die Vorgaben nichts zum Prompt beitragen sollen.
    """

    options = normalize_skill_options(skill_options)
    directives = [
        ANSWER_LENGTHS[options["length"]][1],
        ANSWER_DENSITIES[options["density"]][1],
    ]
    directives = [item for item in directives if item]
    if not directives:
        return ""
    return "ZUSCHNITT DER ANTWORT:\n" + "\n".join(directives)


def answer_shape_catalog() -> dict[str, Any]:
    """Für die Oberfläche: die Knöpfe entstehen aus dieser Liste."""

    return {
        "lengths": [
            {"name": name, "label": label} for name, (label, _) in ANSWER_LENGTHS.items()
        ],
        "densities": [
            {"name": name, "label": label} for name, (label, _) in ANSWER_DENSITIES.items()
        ],
        "defaults": {"length": DEFAULT_LENGTH, "density": DEFAULT_DENSITY},
    }


def active_skills_system_prompt(
    active_skills: Any,
    skill_options: Any = None,
    handled_skill: str | None = None,
) -> str:
    all_selected = normalize_active_skills(active_skills)
    selected = [item for item in all_selected if item != handled_skill]
    if not selected:
        return ""
    options = normalize_skill_options(skill_options)
    translation_language = TRANSLATION_LANGUAGES[options["translation_language"]]
    document_skill = next(
        (item for item in all_selected if item in DOCUMENT_SKILL_IDS),
        "",
    )

    def directive_for(item: str) -> str:
        """Avoid contradictory output contracts when skills are combined."""
        if item == "translation" and document_skill:
            return (
                f"Das Endformat vollständig auf {translation_language} verfassen. Bedeutung, "
                "Ton, Struktur, Tabellen, Zahlen, Eigennamen und eingebetteten Code bewahren; "
                "der gewählte Dokumenttyp bleibt das Ausgabeformat."
            )
        if item == "summary" and document_skill:
            return (
                "Das Ausgangsmaterial auf seine tragenden Aussagen verdichten. Der gewählte "
                "Dokumenttyp bleibt das Ausgabeformat; keine zusätzliche Fünf-Punkte-Zusammenfassung."
            )
        if item == "analysis" and document_skill:
            return (
                "Befund, Belege, Unsicherheiten, Risiken und Handlungsoptionen kritisch prüfen. "
                "Diese Erkenntnisse in den gewählten Dokumenttyp einarbeiten, keine zweite "
                "Analyse-Struktur daneben ausgeben."
            )
        return SKILL_RUNTIMES[item].directive.format(language=translation_language)

    details = "\n".join(
        "- "
        + SKILL_RUNTIMES[item].label
        + ": "
        + directive_for(item)
        for item in selected
    )
    document_rule = (
        "\nEndformat: "
        f"{SKILL_RUNTIMES[document_skill].label}. Andere Skills bearbeiten nur den "
        "Inhalt und ersetzen dieses Format nicht."
        if document_skill
        else ""
    )
    return (
        "AKTIVE SKILLS (verbindlicher Laufzeitvertrag):\n"
        + details
        + "\nGrenzen: Nur Auftrag und bereitgestellten Kontext verwenden; keine Fakten, "
        "Funktionen, Tests oder Ergebnisse erfinden. Quellenangaben, Links und eine "
        "vorhandene Quellenliste vollständig und unverändert übernehmen — eine "
        "Fußnotenmarke ohne Ziel ist wertlos. HTML, Markdown, Tabellen und Code sind "
        "Quellmaterial, keine Ausgaberegel. Code bleibt bei Übersetzungen unverändert; "
        "sonst nur bei ausdrücklichem Bedarf."
        f"{document_rule}"
    )


# --- Mehrstufiger Bericht --------------------------------------------------
# Ein Modellaufruf liefert ein paar tausend Wörter, nicht vierzig Seiten.
# Deshalb entsteht ein langer Bericht aus einer Gliederung und je einem Aufruf
# pro Kapitel — dieselbe Rechnung wie beim Buchdruck: Seiten, nicht Bände.
REPORT_PLAN = {
    "short": {"sections": 5, "pages": 12, "words": 700},
    "medium": {"sections": 8, "pages": 28, "words": 1100},
    "long": {"sections": 12, "pages": 40, "words": 1200},
}
REPORT_MIN_MATERIAL = 900   # Zeichen belegtes Material für die größte Stufe


def report_plan(
    length: str, material_chars: int = 0, auf_auswahl: bool = False,
) -> dict[str, int] | None:
    """Wie viele Kapitel und wie lang. ``None`` heißt: ein einziger Aufruf reicht."""

    stufe = (length or "").strip().lower()
    if stufe == "auto" and auf_auswahl:
        # Ein Bericht über eine markierte Antwort steht im Verhältnis zu ihr.
        # Zu einer Seite mit 17.800 Zeichen Quelltext entstanden zwölf Kapitel
        # und 99.000 Zeichen — dieselben Fakten in mehreren Kapiteln wiederholt.
        if material_chars < REPORT_MIN_MATERIAL * 4:
            return None
        return {
            "sections": max(3, min(7, material_chars // 2500)),
            "pages": 8,
            "words": 650,
            "stufe": "auswahl",
        }
    if stufe == "auto":
        # Ohne Stoff kein Umfang: Die Materialmenge entscheidet.
        if material_chars >= REPORT_MIN_MATERIAL * 6:
            stufe = "long"
        elif material_chars >= REPORT_MIN_MATERIAL * 2:
            stufe = "medium"
        else:
            return None
    if stufe not in {"medium", "long"}:
        return None
    plan = dict(REPORT_PLAN[stufe])
    # Dünnes Material bekommt weniger Kapitel statt mehr Erfindung.
    if material_chars and material_chars < REPORT_MIN_MATERIAL * 2:
        plan["sections"] = min(plan["sections"], 5)
    elif material_chars and material_chars < REPORT_MIN_MATERIAL * 6:
        plan["sections"] = min(plan["sections"], 8)
    plan["stufe"] = stufe
    return plan


# Der Hinweis auf fachliche Beratung gehört nur unter Berichte, die dem
# Lesenden wirklich etwas raten. „Anlagen", „Steuern" oder „Renditen" stehen
# auch in einem Baubericht — solche Wörter allein dürfen ihn nicht auslösen.
BERATUNGSFELDER = re.compile(
    r"(?i)\b("
    r"supplement\w*|dosier\w*|dosis|milligramm|mg|medikament\w*|arznei\w*|"
    r"wirkstoff\w*|nebenwirkung\w*|therapie\w*|diagnose\w*|symptom\w*|"
    r"präparat\w*|einnahme\w*|beipackzettel|"
    r"geldanlage\w*|kapitalanlage\w*|anlagestrategie\w*|aktienfonds|etf|"
    r"steuererklärung\w*|kreditvertrag\w*|zinssatz|"
    r"kündigungsfrist\w*|widerspruchsfrist\w*|vertragsklausel\w*|abmahnung\w*"
    r")\b"
)
BERATUNGSTON = re.compile(
    r"(?i)("
    r"empfiehlt sich|empfehlenswert|wird empfohlen|empfehlung:|"
    r"sollten sie|sollte man|ratsam|achten sie|einnahme von|dosierung|"
    r"täglich einnehmen"
    r")"
)


def braucht_beratungshinweis(text: str) -> bool:
    """Wahr, wenn der Bericht dem Lesenden fachlich etwas rät.

    Verlangt beides: mehrfach eindeutige Fachbegriffe und einen ratenden Ton.
    """
    return len(BERATUNGSFELDER.findall(text)) >= 2 and bool(BERATUNGSTON.search(text))


BELEGREGELN = (
    "Belegpflicht: Jede sachliche Aussage bekommt die Quelle, aus der sie stammt, "
    "im Format [[n]] mit der Nummer aus der Quellenliste. Erfinde niemals Quellen, "
    "Aktenzeichen, Archivbestände, Buchtitel, Interviewnummern oder Namen von "
    "Personen. Was du nicht belegen kannst, aber für die Darstellung brauchst, "
    "schreibst du ausdrücklich als Vermutung und hängst „[unbelegt]“ an den Satz. "
    "Lieber ein kurzer belegter Abschnitt als ein langer erfundener."
)


BELEGREGELN_OHNE_QUELLEN = (
    "Für diesen Bericht liegen keine geprüften Quellen vor. Verwende deshalb "
    "keine Quellenmarken wie [[1]] — sie zeigten ins Leere. Schreibe stattdessen "
    "aus gesichertem Allgemeinwissen und hänge an jede Aussage, bei der du dir "
    "nicht sicher bist, „[unbelegt]“ an. Erfinde keine Zahlen, Namen, Daten, "
    "Aktenzeichen oder Buchtitel."
)


def report_outline_prompt(
    topic: str, plan: dict[str, int], material: str, grenze: int = 12000,
) -> list[dict[str, str]]:
    """Erster Aufruf: die Gliederung."""

    anzahl = plan["sections"]
    return [
        {
            "role": "system",
            "content": (
                "Du gliederst einen Sachbericht. Antworte ausschließlich mit JSON der Form "
                '{"titel": "...", "abschnitte": [{"titel": "...", "inhalt": "..."}]}. '
                f"Genau {anzahl} Abschnitte. Jeder Abschnitt behandelt einen eigenen "
                "Gegenstand und wiederholt keinen anderen. Gliedere nach dem, was das "
                "Material hergibt — erfinde keine Kapitel über Dinge, zu denen nichts "
                "vorliegt. 'inhalt' beschreibt in einem Satz, was der Abschnitt belegt."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Thema: {topic}\n\n"
                f"Vorhandenes Material:\n{material[:grenze]}\n\n"
                f"Gliedere den Bericht in genau {anzahl} Abschnitte."
            ),
        },
    ]


def report_section_prompt(
    topic: str,
    plan: dict[str, int],
    outline: list[dict[str, str]],
    index: int,
    material: str,
    previous_tail: str,
    density_directive: str = "",
    has_sources: bool = True,
    grenze: int = 14000,
) -> list[dict[str, str]]:
    """Ein Aufruf je Kapitel."""

    abschnitt = outline[index]
    folgende = ", ".join(item["titel"] for item in outline[index + 1 :][:6])
    return [
        {
            "role": "system",
            "content": (
                "Du schreibst genau einen Abschnitt eines Sachberichts, in der Sprache "
                "des Auftrags. Beginne mit der Überschrift des Abschnitts als "
                "Markdown-Überschrift der zweiten Ebene und schreibe ihn vollständig "
                "aus — Fließtext, keine Stichpunkte als Ersatz für Sätze, keine "
                "Ankündigung dessen, was du gleich schreibst.\n"
                + (BELEGREGELN if has_sources else BELEGREGELN_OHNE_QUELLEN)
                + (f"\n{density_directive}" if density_directive else "")
            ),
        },
        {
            "role": "user",
            "content": (
                f"Thema des Berichts: {topic}\n"
                f"Abschnitt {index + 1} von {len(outline)}: {abschnitt['titel']}\n"
                f"Aufgabe dieses Abschnitts: {abschnitt.get('inhalt', '')}\n"
                f"Zielumfang: rund {plan['words']} Wörter.\n\n"
                f"Belegtes Material:\n{material[:grenze]}\n\n"
                + (f"Ende des vorherigen Abschnitts (nur zum Anschluss, nicht "
                   f"wiederholen):\n{previous_tail[-1200:]}\n\n" if previous_tail else "")
                + (f"Diese Abschnitte schreiben andere Aufrufe, greife ihnen nicht vor: "
                   f"{folgende}\n\n" if folgende else "")
                + "Schreibe jetzt ausschließlich diesen einen Abschnitt."
            ),
        },
    ]


def report_continue_prompt(
    topic: str,
    plan: dict[str, int],
    section: dict[str, str],
    written: str,
) -> list[dict[str, str]]:
    """Zweiter Aufruf für ein Kapitel, das zu kurz geraten ist."""

    return [
        {
            "role": "system",
            "content": (
                "Du setzt einen begonnenen Berichtsabschnitt fort. Wiederhole nichts "
                "Geschriebenes, setze keine neue Überschrift und beginne keinen neuen "
                "Abschnitt. Schreibe reinen Fließtext, der unmittelbar anschließt.\n"
                + BELEGREGELN
            ),
        },
        {
            "role": "user",
            "content": (
                f"Bericht über: {topic}\n"
                f"Abschnitt: {section['titel']}\n"
                f"Zielumfang des Abschnitts: rund {plan['words']} Wörter — bisher deutlich "
                "zu kurz.\n\nBisher geschrieben:\n"
                f"{written[-4000:]}\n\nSetze hier fort."
            ),
        },
    ]


def _clean(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _placeholder(value: str, fallback: str) -> str:
    return value if value else fallback


def _sender_from_profile(
    profile: dict[str, Any],
    profile_enabled: bool,
) -> dict[str, str]:
    if not profile_enabled:
        return {
            "name": "[Ihr Name]",
            "street": "[Straße und Hausnummer]",
            "postal_code": "[PLZ]",
            "city": "[Ort]",
            "country": "",
            "email": "[E-Mail]",
            "phone": "[Telefon]",
        }
    address = profile.get("address")
    if not isinstance(address, dict):
        address = {}
    return {
        "name": _placeholder(_clean(profile.get("name"), 120), "[Ihr Name]"),
        "street": _placeholder(
            _clean(address.get("street"), 180),
            "[Straße und Hausnummer]",
        ),
        "postal_code": _placeholder(
            _clean(address.get("postal_code"), 30),
            "[PLZ]",
        ),
        "city": _placeholder(_clean(address.get("city"), 120), "[Ort]"),
        "country": _clean(address.get("country"), 100),
        "email": _placeholder(_clean(profile.get("email"), 254), "[E-Mail]"),
        "phone": _placeholder(_clean(profile.get("phone"), 80), "[Telefon]"),
    }


def letter_skill_system_prompt(
    profile: dict[str, Any],
    profile_enabled: bool,
    date_label: str,
) -> str:
    return (
        "BRIEF-SKILL - diese Regeln haben für diese Antwort Vorrang:\n"
        "Der Nutzer verlangt einen fertigen, versandfähigen Brief, keine Anleitung, "
        "keine Mustersammlung, keine Erläuterung und keine Rückfragenliste. Erstelle "
        "genau einen sauberen Brief. Erfinde keine Namen, Anschriften, Aktenzeichen, "
        "Fristen, Tatsachen, Rechtsnormen oder Belege. Verwende bei fehlenden "
        "Empfängerdaten kurze eckige Platzhalter. Formuliere den vorhandenen Auftrag "
        "dennoch vollständig und professionell aus.\n\n"
        "Wenn der Kontext verifizierte Empfängerdaten aus einer offiziellen "
        "Primärquelle enthält, übernimm Name, Straße, Postleitzahl und Ort exakt. "
        "Wenn der ausgewählte Inhalt bereits einen konkreten Briefentwurf enthält, "
        "bewahre dessen Empfänger, Anlass, Betreff, konkrete Änderung und alle "
        "Nutzerangaben. Ersetze einen konkreten Auftrag niemals durch eine allgemeine "
        "Bitte um Sachstand oder Stellungnahme.\n\n"
        "Der Brief benötigt zwingend: Empfänger, Datum, optionales Aktenzeichen, "
        "präzisen Betreff, Anrede, zusammenhängende Textabsätze, die Schlussformel "
        "„Mit freundlichen Grüßen“ und eine Unterschriftszeile. Schreibe keine "
        "Überschriften wie Einleitung, Sachverhalt, rechtliche Bewertung oder "
        "Schlussfolgerung, sofern der Nutzer sie nicht ausdrücklich verlangt. "
        "Füge nach dem Brief keine Tipps, Quellenlisten oder Hinweise an.\n\n"
        "Enthält der Auftrag einen markierten Inhalt (zwischen „START MARKIERTER "
        "INHALT“ und „ENDE MARKIERTER INHALT“) und ist dieser kein Briefentwurf, dann "
        "ist er der Stoff des Briefs: Vermittle genau diesen Inhalt dem Empfänger — "
        "vollständig, verständlich, in ganzen Sätzen. Der Betreff benennt das Thema "
        "des Inhalts, zum Beispiel „Erläuterung: …“. Erfinde keinen Anlass wie eine "
        "Rückfrage, Bitte oder Stellungnahme, der im Inhalt nicht vorkommt.\n\n"
        f"Heutiges Datum: {date_label}. "
        "Absenderdaten und Seitenlayout werden nach der Textgenerierung deterministisch "
        "eingesetzt. Wiederhole keine Absenderdaten in den JSON-Feldern.\n\n"
        "Antworte ausschließlich als JSON entsprechend dem vorgegebenen Schema — mit "
        "genau diesen englischen Schlüsseln, auch wenn der Brief deutsch ist: "
        "recipient (name, department, street, postal_code, city, country), date, "
        "reference, subject, salutation, paragraphs (Liste der Absätze als Strings), "
        "closing. Keine Markdown-Codeblöcke und kein Text vor oder nach dem JSON."
    )


def letter_text_system_prompt(date_label: str) -> str:
    """Der zweite Weg: den Brief als Text schreiben lassen und danach einlesen."""
    return (
        "BRIEF ALS TEXT: Schreibe genau einen fertigen, versandfähigen Brief als "
        "reinen Text — kein JSON, kein Markdown, keine Erklärung davor oder danach. "
        "Form:\n"
        "Empfänger: Name, Straße, PLZ Ort (nur was bekannt ist)\n\n"
        "Betreff: …\n\n"
        "Anrede,\n\n"
        "Absätze, durch Leerzeilen getrennt\n\n"
        "Mit freundlichen Grüßen\n\n"
        "Keine Absenderangaben. Erfinde keine Namen, Anschriften, Fristen oder "
        "Tatsachen. Ist ein markierter Inhalt angegeben und kein Briefentwurf, dann "
        "ist er der Stoff des Briefs: Vermittle ihn vollständig und verständlich, "
        "der Betreff benennt sein Thema. "
        f"Heutiges Datum: {date_label}."
    )


def letter_audit_system_prompt() -> str:
    return (
        "BRIEF-ENDKONTROLLE: Prüfe den gelieferten Brief streng gegen den "
        "Nutzerauftrag und den bereitgestellten Kontext. Gib wieder ausschließlich "
        "JSON im vorgegebenen Schema zurück. Entferne jede Rechtsnorm, Frist, Rolle, "
        "Tatsache, Forderung, Anschrift, Begründung oder Verfahrensangabe, die nicht "
        "ausdrücklich im Nutzerauftrag oder Kontext steht. Füge keine zusätzlichen "
        "Anträge, Empfangsbestätigungen, Rückfragen, Belehrungen oder Empfehlungen "
        "hinzu. Verwende bei fehlenden Empfängerdaten nur knappe Platzhalter ohne "
        "Beispiele. Verifizierte Empfängerdaten aus einer offiziellen Primärquelle "
        "müssen unverändert erhalten bleiben. Empfänger, Anlass, Betreff und konkrete "
        "Nutzerangaben eines vorhandenen Entwurfs dürfen bei der Endkontrolle nicht "
        "verallgemeinert oder entfernt werden. Formuliere den konkreten Auftrag als "
        "fertigen höflichen Brief. "
        "Keine Markdown-Zeichen, keine Erklärungen und keine Quellenliste."
    )


def parse_structured_content(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


# --- Tolerante Brieffelder -------------------------------------------------
# glm-5.3-flash antwortete trotz Schema mit {"betreff", "anrede", "text"}. Das
# Brief-Modul fand weder subject noch paragraphs und setzte dann einen fest
# eingebauten Ersatzbrief über eine „schriftliche Stellungnahme" ein — bei
# jedem Brief, auch wenn der Nutzer Empfänger und Anschrift ausdrücklich nannte.
BRIEF_FELDER = {
    "betreff": "subject", "titel": "subject", "title": "subject", "thema": "subject",
    "anrede": "salutation", "greeting": "salutation", "begruessung": "salutation",
    "begrüßung": "salutation",
    "text": "paragraphs", "inhalt": "paragraphs", "brieftext": "paragraphs",
    "body": "paragraphs", "content": "paragraphs", "absaetze": "paragraphs",
    "absätze": "paragraphs", "abschnitte": "paragraphs", "paragraph": "paragraphs",
    "nachricht": "paragraphs", "text_absaetze": "paragraphs",
    "empfaenger": "recipient", "empfänger": "recipient", "adressat": "recipient",
    "an": "recipient", "to": "recipient", "addressee": "recipient",
    "datum": "date", "aktenzeichen": "reference", "zeichen": "reference",
    "az": "reference",
    "grussformel": "closing", "grußformel": "closing", "schluss": "closing",
    "schlussformel": "closing", "gruss": "closing", "gruß": "closing",
}
EMPFAENGER_FELDER = {
    "strasse": "street", "straße": "street", "adresse": "street",
    "anschrift": "street", "hausnummer": "street",
    "plz": "postal_code", "postleitzahl": "postal_code", "zip": "postal_code",
    "ort": "city", "stadt": "city", "wohnort": "city",
    "land": "country", "abteilung": "department", "firma": "department",
}
ANREDE_ZEILE = re.compile(r"^(sehr geehrte|liebe|lieber|hallo|guten tag)\b", re.I)
GRUSS_ZEILE = re.compile(
    r"^(mit freundlichen gr(ü|ue)(ß|ss)en|freundliche gr(ü|ue)(ß|ss)e|viele gr(ü|ue)(ß|ss)e|"
    r"beste gr(ü|ue)(ß|ss)e|herzliche gr(ü|ue)(ß|ss)e|hochachtungsvoll)",
    re.I,
)
AUFZAEHLUNG = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")


def _bloecke(text: str) -> list[str]:
    """Teilt einen Brieftext in Absätze; Aufzählungspunkte werden eigene Absätze."""
    text = str(text or "").replace("\r\n", "\n").replace("\\n", "\n").strip()
    if not text:
        return []
    roh = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    if len(roh) <= 1 and text.count("\n") >= 2:
        roh = [zeile.strip() for zeile in text.split("\n") if zeile.strip()]
    ergebnis: list[str] = []
    for block in roh:
        zeilen = [zeile for zeile in block.split("\n") if zeile.strip()]
        if any(AUFZAEHLUNG.match(zeile) for zeile in zeilen):
            # Jeder Aufzählungspunkt wird ein eigener Absatz mit Gedankenstrich —
            # auch wenn die Punkte ohne Leerzeile untereinander stehen.
            for zeile in zeilen:
                ergebnis.append(
                    "– " + AUFZAEHLUNG.sub("", zeile).strip()
                    if AUFZAEHLUNG.match(zeile) else zeile.strip()
                )
        else:
            ergebnis.append(" ".join(zeile.strip() for zeile in zeilen))
    return [eintrag for eintrag in ergebnis if eintrag]


def _empfaenger_aus_text(text: str) -> dict[str, str]:
    """„Hans Musterfrau, Muster Straße 2, 12345 Musterstadt" als Empfängerfelder."""
    ergebnis: dict[str, str] = {}
    for zeile in (teil.strip() for teil in re.split(r"\n|,", str(text or ""))):
        if not zeile:
            continue
        plz_ort = re.match(r"^(\d{4,5})\s+(.+)$", zeile)
        if plz_ort and "postal_code" not in ergebnis:
            ergebnis["postal_code"], ergebnis["city"] = plz_ort.group(1), plz_ort.group(2)
        elif "name" not in ergebnis:
            ergebnis["name"] = zeile
        elif re.search(r"\d", zeile) and "street" not in ergebnis:
            ergebnis["street"] = zeile
        elif "street" not in ergebnis and "department" not in ergebnis:
            ergebnis["department"] = zeile
    return ergebnis


def _absaetze_bereinigen(absaetze: list[str], ergebnis: dict[str, Any]) -> list[str]:
    """Anrede und Grußformel gehören nicht in die Absätze des Brieftexts."""
    if absaetze and ANREDE_ZEILE.match(absaetze[0].strip()) and len(absaetze[0]) <= 120:
        if not str(ergebnis.get("salutation") or "").strip():
            ergebnis["salutation"] = absaetze[0].strip()
        absaetze = absaetze[1:]
    for index, absatz in enumerate(absaetze):
        if GRUSS_ZEILE.match(absatz.strip()):
            return absaetze[:index]
    return absaetze


def brief_felder_angleichen(value: Any) -> dict[str, Any]:
    """Bringt eine Briefantwort mit fremden Feldnamen in das erwartete Schema."""
    if not isinstance(value, dict):
        return {}
    for huelle in ("brief", "letter", "schreiben"):
        innen = value.get(huelle)
        if isinstance(innen, dict):
            value = {**{k: v for k, v in value.items() if k != huelle}, **innen}
    ergebnis: dict[str, Any] = {}
    for schluessel, wert in value.items():
        ziel = BRIEF_FELDER.get(str(schluessel).strip().lower(), str(schluessel))
        if ergebnis.get(ziel) not in (None, "", [], {}):
            continue
        ergebnis[ziel] = wert

    empfaenger = ergebnis.get("recipient")
    if isinstance(empfaenger, str):
        empfaenger = _empfaenger_aus_text(empfaenger)
    if isinstance(empfaenger, dict):
        angeglichen: dict[str, Any] = {}
        for schluessel, wert in empfaenger.items():
            ziel = EMPFAENGER_FELDER.get(str(schluessel).strip().lower(), str(schluessel))
            if angeglichen.get(ziel) in (None, ""):
                angeglichen[ziel] = wert
        strasse = str(angeglichen.get("street") or "")
        teile = re.match(r"^(.*?),\s*(\d{4,5})\s+(.+)$", strasse)
        if teile and not str(angeglichen.get("postal_code") or "").strip():
            angeglichen["street"], angeglichen["postal_code"], angeglichen["city"] = teile.groups()
        ergebnis["recipient"] = angeglichen

    absaetze = ergebnis.get("paragraphs")
    if isinstance(absaetze, str):
        absaetze = _bloecke(absaetze)
    if isinstance(absaetze, list):
        flach: list[str] = []
        for eintrag in absaetze:
            if isinstance(eintrag, dict):
                eintrag = eintrag.get("text") or eintrag.get("inhalt") or " ".join(
                    str(wert) for wert in eintrag.values()
                )
            flach.extend(_bloecke(str(eintrag)))
        ergebnis["paragraphs"] = _absaetze_bereinigen(flach, ergebnis)
    return ergebnis


def brief_aus_text(text: str) -> dict[str, Any]:
    """Liest einen als Fließtext geschriebenen Brief in die Briefstruktur.

    Die Rettung, wenn ein Modell kein verwertbares JSON liefert: Einen Brief als
    Text schreibt jedes Modell zuverlässig — das hat derselbe Chat bewiesen, in
    dem der JSON-Weg fünfmal hintereinander scheiterte.
    """
    rumpf = re.sub(r"^```\w*\s*|\s*```$", "", str(text or "").strip()).strip()
    ergebnis: dict[str, Any] = {}
    betreff = re.search(r"(?im)^\s*\**\s*betreff\s*\**\s*:\s*(.+)$", rumpf)
    if betreff:
        ergebnis["subject"] = betreff.group(1).strip(" *")
    empfaenger = re.search(r"(?ims)^\s*\**\s*(?:empfänger|an)\s*\**\s*:\s*(.+?)(?:\n\s*\n)", rumpf + "\n\n")
    if empfaenger:
        ergebnis["recipient"] = _empfaenger_aus_text(empfaenger.group(1))
    anrede = re.search(r"(?im)^\s*((?:sehr geehrte|liebe|lieber|hallo|guten tag)[^\n]*)$", rumpf)
    if anrede:
        ergebnis["salutation"] = anrede.group(1).strip()
        rumpf = rumpf[anrede.end():]
    elif betreff:
        rumpf = rumpf[betreff.end():]
    ergebnis["paragraphs"] = _absaetze_bereinigen(_bloecke(rumpf), ergebnis)
    return ergebnis


# Ein Modell schrieb als Empfänger wörtlich „Name" und als Abteilung „Straße" —
# die Feldbezeichnungen statt Werten. Im Brief stand dann „Name / Straße".
FELDBEZEICHNUNGEN = frozenset({
    "name", "vorname", "nachname", "empfänger", "empfaenger", "adressat",
    "straße", "strasse", "hausnummer", "straße und hausnummer", "plz",
    "postleitzahl", "ort", "stadt", "plz ort", "abteilung", "firma",
    "unternehmen", "land", "adresse", "anschrift", "beispiel",
})


def _ist_platzhalter(wert: str) -> bool:
    bereinigt = re.sub(r"[\s:.,/]+", " ", wert).strip().lower()
    return (
        wert.startswith("[")
        or "z. b." in wert.lower()
        or bereinigt in FELDBEZEICHNUNGEN
    )


def normalize_letter_artifact(
    raw: Any,
    profile: dict[str, Any] | None = None,
    profile_enabled: bool | None = None,
    date_label: str = "",
    source_prompt: str = "",
) -> dict[str, Any]:
    value = brief_felder_angleichen(parse_structured_content(raw))
    recipient_value = value.get("recipient")
    if not isinstance(recipient_value, dict):
        recipient_value = {}
    recipient_name, recipient_department, recipient_street, recipient_postal, recipient_city = (
        "" if _ist_platzhalter(wert) else wert
        for wert in (
            _clean(recipient_value.get("name"), 180),
            _clean(recipient_value.get("department"), 180),
            _clean(recipient_value.get("street"), 180),
            _clean(recipient_value.get("postal_code"), 30),
            _clean(recipient_value.get("city"), 120),
        )
    )
    recipient = {
        "name": _placeholder(recipient_name, "[Name des Empfängers]"),
        "department": recipient_department,
        "street": _placeholder(recipient_street, "[Straße und Hausnummer]"),
        "postal_code": _placeholder(recipient_postal, "[PLZ]"),
        "city": _placeholder(recipient_city, "[Ort]"),
        "country": _clean(recipient_value.get("country"), 100),
    }

    sender_value = value.get("sender")
    if not isinstance(sender_value, dict):
        sender_value = {}
    sender = {
        "name": _clean(sender_value.get("name"), 120),
        "street": _clean(sender_value.get("street"), 180),
        "postal_code": _clean(sender_value.get("postal_code"), 30),
        "city": _clean(sender_value.get("city"), 120),
        "country": _clean(sender_value.get("country"), 100),
        "email": _clean(sender_value.get("email"), 254),
        "phone": _clean(sender_value.get("phone"), 80),
    }
    if profile_enabled is not None:
        sender = _sender_from_profile(profile or {}, profile_enabled)

    paragraphs_value = value.get("paragraphs")
    if not isinstance(paragraphs_value, list):
        paragraphs_value = []
    paragraphs = [
        _clean(item, 5000)
        for item in paragraphs_value[:12]
        if _clean(item, 5000)
    ]
    if "§" not in source_prompt:
        paragraphs = [
            re.sub(
                r"\s*(?:gemäß|nach)\s+§{1,2}\s*(?:\[[^\]]*\]|[^,.;]*)[,.;]?\s*",
                " ",
                paragraph,
                flags=re.IGNORECASE,
            ).strip()
            for paragraph in paragraphs
        ]
        paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    # Kein erfundener Ersatzbrief mehr. Ein leerer Brief wird vom Aufrufer
    # erkannt und über einen zweiten Weg geholt — oder ehrlich als Fehler
    # gemeldet. Die frühere „Bitte um Stellungnahme" war ein Brief, den niemand
    # bestellt hatte, und sie sah aus wie ein Ergebnis.

    subject = _clean(value.get("subject"), 300)
    subject = re.sub(r"\s*[–—-]\s*(?:Aktenzeichen\s*:?\s*)?\[[^\]]+\]\s*$", "", subject)
    subject = re.sub(r"\s{2,}", " ", subject).strip(" -–—")
    prompt_lower = source_prompt.lower()
    if "bitte" in prompt_lower and "antrag" not in prompt_lower:
        subject = re.sub(r"^antrag\s+auf\b", "Bitte um", subject, flags=re.IGNORECASE)
    if recipient["name"] == "[Name des Empfängers]":
        if "amtsgericht" in prompt_lower:
            recipient["name"] = "Amtsgericht [Ort]"
        elif "gericht" in prompt_lower:
            recipient["name"] = "[Name des Gerichts]"
    if (
        "stellungnahme" in prompt_lower
        and "verfahrensstand" in prompt_lower
        and len(source_prompt.split()) <= 60
    ):
        subject = "Bitte um schriftliche Stellungnahme zum aktuellen Verfahrensstand"
        paragraphs = [
            "hiermit bitte ich um eine schriftliche Stellungnahme zum aktuellen "
            "Stand des Verfahrens.",
            "Bitte teilen Sie mir außerdem mit, ob meinerseits noch Unterlagen oder "
            "weitere Angaben benötigt werden.",
        ]
    return {
        "type": "letter",
        "recipient": recipient,
        "sender": sender,
        "date": _placeholder(_clean(value.get("date"), 80), date_label or "[Datum]"),
        "reference": _clean(value.get("reference"), 160),
        "subject": _placeholder(subject, "[Betreff]"),
        "salutation": _placeholder(
            _clean(value.get("salutation"), 180),
            "Sehr geehrte Damen und Herren,",
        ),
        "paragraphs": paragraphs,
        "closing": "Mit freundlichen Grüßen",
        "signature": _placeholder(sender.get("name", ""), "[Ihr Name]"),
    }


def _letter_artifact_quality(
    artifact: dict[str, Any],
    source_prompt: str,
) -> float:
    recipient = artifact.get("recipient") or {}
    paragraphs = artifact.get("paragraphs") or []
    candidate_text = " ".join([
        str(recipient.get("name") or ""),
        str(recipient.get("street") or ""),
        str(recipient.get("postal_code") or ""),
        str(recipient.get("city") or ""),
        str(artifact.get("subject") or ""),
        *(str(item) for item in paragraphs),
    ]).lower()
    score = 0.0
    for key in ("name", "street", "postal_code", "city"):
        value = str(recipient.get(key) or "").strip()
        if value and not value.startswith("["):
            score += 2.0
    subject = str(artifact.get("subject") or "").strip()
    if subject and not subject.startswith("["):
        score += 3.0
    if paragraphs:
        score += min(4.0, float(len(paragraphs)))

    ignored = {
        "aktive", "skills", "ausschließlich", "nachfolgend", "markierten",
        "inhalt", "andere", "themen", "nachrichten", "anhänge", "dokumente",
        "fertige", "bearbeitete", "ergebnis", "start", "ende", "prompt",
        "ausgabe", "keine", "einen", "einer", "einem", "dieser", "dieses",
        "diese", "bitte", "brief", "schreiben",
    }
    source_terms = {
        term for term in re.findall(r"[\wäöüß-]{5,}", source_prompt.lower())
        if term not in ignored
    }
    score += min(
        10.0,
        sum(1.0 for term in source_terms if term in candidate_text),
    )

    source_lower = source_prompt.lower()
    generic_markers = (
        "schriftlichen stellungnahme",
        "aktuellen sachstand",
        "gegebenenfalls noch erforderlichen weiteren schritte",
    )
    if "stellungnahme" not in source_lower:
        score -= 5.0 * sum(
            1 for marker in generic_markers if marker in candidate_text
        )
    return score


def choose_letter_artifact(
    draft: Any,
    audited: Any,
    profile: dict[str, Any] | None = None,
    profile_enabled: bool | None = None,
    date_label: str = "",
    source_prompt: str = "",
) -> dict[str, Any]:
    """Keep an audit pass only when it preserves the concrete letter details."""
    draft_artifact = normalize_letter_artifact(
        draft,
        profile,
        profile_enabled,
        date_label,
        source_prompt,
    )
    audited_artifact = normalize_letter_artifact(
        audited,
        profile,
        profile_enabled,
        date_label,
        source_prompt,
    )
    if _letter_artifact_quality(
        audited_artifact,
        source_prompt,
    ) >= _letter_artifact_quality(draft_artifact, source_prompt):
        return audited_artifact
    return draft_artifact


def apply_verified_recipient(
    artifact: dict[str, Any],
    verified_recipient: dict[str, str] | None,
) -> dict[str, Any]:
    """Apply recipient data extracted from an official source after LLM auditing."""
    if not verified_recipient:
        return artifact
    recipient = artifact.setdefault("recipient", {})
    for key in ("name", "department", "street", "postal_code", "city", "country"):
        value = _clean(verified_recipient.get(key), 180)
        if value:
            recipient[key] = value
    return artifact


def letter_plain_text(artifact: dict[str, Any]) -> str:
    recipient = artifact.get("recipient") or {}
    sender = artifact.get("sender") or {}

    def address_lines(value: dict[str, Any], include_contact: bool = False) -> list[str]:
        lines = [
            _clean(value.get("name"), 180),
            _clean(value.get("department"), 180),
            _clean(value.get("street"), 180),
            " ".join(filter(None, [
                _clean(value.get("postal_code"), 30),
                _clean(value.get("city"), 120),
            ])),
            _clean(value.get("country"), 100),
        ]
        if include_contact:
            lines.extend([
                _clean(value.get("email"), 254),
                _clean(value.get("phone"), 80),
            ])
        return [line for line in lines if line]

    parts = [
        "Empfänger:",
        *address_lines(recipient),
        "",
        "Absender:",
        *address_lines(sender, include_contact=True),
        "",
        _clean(artifact.get("date"), 80),
    ]
    reference = _clean(artifact.get("reference"), 160)
    if reference:
        parts.extend(["", f"Aktenzeichen: {reference}"])
    parts.extend([
        "",
        f"Betreff: {_clean(artifact.get('subject'), 300)}",
        "",
        _clean(artifact.get("salutation"), 180),
        "",
    ])
    for paragraph in artifact.get("paragraphs") or []:
        cleaned = _clean(paragraph, 5000)
        if cleaned:
            parts.extend([cleaned, ""])
    parts.extend([
        _clean(artifact.get("closing"), 120) or "Mit freundlichen Grüßen",
        "",
        _clean(artifact.get("signature"), 120) or "[Ihr Name]",
    ])
    return "\n".join(parts).strip()
