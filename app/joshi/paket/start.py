# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Startet diese JOSHI-Anwendung im Browser – über http://localhost.

Warum nicht einfach index.html doppelklicken? Eine geöffnete Datei meldet sich
beim lokalen KI-Modell (Ollama) ohne Herkunft an und wird abgelehnt. Über
http://localhost lässt Ollama die Anwendung ab Werk zu. Der Server ist nur auf
diesem Rechner erreichbar (127.0.0.1) und liefert nur die Dateien dieses Ordners.
Beenden: Fenster schließen oder Strg+C.
"""
import functools
import http.server
import os
import socket
import threading
import webbrowser

ORDNER = os.path.dirname(os.path.abspath(__file__))


def freier_port() -> int:
    for port in range(8790, 8890):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("Kein freier Port zwischen 8790 und 8889 gefunden.")


class Leise(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main() -> None:
    port = freier_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Leise, directory=ORDNER))
    adresse = f"http://localhost:{port}/index.html"
    print(f"Die Anwendung läuft: {adresse}")
    print("KI-Funktionen nutzen das lokale Ollama (http://localhost:11434).")
    print("Zum Beenden dieses Fenster schließen oder Strg+C drücken.")
    threading.Timer(0.8, webbrowser.open, [adresse]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
