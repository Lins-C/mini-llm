# Anleitungen

*Mini LLM – powered by AI-Implements · C. Lins*

- [Modell wählen](#modell-wählen)
- [Vom Handy zugreifen](#vom-handy-zugreifen)
- [Unterwegs mit Tailscale](#unterwegs-mit-tailscale)
- [Dauerbetrieb (24/7)](#dauerbetrieb-247)
- [JOSHI nutzen](#joshi-nutzen)
- [Aktualisieren](#aktualisieren)
- [Sichern und Umziehen](#sichern-und-umziehen)
- [Deinstallieren](#deinstallieren)
- [Probleme lösen](#probleme-lösen)

---

## Modell wählen

```bash
ollama pull gemma3:4b        # schnell, klein, gut für Alltagsfragen
ollama pull qwen3:8b         # stärker, braucht ~8 GB freien Speicher
ollama pull gemma3:12b       # Bilder verstehen (Vision), ab 16 GB
```

Alle geladenen Modelle erscheinen automatisch in der Auswahl oben. Für JOSHI (Anwendungen
bauen) liefern größere Modelle oder Ollama-Cloud-Modelle deutlich bessere Ergebnisse.

## Vom Handy zugreifen

**Im selben WLAN:** Die Adresse zeigt `start.command` am Ende an (Zeile „Heimnetz“),
zum Beispiel `https://192.168.1.50:8443`. Beim ersten Aufruf warnt der Browser vor dem
selbst erzeugten Zertifikat – bestätigen oder das Zertifikat installieren (siehe unten).

**Zertifikat auf dem iPhone vertrauen** (nur für den direkten Zugriff nötig):

1. `.certs/mini-llm-ca.crt` per AirDrop aufs iPhone senden
2. **Einstellungen → Allgemein → VPN und Geräteverwaltung** → Profil installieren
3. **Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen** →
   „Mini LLM private CA“ aktivieren

`.certs/mini-llm-ca.key` niemals weitergeben.

## Unterwegs mit Tailscale

Empfohlen – kein Router-Umbau, gültiges Zertifikat, nur deine Geräte haben Zugriff.

1. [Tailscale](https://tailscale.com/download) auf Mac und Handy installieren, gleiches Konto
2. `start.command` einmal ausführen
3. `tailscale-access.command` doppelklicken
4. Die angezeigte Adresse `https://<mac>.<tailnet>.ts.net` auf dem Handy öffnen und als
   Lesezeichen oder auf dem Home-Bildschirm speichern

## Dauerbetrieb (24/7)

`start.command` richtet den Dienst bereits so ein, dass er im Hintergrund weiterläuft und nach
einer Anmeldung automatisch startet. Zusätzlich:

- Ollama unter **Systemeinstellungen → Allgemein → Anmeldeobjekte** eintragen
- **Systemeinstellungen → Energie:** Ruhezustand verhindern, nach Stromausfall starten

Nur den Dienst neu einrichten: `install-24-7.command`. Entfernen: `uninstall-24-7.command`.

## JOSHI nutzen

1. Oben auf **JOSHI**
2. Beschreiben, was du brauchst – so konkret wie möglich, gern mit Bildern oder Dateien
3. Optional **Web** einschalten: JOSHI recherchiert aktuelle Produkte und Preise mit Quelle
4. JOSHI baut, lädt die Anwendung im Browser, bedient und prüft sie, repariert Fehler selbst

Danach einfach schreiben, was anders sein soll. Nützliche Sätze:

| Du schreibst | JOSHI macht |
|---|---|
| „versuch es erneut“ | weiterer Versuch mit demselben Auftrag |
| „lass X drin“ / „X machen wir später“ | nimmt einen Punkt zurück |
| „nimm X wieder auf“ | holt einen zurückgestellten Punkt zurück |
| „verwirf die Änderung“ | beendet den offenen Auftrag, die aktive Version bleibt |

Jede Änderung wird eine neue Version; **Rückgängig** holt die vorige zurück.

## Aktualisieren

```bash
git pull
```

Danach `start.command` doppelklicken – es erkennt geänderte Dateien und richtet den Dienst neu
ein. Deine Daten bleiben unberührt.

## Sichern und Umziehen

Alle Daten liegen in einem Ordner:

```text
~/Library/Application Support/MiniLLM/data
```

Zum Sichern diesen Ordner kopieren (vorher den Dienst mit `uninstall-24-7.command` stoppen
oder kurz warten, bis nichts läuft). Zum Umziehen den Ordner auf dem neuen Mac an dieselbe
Stelle legen und `start.command` starten.

Eine zweite, getrennte Installation auf demselben Mac:

```bash
MINI_LLM_DATA_DIR=~/mini-llm-test ./start.sh
```

## Deinstallieren

```bash
./uninstall-24-7.command                                   # Dienst entfernen
rm -rf ~/Library/Application\ Support/MiniLLM              # Programmkopie und ALLE Daten löschen
```

Ollama und die Modelle entfernst du über die Ollama-App bzw. `ollama rm <modell>`.

## Probleme lösen

| Problem | Lösung |
|---|---|
| „Python 3.10 oder neuer wurde nicht gefunden“ | `brew install python@3.12`, dann erneut starten |
| Modellauswahl ist leer | Ollama-App öffnen, `ollama pull gemma3:4b` |
| „Ollama nicht erreichbar“ | Ollama-App starten bzw. `ollama serve` im Terminal |
| Seite lädt nicht | Protokoll ansehen: `~/Library/Application Support/MiniLLM/logs/webui-error.log` |
| Nach einem Update sieht die Oberfläche alt aus | Seite neu laden (Cmd+Shift+R) |
| Passwort vergessen | `.env` im Projektordner enthält das Startpasswort des ersten Nutzers; sonst einen neuen Nutzer anlegen |
| Lokales Modell sehr langsam / Abbruch bei großen Dateien | kleineres Modell wählen oder ein Ollama-Cloud-Modell nutzen |
| JOSHI prüft nicht im Browser | `xcode-select --install`, danach Mini LLM neu starten |
