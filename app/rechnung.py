# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Rechnungs-Skill: aus einem Auftrag eine vollständige, prüfbare Rechnung.

Das Modell liefert nur, was im Auftrag steht: Empfänger, Leistungen, Preise,
Zahlungsziel und Bankverbindung. Rechnungsnummer, Datum, Netto, Umsatzsteuer
und Summen setzt und rechnet Mini LLM selbst — ein Modell verrechnet sich,
eine Rechnung darf das nicht. Fehlende Pflichtangaben nach § 14 UStG werden
nicht erfunden, sondern als Hinweis gemeldet.

Beobachtet am 18.10.2026: Mit dem Brief-Skill wurde eine Rechnung zu einem
Brief mit „Aktenzeichen: RE/2026/0045“, die Posten standen als Strichlinien-
Tabelle im Fließtext, Netto und Umsatzsteuer fehlten.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.task_skills import _clean, _ist_platzhalter, parse_structured_content

CENT = Decimal("0.01")
STANDARD_STEUERSATZ = Decimal("19")

INVOICE_SCHEMA: dict[str, Any] = {
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
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": "string"},
        "service_date": {"type": "string"},
        "customer_number": {"type": "string"},
        "subject": {"type": "string"},
        "salutation": {"type": "string"},
        "intro": {"type": "string"},
        "items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 40,
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "unit_price": {"type": "number"},
                    "included": {"type": "boolean"},
                },
                "required": ["description", "quantity", "unit", "unit_price", "included"],
            },
        },
        "prices_are": {"type": "string", "enum": ["brutto", "netto", "unbekannt"]},
        "vat_rate": {"type": "number"},
        "payment_days": {"type": "integer"},
        "payment_day_type": {"type": "string"},
        "iban": {"type": "string"},
        "bic": {"type": "string"},
        "bank": {"type": "string"},
        "closing": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
    },
    "required": [
        "recipient", "invoice_number", "invoice_date", "service_date", "customer_number",
        "subject", "salutation", "intro", "items", "prices_are", "vat_rate",
        "payment_days", "payment_day_type", "iban", "bic", "bank", "closing", "notes",
    ],
}


def invoice_system_prompt(date_label: str) -> str:
    return (
        "RECHNUNGS-SKILL - diese Regeln haben für diese Antwort Vorrang:\n"
        "Erstelle die Daten genau einer Rechnung. Übernimm Empfänger, Leistungen, "
        "Mengen, Preise, Steuerangaben, Leistungsdatum, Zahlungsziel und "
        "Bankverbindung ausschließlich aus Auftrag, Verlauf oder markiertem Inhalt. "
        "Erfinde keine Beträge, Positionen, Rechnungsnummern, Kundennummern, Daten "
        "oder Bankdaten: Unbekannte Textfelder bleiben leer (\"\"), unbekannte Zahlen 0.\n\n"
        "Positionen: Gehe den Auftrag Leistung für Leistung durch. Jede Leistung, die "
        "mit eigenem Betrag oder mit „inkl.“/„inklusive“ statt eines Betrags genannt "
        "wird, ist eine eigene Position — fasse nie zwei Leistungen zusammen und teile "
        "keine. Die Beschreibung ist die Leistung so, wie sie im Auftrag steht, in "
        "sauberem Deutsch: Tippfehler korrigieren, nichts hinzufügen, nichts weglassen. "
        "quantity ist die Menge, ohne Angabe 1; unit ist die Einheit (Stück, Std., "
        "Monat, Jahr), ohne Angabe „pauschal“. unit_price ist der Preis je Einheit als "
        "Zahl ohne Währung und ohne Tausenderpunkt, z. B. 3880. Eine Leistung, die "
        "„inklusive“ oder „inkl.“ ohne eigenen Preis ist, wird eine Position mit "
        "included=true und unit_price 0. Rechne keine Summen aus — das übernimmt die "
        "Anwendung. Prüfe vor der Antwort: Zahl der Positionen = Zahl der genannten "
        "Leistungen, jeder genannte Betrag steht bei genau der Leistung, zu der er im "
        "Auftrag gehört.\n\n"
        "prices_are: „brutto“, wenn der Auftrag Bruttobeträge nennt, „netto“ bei "
        "Nettobeträgen, sonst „unbekannt“. vat_rate: der genannte Umsatzsteuersatz in "
        "Prozent, sonst 0. payment_days und payment_day_type aus dem Zahlungsziel "
        "(z. B. 14 und „Werktage“ oder „Tage“), sonst 0 und \"\". iban, bic und bank "
        "nur, wenn sie im Auftrag stehen.\n\n"
        "subject: kurzer Betreff wie „Rechnung für …“. salutation: eine vom Nutzer "
        "verlangte Anrede wörtlich, sonst eine passende förmliche Anrede mit Komma. "
        "intro: ein kurzer Satz, der auf die aufgeführten Leistungen verweist. "
        "closing: die vom Nutzer gewünschte Grußformel, sonst „Mit freundlichen "
        "Grüßen“. notes: nur Hinweise, die der Nutzer ausdrücklich nennt.\n\n"
        "Steht im Verlauf oder im markierten Inhalt bereits eine Rechnung, übernimm "
        "sie vollständig und ändere nur, was der Nutzer verlangt. Absenderdaten, "
        "Steuernummer, Rechnungsnummer und Datum setzt die Anwendung ein.\n\n"
        f"Heutiges Datum: {date_label}. Antworte ausschließlich als JSON nach dem "
        "vorgegebenen Schema mit genau diesen englischen Schlüsseln. Keine "
        "Markdown-Codeblöcke und kein Text vor oder nach dem JSON."
    )


