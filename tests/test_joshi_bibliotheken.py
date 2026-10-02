# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""02.10.2026: three.js vom CDN liess die 3D-App schwarz bleiben — JOSHI bettet Bibliotheken jetzt ein."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from app.joshi import bibliotheken
from app.joshi.html_werk import laufzeit_dokument, statische_befunde

URL = "https://cdn.jsdelivr.net/npm/three@0.152.2/build/three.min.js"
SEITE = f'<!DOCTYPE html><html><body><canvas></canvas><script src="{URL}"></script><script>new THREE.Scene()</script></body></html>'


class BibliothekTests(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        self.patch = patch.object(bibliotheken, "_ordner", lambda: self._ordner())
        self.patch.start()
        self.geladen = []

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _ordner(self):
        from pathlib import Path
        os.makedirs(self.ordner, exist_ok=True)
        return Path(self.ordner)

    def laden(self, url):
        self.geladen.append(url)
        return b"window.THREE = {Scene: function(){}}; // </script> im Code"

    def test_cdn_script_becomes_a_placeholder_and_is_embedded_offline(self):
        html, eingebunden, fehl = bibliotheken.einbinden(SEITE, laden=self.laden)
        self.assertEqual(len(eingebunden), 1)
        self.assertNotIn("cdn.jsdelivr.net/npm/three@0.152.2/build/three.min.js\"></script>", html.split("data-quelle")[0])
        self.assertEqual([b for b in statische_befunde(html) if b.art == "fehler"], [])      # kein „Skript aus dem Internet“
        dokument = laufzeit_dokument(html, modus="vorschau")
        self.assertIn("window.THREE", dokument)
        self.assertIn("<\\/script> im Code", dokument)                                       # kann das Skript nicht beenden
        bibliotheken.einbinden(SEITE, laden=self.laden)
        self.assertEqual(len(self.geladen), 1)                                               # nur einmal geladen

    def test_missing_cache_is_reloaded_and_foreign_hosts_stay_blocked(self):
        html, _, _ = bibliotheken.einbinden(SEITE, laden=self.laden)
        shutil.rmtree(self.ordner)
        self.assertIn("window.THREE", bibliotheken.einsetzen(html, laden=self.laden))
        fremd = '<script src="https://evil.example.com/x.js"></script>'
        self.assertEqual(bibliotheken.einbinden(fremd, laden=self.laden)[0], fremd)


if __name__ == "__main__":
    unittest.main()
