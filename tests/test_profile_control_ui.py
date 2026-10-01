# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ProfileControlUiTests(unittest.TestCase):
    def test_control_center_uses_unclipped_portal(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("document.body.append(controlCenter)", javascript)
        self.assertIn('controlCenter.classList.add("is-portal")', javascript)
        self.assertIn("positionControlCenter()", javascript)
        self.assertIn("controlCenterHost.append(controlCenter)", javascript)
        self.assertRegex(
            styles,
            r"\.control-center\s*\{[^}]*position:\s*fixed",
        )

    def test_profile_action_still_opens_profile_dialog(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="open-profile"', markup)
        self.assertIn('id="profile-dialog"', markup)
        self.assertIn(
            '$("#open-profile").addEventListener("click", () => {',
            javascript,
        )
        self.assertIn("openProfileDialog();", javascript)

class OllamaConnectionUiTests(unittest.TestCase):
    """Startet Ollama nach der Oberfläche, muss die Anzeige nachziehen."""

    def test_the_model_list_retries_until_ollama_answers(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("scheduleModelRetry()", javascript)
        self.assertIn("stopModelRetry()", javascript)
        # Der Fehlerzweig plant nach, der Erfolgszweig beendet die Nachprüfung.
        misserfolg = javascript.index('Ollama nicht erreichbar</option>')
        self.assertIn("scheduleModelRetry()", javascript[misserfolg:misserfolg + 400])

    def test_the_connection_badge_can_be_clicked_to_recheck(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('$("#connection").addEventListener("click"', javascript)
        self.assertIn('title="Verbindung erneut prüfen"', markup)

    def test_the_asset_version_was_raised_with_the_change(self):
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("app.js?v=42", markup, "Sonst liefert der Browser die alte Datei.")

class BootResilienceTests(unittest.TestCase):
    """Ein gescheiterter Startschritt darf die übrigen nicht mitreißen."""

    def test_every_boot_step_runs_on_its_own(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        start = javascript.index("async function completeAuthentication")
        block = javascript[start:start + 900]

        self.assertNotIn("await loadProfile();", block, "Die alte starre Kette ist zurück.")
        self.assertNotIn("await loadUserWorkspace();", block)
        self.assertIn('bootSchritt("die Modellliste", loadModels)', block)
        # Die Modelle müssen auch dann geladen werden, wenn Profil oder Chats
        # scheitern — sonst bleibt die Anzeige auf „Prüfe Ollama" stehen.
        self.assertLess(
            block.index('bootSchritt("deine Chats"'),
            block.index('bootSchritt("die Modellliste"'),
        )

    def test_a_failed_chat_load_is_not_shown_as_empty(self):
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("state.workspaceError", javascript)
        leer = javascript.index("Noch keine Chats vorhanden.")
        umgebung = javascript[leer - 400:leer + 200]
        self.assertIn("konnten nicht geladen werden", umgebung)
        self.assertIn("workspace-retry", umgebung)

class LazyChatLoadingTests(unittest.TestCase):
    """Nachrichten liegen auf dem Mac und kommen erst beim Öffnen."""

    def javascript(self) -> str:
        return (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    def test_the_browser_copy_of_all_chats_is_gone(self):
        javascript = self.javascript()
        self.assertNotIn("workspaceSnapshot", javascript)
        self.assertNotIn("cacheWorkspace", javascript)
        self.assertNotIn("userStorageKey", javascript)

    def test_opening_a_chat_fetches_it(self):
        javascript = self.javascript()
        self.assertIn("function ensureChatMessages(", javascript)
        self.assertIn("`/api/chats/${encodeURIComponent(conversation.id)}`", javascript)
        start = javascript.index("function renderActiveChat()")
        self.assertIn("ensureChatMessages(item)", javascript[start:start + 800])

    def test_saving_writes_one_chat_not_all(self):
        javascript = self.javascript()
        start = javascript.index("async function persistWorkspace()")
        block = javascript[start:start + 1800]
        self.assertIn('method: "PUT"', block)
        self.assertIn("`/api/chats/${encodeURIComponent(kennung)}`", block)
        self.assertNotIn("chats: state.chats", block, "Das wären wieder alle Chats auf einmal.")

    def test_the_layout_request_carries_no_messages(self):
        javascript = self.javascript()
        start = javascript.index('await fetch("/api/workspace"')
        block = javascript[start:start + 400]
        self.assertIn("order: state.chats.map((item) => item.id)", block)
        self.assertNotIn("chats:", block)

    def test_a_deleted_chat_is_removed_on_the_mac(self):
        javascript = self.javascript()
        self.assertIn("function forgetChat(", javascript)
        start = javascript.index("function forgetChat(")
        self.assertIn('method: "DELETE"', javascript[start:start + 300])

    def test_a_chat_with_a_running_answer_is_fetched_at_startup(self):
        javascript = self.javascript()
        start = javascript.index("async function loadUserWorkspace()")
        block = javascript[start:start + 1600]
        self.assertIn("pendingRequestIds", block)
        self.assertIn("ensureChatMessages(item)", block)


if __name__ == "__main__":
    unittest.main()
