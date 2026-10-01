# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Daten aus dem Netz (29.09.2026): Preise recherchiert JOSHI, das Modell setzt nur ein."""
from __future__ import annotations

import asyncio
import unittest

from app.joshi import recherche as r


class ErkennenTests(unittest.TestCase):
    def test_price_updates_need_research(self):
        for text in ("bitte die preise aktualisieren", "Preise stimmen nicht mehr, nimm echte Marktpreise",
                     "gleiche die Preise mit dem Internet ab"):
            self.assertEqual(r.bedarf(text), "preise", text)
        for text in ("mach die Preisanzeige größer", "füge ein Budgetfeld hinzu"):
            self.assertEqual(r.bedarf(text), "", text)

    def test_euro_amounts_are_read(self):
        self.assertEqual(r.betraege("ab € 189,00 bei geizhals, 1.049,00 € oder 199 EUR"), [189.0, 1049.0, 199.0])

    def test_neighbour_models_do_not_count(self):
        name = "NVIDIA GeForce RTX 4060"
        self.assertTrue(r.passt_zum_produkt("ASUS Dual GeForce RTX 4060 EVO OC ab € 289,00", name))
        self.assertFalse(r.passt_zum_produkt("MSI GeForce RTX 4060 Ti Ventus ab € 539,10", name))
        self.assertFalse(r.passt_zum_produkt("AMD Ryzen 5 7600X ab € 189,00", "AMD Ryzen 5 7600"))
        self.assertTrue(r.fremde_variante("Samsung SSD 990 EVO Plus 1TB ab € 189,00", "Samsung 990 EVO 1TB"))

    def test_placeholders_are_not_researched(self):
        positionen = r.positionen_normalisieren({"positionen": [
            {"name": "AMD Ryzen 5 7600", "preis": 200}, {"name": "Midi-Tower Standard", "preis": 80},
            {"name": "Tower", "preis": 30}, {"name": "AMD Ryzen 5 7600", "preis": 200}]})
        self.assertEqual([p["name"] for p in positionen], ["AMD Ryzen 5 7600"])


class SuchenTests(unittest.TestCase):
    TREFFER = {
        "AMD Ryzen 5 7600 Preis": [
            {"title": "AMD Ryzen 5 7600, 6C/12T ab € 154,50 | Geizhals", "url": "https://geizhals.de/amd-ryzen-5-7600-a1.html",
             "snippet": "Zubehör ab 4,99 €"},
            {"title": "AMD Ryzen 5 7600X ab € 139,00", "url": "https://geizhals.de/amd-ryzen-5-7600x-a2.html", "snippet": ""}],
        "NVIDIA GeForce RTX 4060 Preis": [
            {"title": "ASUS Dual GeForce RTX 4060 EVO OC White ab € 727,61", "url": "https://geizhals.de/asus-4060-a3.html",
             "snippet": ""}],
    }

    def suche(self, anfrage: str) -> list[dict[str, str]]:
        return self.TREFFER.get(anfrage, [])

    def test_the_right_model_with_source_is_chosen(self):
        funde = asyncio.run(r.recherchieren([{"name": "AMD Ryzen 5 7600", "kategorie": "CPU", "preis": 200},
                                             {"name": "NVIDIA GeForce RTX 4060", "kategorie": "GPU", "preis": 300}],
                                            suche=self.suche))
        ryzen, gpu = funde
        self.assertEqual((ryzen.neu, ryzen.quelle), (154.5, "geizhals.de"))   # nicht der 7600X, nicht Zubehör
        self.assertIsNone(gpu.neu)                                            # ein Beleg, +140 % → unsicher
        self.assertTrue(gpu.unsicher)
        auftrag = r.auftrag_text(funde)
        self.assertIn("AMD Ryzen 5 7600: 154,50 €", auftrag)
        self.assertIn("bleiben unverändert: NVIDIA GeForce RTX 4060", auftrag)

    def test_the_new_version_must_contain_the_prices(self):
        fund = r.Fund("AMD Ryzen 5 7600", 200, neu=154.5, quelle="geizhals.de")
        self.assertEqual(r.abgleich('const P = {cpu: {name: "AMD Ryzen 5 7600", preis: 154.50}}', [fund])[1], [])
        self.assertEqual(r.abgleich("<td>154,50 €</td>", [fund])[1], [])
        self.assertEqual(r.abgleich("preis: 200", [fund])[1], [fund])
        self.assertEqual(r.abgleich("preis: 1154.50", [fund])[1], [fund])      # keine Teilzahl


