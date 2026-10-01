# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""JOSHI – Just On-demand Software from Human Intent.

Aus einer Idee (Text, Bilder, Dateien, optional Chat-Kontext) wird eine
lauffähige, eigenständige HTML-Anwendung: gebaut vom gewählten Modell, geprüft
in einer echten Browser-Engine, versioniert, exportier- und teilbar.

Aufbau (siehe docs/JOSHI.md):
  html_werk  – HTML aus Modellantworten, Änderungsblöcke, Assets, Laufzeit-Hülle
  renderer   – WebKit-Renderer (Swift) für Prüfung, Bild und PDF
  pruefer    – entscheidet anhand der Messung, ob ein Produkt funktioniert
  prompts    – Verstehen, Bauen, Ändern, Reparieren
  pipeline   – der feste Ablauf VERSTEHEN → BAUEN → PRÜFEN → REPARIEREN → BEREIT
  speicher   – Produkte, Versionen, Aufträge, Bilder (SQLite + Dateien)
  jobs       – Hintergrundaufträge, die ohne offenen Browser weiterlaufen
  export     – HTML mit Zustand, PNG/JPG, PDF, Word, E-Mail
  bruecke    – Chat → JOSHI und JOSHI → Chat
  api        – HTTP-Schnittstelle /api/joshi/*
"""
