# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Die Schnittstelle, über die JOSHI Modelle nutzt.

JOSHI spricht nie selbst mit Ollama. Mini LLM reicht beim Start einen
Modellzugang herein (siehe app/main.py: MiniLLMModellzugang), der die zentrale
Modellschicht verwendet — dieselbe Adresse, dieselben Wiederholungen,
dasselbe Kontextfenster, dieselben Fehlermeldungen wie der Chat. Ein anderer
Anbieter oder ein Routing nach Fähigkeiten tauscht nur diesen Zugang aus.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class Modellzugang(Protocol):
    async def strukturiert(self, modell: str, nachrichten: list[dict[str, Any]], schema: dict[str, Any], *,
                           temperatur: float, verbrauch: dict[str, int]) -> Any:
        """Eine JSON-Antwort nach Schema (nicht streamend)."""

    def strom(self, modell: str, nachrichten: list[dict[str, Any]], *, temperatur: float,
              verbrauch: dict[str, int]) -> AsyncIterator[dict[str, Any]]:
        """Streamt {"text": …}, {"denken": n} und zum Schluss {"ende": done_reason}."""

    async def faehigkeiten(self, modell: str) -> set[str]:
        """Zum Beispiel {"completion", "vision"}; leer, wenn unbekannt."""

    def fenster(self, modell: str) -> int:
        """Kontextfenster in Tokens, mit dem JOSHI für dieses Modell rechnen darf."""


class ModellFehler(RuntimeError):
    """Verständliche Meldung der Modellschicht (Limit erreicht, nicht angemeldet …)."""
