# Sicherheit

*Mini LLM – powered by AI-Implements · C. Lins*

## Sicherheitslücke melden

Bitte **kein öffentliches Issue** für Sicherheitslücken. Nutze stattdessen die Funktion
**„Report a vulnerability“** im Reiter *Security* dieses Repositorys. Wir melden uns so schnell
wie möglich.

## Grundsätze

- Alle Daten bleiben lokal im Datenordner (`~/Library/Application Support/MiniLLM/data`).
- Passwörter werden mit Argon2 gespeichert; der erste Nutzer bekommt ein zufälliges Passwort.
- `.env`, Zertifikate und Datenbanken sind per `.gitignore` ausgeschlossen – niemals committen.
- Von JOSHI erzeugte Anwendungen laufen in einem abgeschotteten Rahmen ohne Netzwerkzugriff.
- Für den Zugriff von außen wird Tailscale empfohlen statt einer offenen Portfreigabe.

## Hinweise für den Betrieb

- Nach der ersten Anmeldung das Startpasswort ändern.
- Selbstregistrierung ist standardmäßig aus (`ALLOW_REGISTRATION=false`). Nur einschalten, wenn
  Mini LLM nicht offen aus dem Internet erreichbar ist.
- `.certs/mini-llm-ca.key` niemals weitergeben.