# --- Zahlen ---------------------------------------------------------------

def betrag(wert: Any) -> Decimal | None:
    """3880, "3.880,00 €", "3880.5", "1,5" → Decimal. Unlesbares → None."""

    if isinstance(wert, bool) or wert is None:
        return None
    if isinstance(wert, (int, float, Decimal)):
        try:
            return Decimal(str(wert))
        except InvalidOperation:
            return None
    text = re.sub(r"[^\d,.\-]", "", str(wert))
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") \
            else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if re.search(r",\d{1,2}$", text) else text.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", text):
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def euro(wert: Decimal | int | float) -> str:
    """4860 → „4.860,00 €“."""

    zahl = Decimal(str(wert)).quantize(CENT, rounding=ROUND_HALF_UP)
    ganz, _, rest = f"{abs(zahl):.2f}".partition(".")
    gruppiert = f"{int(ganz):,}".replace(",", ".")
    return f"{'-' if zahl < 0 else ''}{gruppiert},{rest} €"


def menge_text(wert: Decimal) -> str:
    if wert == wert.to_integral_value():
        return str(int(wert))
    return f"{wert.normalize():f}".replace(".", ",")


def _zahlen_im_text(text: str) -> set[Decimal]:
    """Alle Beträge, die im Auftrag vorkommen — für die Gegenprobe der Positionen."""

    gefunden: set[Decimal] = set()
    for roh in re.findall(r"\d[\d.,]*", text or ""):
        wert = betrag(roh.rstrip(".,"))
        if wert is not None:
            gefunden.add(wert.quantize(CENT, rounding=ROUND_HALF_UP))
    return gefunden


# --- IBAN -----------------------------------------------------------------

def iban_formatieren(wert: str) -> str:
    kompakt = re.sub(r"\s+", "", wert or "").upper()
    return " ".join(kompakt[i:i + 4] for i in range(0, len(kompakt), 4))


def iban_gueltig(wert: str) -> bool:
    kompakt = re.sub(r"\s+", "", wert or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", kompakt):
        return False
    umgestellt = kompakt[4:] + kompakt[:4]
    return int("".join(str(int(zeichen, 36)) for zeichen in umgestellt)) % 97 == 1


# --- Daten ----------------------------------------------------------------

def _datum(text: str) -> dt.date | None:
    treffer = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text or "")
    if not treffer:
        return None
    try:
        return dt.date(int(treffer.group(3)), int(treffer.group(2)), int(treffer.group(1)))
    except ValueError:
        return None


def _deutsches_datum(text: str) -> str:
    """2026-10-14 → 14.10.2026; alles andere bleibt, wie es ist."""

    treffer = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", text or "")
    return f"{treffer.group(3)}.{treffer.group(2)}.{treffer.group(1)}" if treffer else text


ANSCHRIFT_IM_AUFTRAG = re.compile(
    r"\b(?:an|für)\s+(?:die|den|das|der)?\s*"
    r"([^,:\n]{2,80}),\s*([^,:\n]*\d[^,:\n]*),\s*(\d{4,5})\s+([^\s,:.]+(?:[ -][A-ZÄÖÜ][^\s,:.]*)*)",
    re.IGNORECASE,
)