class EinsetzenTests(unittest.TestCase):
    """JOSHI tauscht Preise selbst — das Modell brach die App am 29.09.2026 mit einem Reihenfolgefehler."""

    CODE = """const DATA = {cpu: [
      {id:'cpu-r5-7600', name:'AMD Ryzen 5 7600', price:200, perf:75},
      {id:'cpu-r5-7600x', name:'AMD Ryzen 5 7600X', price:230, perf:80}],
    gpu: [{id:'gpu-4060', name:"NVIDIA GeForce RTX 4060", "price": 300.00, len:245},
          {id:'gpu-4060ti', name:'NVIDIA GeForce RTX 4060 Ti', price:400}]};"""

    def test_prices_are_replaced_at_the_right_product_only(self):
        funde = [r.Fund("AMD Ryzen 5 7600", 200, neu=149.89, quelle="geizhals.de"),
                 r.Fund("NVIDIA GeForce RTX 4060", 300, neu=289.0, quelle="idealo.de"),
                 r.Fund("Gibt es nicht 9000", 10, neu=9.0)]
        neu, eingesetzt, offen = r.einsetzen(self.CODE, funde)
        self.assertEqual([f.name for f in eingesetzt], ["AMD Ryzen 5 7600", "NVIDIA GeForce RTX 4060"])
        self.assertEqual([f.name for f in offen], ["Gibt es nicht 9000"])
        self.assertIn("name:'AMD Ryzen 5 7600', price:149.89", neu)
        self.assertIn("name:'AMD Ryzen 5 7600X', price:230", neu)          # Nachbarmodell unberührt
        self.assertIn('"price": 289, len', neu)
        self.assertIn("name:'NVIDIA GeForce RTX 4060 Ti', price:400", neu)
        self.assertIn("Ändere diese Preiswerte NICHT", r.anzeige_auftrag(funde, eingesetzt))
        self.assertIn("Änderungswunsch oben vollständig um", r.anzeige_auftrag(funde, eingesetzt))


class KatalogTests(unittest.TestCase):
    """Neubau mit Daten aus dem Netz: nur Produkte aus echten Seiten, nur mit gefundenem Preis."""

    class Zugang:
        def __init__(self):
            self.antworten = [
                {"kategorien": [{"name": "Grafikkarte", "suche": "Grafikkarten Bestenliste 2026"}]},
                {"produkte": [{"name": "NVIDIA GeForce RTX 5070", "leistung": 80, "merkmale": "12 GB GDDR7", "preis": 0},
                              {"name": "NVIDIA GeForce RTX 9999", "leistung": 99, "preis": 0},          # erfunden
                              {"name": "AMD Radeon RX 9060 XT", "leistung": 60, "preis": 0}]}]

        async def strukturiert(self, *a, **k):
            return self.antworten.pop(0)

    def suche(self, anfrage: str) -> list[dict[str, str]]:
        if "Bestenliste" in anfrage:
            return [{"title": "Die besten Grafikkarten 2026", "url": "https://example.org/beste",
                     "snippet": "Platz 1: NVIDIA GeForce RTX 5070, danach AMD Radeon RX 9060 XT und RTX 5070 Ti."}]
        if "5070" in anfrage:
            return [{"title": "NVIDIA GeForce RTX 5070 ab € 549,00", "url": "https://geizhals.de/rtx-5070.html", "snippet": ""}]
        return []

    def test_only_real_products_with_prices_enter_the_catalog(self):
        katalog, funde = asyncio.run(r.katalog_erstellen(self.Zugang(), "m", "PC-Konfigurator mit aktueller Hardware",
                                                         {}, suche=self.suche, seiten_laden=None))
        self.assertEqual([p["name"] for p in katalog], ["NVIDIA GeForce RTX 5070"])   # 9999 erfunden, 9060 XT ohne Preis
        self.assertEqual((katalog[0]["preis"], katalog[0]["quelle"], katalog[0]["leistung"]), (549.0, "geizhals.de", 80.0))
        text = r.katalog_text(katalog)
        self.assertIn("Grafikkarte | NVIDIA GeForce RTX 5070 | 549,00 € | 80", text)
        self.assertTrue(r.bedarf_neubau("Erstelle einen PC-Konfigurator mit aktuellen Hardware-Daten aus dem Netz"))
        self.assertFalse(r.bedarf_neubau("Baue einen BMI-Rechner"))


if __name__ == "__main__":
    unittest.main()


class DruckTests(unittest.TestCase):
    """PDF aus der App: eine Seite statt einer fast leeren zweiten, helle Schrift lesbar (29.09.2026)."""

    def test_slight_overflow_fits_one_page_and_light_text_gets_dark(self):
        import io
        from pypdf import PdfReader
        from app.joshi import export, renderer
        if not renderer.status().get("verfuegbar"):
            self.skipTest("WebKit-Renderer nicht übersetzt")
        zeilen = "".join(f"<tr><td>Teil {i}</td><td class='d'>Details {i}</td><td>{100 + i},00 €</td></tr>" for i in range(30))
        daten = asyncio.run(export.aus_abschnitt(format_="pdf", titel="PC",
                                                 html=f"<div><h2>Konfiguration</h2><table>{zeilen}</table></div>",
                                                 css="td{padding:14px 8px;font-size:15px} .d{color:#cfe7ff}"))
        self.assertEqual(len(PdfReader(io.BytesIO(daten)).pages), 1)
        self.assertIn("export.DRUCK_JS", "export.DRUCK_JS")
        self.assertIn('"#1f2937"', export.DRUCK_JS)          # helle Schrift auf Weiß wird dunkel