def _empfaenger_aus_auftrag(text: str) -> dict[str, str]:
    """„… an die Bäckerei Korn, Hauptstraße 5, 12345 Musterstadt: …“ — Rückfallebene."""

    treffer = ANSCHRIFT_IM_AUFTRAG.search(text or "")
    if not treffer:
        return {}
    return {"name": treffer.group(1).strip(), "street": treffer.group(2).strip(),
            "postal_code": treffer.group(3), "city": treffer.group(4).strip()}


def _rechnungsnummer(jetzt: dt.datetime) -> str:
    """Eindeutig und zeitlich fortlaufend: RE-JJJJMMTT-HHMM."""

    return f"RE-{jetzt:%Y%m%d}-{jetzt:%H%M}"


def _sender_aus_profil(profile: dict[str, Any], profile_enabled: bool) -> dict[str, str]:
    leer = {"name": "", "organization": "", "street": "", "postal_code": "", "city": "",
            "country": "", "email": "", "phone": ""}
    if not profile_enabled:
        return leer
    adresse = profile.get("address") if isinstance(profile.get("address"), dict) else {}
    return {
        "name": _clean(profile.get("name"), 120),
        "organization": _clean(profile.get("organization"), 180),
        "street": _clean(adresse.get("street"), 180),
        "postal_code": _clean(adresse.get("postal_code"), 30),
        "city": _clean(adresse.get("city"), 120),
        "country": _clean(adresse.get("country"), 100),
        "email": _clean(profile.get("email"), 254),
        "phone": _clean(profile.get("phone"), 80),
    }


# --- Tolerante Felder ------------------------------------------------------
# glm-5.3-flash antwortete am 19.10.2026 trotz Schema mal mit „items“, mal mit
# „positions“ — ohne Angleichung kam „keine verwertbaren Positionen“ heraus.
FELDER = {
    "items": ("items", "positions", "positionen", "leistungen", "posten", "line_items",
              "lineitems", "rechnungspositionen", "services"),
    "recipient": ("recipient", "empfaenger", "empfänger", "kunde", "customer"),
    "invoice_number": ("invoice_number", "rechnungsnummer", "number", "nummer"),
    "invoice_date": ("invoice_date", "rechnungsdatum", "date", "datum"),
    "service_date": ("service_date", "leistungsdatum", "leistungszeitraum", "service_period"),
    "customer_number": ("customer_number", "kundennummer"),
    "subject": ("subject", "betreff", "titel", "title"),
    "salutation": ("salutation", "anrede"),
    "intro": ("intro", "einleitung", "text"),
    "prices_are": ("prices_are", "preisart", "preise"),
    "vat_rate": ("vat_rate", "steuersatz", "ust_satz", "mwst_satz", "tax_rate"),
    "payment_days": ("payment_days", "zahlungsziel_tage", "zahlungsfrist"),
    "payment_day_type": ("payment_day_type", "zahlungsziel_art", "fristart"),
    "iban": ("iban",),
    "bic": ("bic", "swift"),
    "bank": ("bank", "bankname"),
    "closing": ("closing", "grussformel", "grußformel", "gruss", "gruß"),
    "notes": ("notes", "hinweise_nutzer", "anmerkungen"),
}
POSITIONSFELDER = {
    "description": ("description", "beschreibung", "bezeichnung", "leistung", "name", "title", "text"),
    "quantity": ("quantity", "menge", "anzahl", "qty"),
    "unit": ("unit", "einheit"),
    "unit_price": ("unit_price", "einzelpreis", "preis", "price", "unitprice"),
    "total": ("total", "gesamt", "gesamtpreis", "betrag", "amount", "summe"),
    "included": ("included", "inklusive", "inkl", "inclusive"),
}


def _angleichen(wert: dict[str, Any], felder: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    klein = {str(schluessel).strip().lower(): inhalt for schluessel, inhalt in wert.items()}
    ergebnis = dict(wert)
    for ziel, namen in felder.items():
        if ergebnis.get(ziel) not in (None, "", [], {}):
            continue
        for name in namen:
            if klein.get(name) not in (None, "", [], {}):
                ergebnis[ziel] = klein[name]
                break
    return ergebnis


EMPFAENGERFELDER = {
    "name": ("name", "firma", "company", "empfänger", "empfaenger"),
    "department": ("department", "abteilung", "zusatz"),
    "street": ("street", "straße", "strasse", "address", "adresse", "anschrift"),
    "postal_code": ("postal_code", "plz", "zip", "postleitzahl", "zip_code", "postcode"),
    "city": ("city", "ort", "stadt"),
    "country": ("country", "land"),
}


def _adresse_aus_text(text: str) -> dict[str, str]:
    """„Bäckerei Korn, Hauptstraße 5, 12345 Musterstadt“ → Felder."""

    teile = [teil.strip() for teil in re.split(r"[,\n]+", text or "") if teil.strip()]
    adresse: dict[str, str] = {}
    for teil in teile:
        ort = re.match(r"^(\d{4,5})\s+(.+)$", teil)
        if ort and "postal_code" not in adresse:
            adresse["postal_code"], adresse["city"] = ort.group(1), ort.group(2)
        elif "name" not in adresse:
            adresse["name"] = teil
        elif "street" not in adresse and re.search(r"\d", teil):
            adresse["street"] = teil
        elif "street" not in adresse:
            adresse["department"] = teil
    return adresse


def _empfaenger_angleichen(wert: dict[str, Any]) -> dict[str, Any]:
    empfaenger = wert.get("recipient")
    if isinstance(empfaenger, str):
        empfaenger = _adresse_aus_text(empfaenger)
    if not isinstance(empfaenger, dict):
        empfaenger = {}
    empfaenger = _angleichen(empfaenger, EMPFAENGERFELDER)
    # Flache Felder wie „recipient_name“, „recipient_zip“ (glm-5.3-flash, 19.10.2026).
    for schluessel, inhalt in wert.items():
        treffer = re.match(r"(?i)^(?:recipient|empfaenger|empfänger|customer|kunde)_(.+)$", str(schluessel))
        if not treffer or inhalt in (None, ""):
            continue
        feld = treffer.group(1).lower()
        for ziel, namen in EMPFAENGERFELDER.items():
            if feld in namen and not empfaenger.get(ziel):
                empfaenger[ziel] = inhalt
    # Name aus Teilen: {"company": "", "first_name": "", "last_name": "Weber"}.
    if not str(empfaenger.get("name") or "").strip():
        klein = {str(k).lower(): str(v or "").strip() for k, v in empfaenger.items()}
        firma = klein.get("company") or klein.get("firma") or klein.get("organization")
        person = " ".join(filter(None, [
            klein.get("first_name") or klein.get("vorname") or klein.get("firstname"),
            klein.get("last_name") or klein.get("nachname") or klein.get("lastname"),
        ]))
        empfaenger["name"] = firma or person
    # „Hauptstraße 5, 12345 Musterstadt“ in einem Feld: Straße, PLZ und Ort trennen.
    for feld in ("street", "city"):
        text = str(empfaenger.get(feld) or "")
        treffer = re.match(r"^(?:(.*?)[,\s]+)?(\d{4,5})\s+([^\d,]+?)\s*$", text)
        if treffer and not empfaenger.get("postal_code"):
            if treffer.group(1):
                empfaenger["street"] = treffer.group(1).strip(" ,")
            elif feld == "street":
                empfaenger["street"] = ""
            empfaenger["postal_code"], empfaenger["city"] = treffer.group(2), treffer.group(3).strip()
    return empfaenger


def rechnung_felder_angleichen(wert: Any) -> dict[str, Any]:
    if isinstance(wert, list):
        wert = {"items": wert}
    if not isinstance(wert, dict):
        return {}
    for huelle in ("invoice", "rechnung"):
        if isinstance(wert.get(huelle), dict) and not wert.get("items"):
            wert = {**wert[huelle], **{k: v for k, v in wert.items() if k != huelle}}
    wert = _angleichen(wert, FELDER)
    wert["recipient"] = _empfaenger_angleichen(wert)
    if isinstance(wert.get("notes"), str):
        wert["notes"] = [wert["notes"]] if wert["notes"].strip() else []
    positionen = []
    for eintrag in wert.get("items") or []:
        if not isinstance(eintrag, dict):
            continue
        eintrag = _angleichen(eintrag, POSITIONSFELDER)
        # Nur ein Gesamtbetrag genannt: Einzelpreis daraus ableiten.
        if eintrag.get("unit_price") in (None, "") and eintrag.get("total") not in (None, ""):
            menge = betrag(eintrag.get("quantity")) or Decimal(1)
            gesamt = betrag(eintrag.get("total"))
            if gesamt is not None and menge:
                eintrag["unit_price"] = (gesamt / menge).quantize(CENT, rounding=ROUND_HALF_UP)
        if isinstance(eintrag.get("included"), str):
            eintrag["included"] = eintrag["included"].strip().lower() in {"true", "ja", "yes", "inkl", "inklusive"}
        positionen.append(eintrag)
    wert["items"] = positionen
    return wert


# --- Normalisieren und Rechnen --------------------------------------------

def normalize_invoice_artifact(
    raw: Any,
    profile: dict[str, Any] | None = None,
    profile_enabled: bool | None = None,
    date_label: str = "",
    source_prompt: str = "",
    jetzt: dt.datetime | None = None,
    vorige_nummer: str = "",
) -> dict[str, Any]:
    """Aus Modellantwort oder gespeichertem Artefakt eine durchgerechnete Rechnung.

    Ohne ``profile_enabled`` (Export, erneute Anzeige) bleiben gespeicherte
    Absender-, Steuer- und Rechnungsdaten unverändert — die Summen werden
    dennoch aus den Positionen neu gerechnet.
    """

    roh = raw if isinstance(raw, (dict, list)) else parse_structured_content(raw)
    if isinstance(raw, str) and not roh:
        roh = _liste_lesen(raw)
    wert = rechnung_felder_angleichen(roh)
    jetzt = jetzt or dt.datetime.now()
    gespeichert = wert.get("type") == "invoice"
    profil = profile or {}
    rechnung_profil = profil.get("invoice") if isinstance(profil.get("invoice"), dict) else {}
    hinweise: list[str] = []

    empfaenger_roh = wert.get("recipient") if isinstance(wert.get("recipient"), dict) else {}
    if not gespeichert and not str(empfaenger_roh.get("name") or "").strip():
        # Das Modell lieferte keinen Empfänger — die Anschrift steht oft wörtlich im Auftrag.
        empfaenger_roh = {**empfaenger_roh, **_empfaenger_aus_auftrag(source_prompt)}
    empfaenger = {
        feld: ("" if _ist_platzhalter(text) else text)
        for feld, text in (
            (feld, _clean(empfaenger_roh.get(feld), 180))
            for feld in ("name", "department", "street", "postal_code", "city", "country")
        )
    }

    if profile_enabled is None:
        absender_roh = wert.get("sender") if isinstance(wert.get("sender"), dict) else {}
        absender = {feld: _clean(absender_roh.get(feld), 254) for feld in (
            "name", "organization", "street", "postal_code", "city", "country", "email", "phone")}
        steuer_id = _clean(wert.get("tax_id"), 60)
        kleinunternehmer = bool(wert.get("small_business"))
    else:
        absender = _sender_aus_profil(profil, bool(profile_enabled))
        steuer_id = _clean(rechnung_profil.get("tax_id"), 60) if profile_enabled else ""
        kleinunternehmer = bool(profile_enabled) and rechnung_profil.get("vat_mode") == "small"

    # Bankverbindung: Angaben im Auftrag gehen dem Profil vor.
    iban = _clean(wert.get("iban"), 60)
    bic = _clean(wert.get("bic"), 20)
    bank = _clean(wert.get("bank"), 120)
    if profile_enabled and not iban:
        iban = _clean(rechnung_profil.get("iban"), 60)
        bic = bic or _clean(rechnung_profil.get("bic"), 20)
        bank = bank or _clean(rechnung_profil.get("bank"), 120)
    iban = iban_formatieren(iban) if iban else ""

    # Positionen
    im_auftrag = _zahlen_im_text(source_prompt)
    positionen: list[dict[str, Any]] = []
    for eintrag in (wert.get("items") or [])[:40]:
        if not isinstance(eintrag, dict):
            continue
        beschreibung = _clean(eintrag.get("description"), 400)
        if not beschreibung:
            continue
        inklusive = bool(eintrag.get("included"))
        menge = betrag(eintrag.get("quantity")) or Decimal(1)
        if menge <= 0:
            menge = Decimal(1)
        preis = betrag(eintrag.get("unit_price")) or Decimal(0)
        if inklusive:
            preis = Decimal(0)
        if not gespeichert and preis and im_auftrag:
            # Cent statt Euro (ministral-3:8b, 19.10.2026: 24000 statt 240 €):
            # Steht genau der hundertste Teil im Auftrag, gilt dieser.
            hundertstel = (preis / 100).quantize(CENT)
            if preis.quantize(CENT) not in im_auftrag and hundertstel in im_auftrag:
                hinweise.append(
                    f"„{_clean(eintrag.get('description'), 60)}“: {euro(preis)} als {euro(hundertstel)} "
                    "gelesen (Betrag laut Auftrag)."
                )
                preis = hundertstel
        gesamt = (menge * preis).quantize(CENT, rounding=ROUND_HALF_UP)
        positionen.append({
            "pos": len(positionen) + 1,
            "description": beschreibung,
            "quantity": float(menge),
            "unit": _clean(eintrag.get("unit"), 30) or "pauschal",
            "unit_price": float(preis),
            "total": float(gesamt),
            "included": inklusive,
        })

    summe = sum((Decimal(str(p["total"])) for p in positionen), Decimal(0))
    preisart = str(wert.get("prices_are") or "").strip().lower()
    if preisart not in {"brutto", "netto"}:
        preisart = "unbekannt"
    satz = betrag(wert.get("vat_rate")) or Decimal(0)
    if gespeichert and kleinunternehmer:
        satz = Decimal(0)
    if kleinunternehmer:
        satz = Decimal(0)
        netto, steuer, brutto = summe, Decimal(0), summe
    else:
        if not (Decimal(0) < satz <= Decimal(30)):
            satz = STANDARD_STEUERSATZ
            if not gespeichert:
                hinweise.append("Umsatzsteuersatz nicht genannt – 19 % angesetzt.")
        if preisart == "brutto":
            brutto = summe
            netto = (brutto / (1 + satz / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
            steuer = brutto - netto
        else:
            if preisart == "unbekannt" and not gespeichert and summe:
                hinweise.append(
                    "Beträge ohne Angabe „brutto“ oder „netto“ als Nettobeträge berechnet."
                )
            netto = summe
            steuer = (netto * satz / 100).quantize(CENT, rounding=ROUND_HALF_UP)
            brutto = netto + steuer

    # Rechnungsnummer, Datum, Leistungsdatum
    nummer = _clean(wert.get("invoice_number"), 60)
    if (not nummer or _ist_platzhalter(nummer)) and vorige_nummer:
        # Eine Änderung an der Rechnung behält ihre Nummer.
        nummer = _clean(vorige_nummer, 60)
    if not nummer or _ist_platzhalter(nummer):
        nummer = _rechnungsnummer(jetzt)
        hinweise.append(f"Rechnungsnummer {nummer} automatisch vergeben – bei eigener Nummernfolge anpassen.")
    rechnungsdatum = _deutsches_datum(_clean(wert.get("invoice_date"), 40))
    if not _datum(rechnungsdatum):
        rechnungsdatum = date_label or jetzt.strftime("%d.%m.%Y")
    leistungsdatum = _deutsches_datum(_clean(wert.get("service_date"), 80))
    if (not leistungsdatum or _ist_platzhalter(leistungsdatum)) and not gespeichert:
        # „Leistung am 14.10.2026“ — glm-5.3-flash ließ es am 19.10.2026 mal weg.
        genannt = re.search(
            r"(?i)leistung\w*\s+(?:am|vom|erbracht am|zeitraum)?\s*:?\s*"
            r"(\d{1,2}\.\d{1,2}\.\d{4}(?:\s*(?:-|–|bis)\s*\d{1,2}\.\d{1,2}\.\d{4})?)",
            source_prompt or "",
        )
        if genannt:
            leistungsdatum = genannt.group(1)
    if not leistungsdatum or _ist_platzhalter(leistungsdatum):
        leistungsdatum = "entspricht dem Rechnungsdatum"
        if not gespeichert:
            hinweise.append("Leistungsdatum nicht genannt – als Rechnungsdatum angegeben.")

    # Zahlungsziel
    tage = 0
    try:
        tage = max(0, min(365, int(wert.get("payment_days") or 0)))
    except (TypeError, ValueError):
        tage = 0
    art = _clean(wert.get("payment_day_type"), 20).lower()
    if gespeichert and wert.get("payment_terms"):
        zahlungsziel = _clean(wert.get("payment_terms"), 300)
    elif tage and "werk" in art:
        zahlungsziel = f"Zahlbar innerhalb von {tage} Werktagen ab Rechnungsdatum ohne Abzug."
    elif tage and "arbeit" in art:
        zahlungsziel = f"Zahlbar innerhalb von {tage} Arbeitstagen ab Rechnungsdatum ohne Abzug."
    else:
        if not tage:
            tage = 14
            hinweise.append("Zahlungsziel nicht genannt – 14 Tage angesetzt.")
        start = _datum(rechnungsdatum) or jetzt.date()
        faellig = start + dt.timedelta(days=tage)
        zahlungsziel = (
            f"Zahlbar innerhalb von {tage} Tagen bis zum {faellig:%d.%m.%Y} ohne Abzug."
        )

    # Pflichtangaben und Gegenprobe — Hinweise statt Erfindungen
    if not gespeichert:
        if not absender.get("name") or not absender.get("street"):
            hinweise.append("Absender fehlt – „Über mich“ einschalten und Adresse im Profil pflegen.")
        if not steuer_id:
            hinweise.append(
                "Steuernummer oder USt-IdNr. fehlt (Pflichtangabe) – im Profil unter Rechnungsangaben eintragen."
            )
        if not all(empfaenger.get(feld) for feld in ("name", "street", "postal_code", "city")):
            hinweise.append("Anschrift des Empfängers unvollständig.")
        if not iban:
            hinweise.append("Keine Bankverbindung angegeben.")
        elif not iban_gueltig(iban):
            hinweise.append(f"Die IBAN {iban} hat eine ungültige Prüfziffer – bitte prüfen.")
        if not positionen:
            hinweise.append("Keine Rechnungspositionen erkannt.")
        if im_auftrag:
            for position in positionen:
                preis = Decimal(str(position["unit_price"])).quantize(CENT)
                gesamt = Decimal(str(position["total"])).quantize(CENT)
                if preis and preis not in im_auftrag and gesamt not in im_auftrag:
                    hinweise.append(
                        f"Position {position['pos']}: {euro(preis)} steht so nicht im Auftrag – bitte prüfen."
                    )
    else:
        hinweise = [_clean(h, 300) for h in (wert.get("hints") or []) if _clean(h, 300)]

    anrede = _clean(wert.get("salutation"), 180) or "Sehr geehrte Damen und Herren,"
    gruss = _clean(wert.get("closing"), 80) or "Mit freundlichen Grüßen"
    notizen = [_clean(n, 400) for n in (wert.get("notes") or []) if _clean(n, 400)][:4]
    # Modelle wiederholen Zahlungsziel oder IBAN gern als Hinweis — doppelt steht es nicht.
    notizen = [
        n for n in notizen
        if not (re.search(r"(?i)zahl|überweis|frist", n) and (str(tage) in n or "tag" in n.lower()))
        and not (iban and re.sub(r"\s", "", iban) in re.sub(r"\s", "", n))
    ]
    if kleinunternehmer:
        hinweis_19 = "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."
        if hinweis_19 not in notizen:
            notizen.append(hinweis_19)

    return {
        "type": "invoice",
        "recipient": empfaenger,
        "sender": absender,
        "tax_id": steuer_id,
        "small_business": kleinunternehmer,
        "invoice_number": nummer,
        "invoice_date": rechnungsdatum,
        "service_date": leistungsdatum,
        "customer_number": _clean(wert.get("customer_number"), 60),
        "subject": _clean(wert.get("subject"), 200) or "Rechnung",
        "salutation": anrede,
        "intro": _clean(wert.get("intro"), 600),
        "items": positionen,
        "prices_are": "brutto" if preisart == "brutto" else "netto",
        "vat_rate": float(satz),
        "net": float(netto),
        "vat": float(steuer),
        "gross": float(brutto),
        "payment_terms": zahlungsziel,
        "iban": iban,
        "bic": bic.upper(),
        "bank": bank,
        "closing": gruss,
        "signature": absender.get("name") or "",
        "notes": notizen,
        "hints": hinweise[:10],
    }


def _liste_lesen(text: str) -> Any:
    """Eine Antwort, die nur aus einer JSON-Liste besteht."""

    import json

    treffer = re.search(r"\[[\s\S]*\]", text or "")
    if not treffer:
        return {}
    try:
        return json.loads(treffer.group(0))
    except ValueError:
        return {}


def vorige_rechnungsnummer(texte: list[str]) -> str:
    """Nummer der zuletzt erstellten Rechnung aus dem Verlauf („Rechnung Nr. …“)."""

    for text in reversed(texte):
        treffer = re.match(r"Rechnung Nr\. (\S+)", text or "")
        if treffer:
            return treffer.group(1)
    return ""


def invoice_totals_lines(rechnung: dict[str, Any]) -> list[tuple[str, str, bool]]:
    """(Bezeichnung, Betrag, hervorgehoben) — dieselbe Reihenfolge in Chat und Export."""

    satz = Decimal(str(rechnung.get("vat_rate") or 0))
    satz_text = menge_text(satz)
    if rechnung.get("small_business"):
        return [("Gesamtbetrag", euro(rechnung["gross"]), True)]
    if rechnung.get("prices_are") == "brutto":
        return [
            ("Gesamtbetrag (brutto)", euro(rechnung["gross"]), True),
            (f"darin enthalten {satz_text} % USt", euro(rechnung["vat"]), False),
            ("Nettobetrag", euro(rechnung["net"]), False),
        ]
    return [
        ("Nettobetrag", euro(rechnung["net"]), False),
        (f"zzgl. {satz_text} % USt", euro(rechnung["vat"]), False),
        ("Gesamtbetrag", euro(rechnung["gross"]), True),
    ]


def invoice_address_lines(wert: dict[str, Any], mit_kontakt: bool = False) -> list[str]:
    zeilen = [
        _clean(wert.get("organization"), 180) if mit_kontakt else "",
        _clean(wert.get("name"), 180),
        _clean(wert.get("department"), 180),
        _clean(wert.get("street"), 180),
        " ".join(filter(None, [_clean(wert.get("postal_code"), 30), _clean(wert.get("city"), 120)])),
        _clean(wert.get("country"), 100),
    ]
    if mit_kontakt:
        zeilen += [_clean(wert.get("email"), 254), _clean(wert.get("phone"), 80)]
    # Organisation und Name dürfen nicht doppelt stehen.
    if zeilen[0] and zeilen[0] == zeilen[1]:
        zeilen[0] = ""
    return [zeile for zeile in zeilen if zeile]


def invoice_plain_text(rechnung: dict[str, Any]) -> str:
    """Textfassung für Verlauf, Kopieren und Folgefragen."""

    teile = [
        f"Rechnung Nr. {rechnung['invoice_number']}",
        f"Rechnungsdatum: {rechnung['invoice_date']} · Leistungsdatum: {rechnung['service_date']}",
    ]
    if rechnung.get("customer_number"):
        teile.append(f"Kundennummer: {rechnung['customer_number']}")
    teile += ["", "Empfänger:", *invoice_address_lines(rechnung["recipient"]), "",
              "Absender:", *invoice_address_lines(rechnung["sender"], mit_kontakt=True)]
    if rechnung.get("tax_id"):
        teile.append(f"Steuernummer/USt-IdNr.: {rechnung['tax_id']}")
    teile += ["", f"Betreff: {rechnung['subject']}", "", rechnung["salutation"], ""]
    if rechnung.get("intro"):
        teile += [rechnung["intro"], ""]
    teile += ["| Pos. | Leistung | Menge | Einzelpreis | Gesamt |", "|---|---|---|---|---|"]
    for position in rechnung["items"]:
        einzel = "inklusive" if position["included"] else euro(position["unit_price"])
        gesamt = "inklusive" if position["included"] else euro(position["total"])
        teile.append(
            f"| {position['pos']} | {position['description']} | "
            f"{menge_text(Decimal(str(position['quantity'])))} {position['unit']} | {einzel} | {gesamt} |"
        )
    teile.append("")
    for bezeichnung, wert, _ in invoice_totals_lines(rechnung):
        teile.append(f"{bezeichnung}: {wert}")
    teile += ["", rechnung["payment_terms"]]
    bank = invoice_bank_line(rechnung)
    if bank:
        teile.append(bank)
    for notiz in rechnung.get("notes") or []:
        teile.append(notiz)
    teile += ["", rechnung["closing"], "", rechnung.get("signature") or ""]
    return "\n".join(teile).strip()


def invoice_bank_line(rechnung: dict[str, Any]) -> str:
    teile = []
    if rechnung.get("iban"):
        teile.append(f"IBAN {rechnung['iban']}")
    if rechnung.get("bic"):
        teile.append(f"BIC {rechnung['bic']}")
    if rechnung.get("bank"):
        teile.append(rechnung["bank"])
    return ("Bankverbindung: " + " · ".join(teile)) if teile else ""
