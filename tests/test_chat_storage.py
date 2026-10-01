# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
"""Chats liegen einzeln auf dem Mac und werden einzeln gelesen und geschrieben."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database
from app.database import (
    chat_summary,
    connect,
    delete_chat,
    init_db,
    load_chat,
    load_workspace_index,
    save_chat,
    save_workspace_meta,
    update_workspace_chat_job,
)


def beispielchat(kennung: str, titel: str, nachrichten: int = 2) -> dict:
    return {
        "id": kennung,
        "title": titel,
        "folderId": None,
        "updatedAt": 1,
        "messages": [
            {"id": f"{kennung}-{nummer}", "role": "user" if nummer % 2 == 0 else "assistant",
             "content": "Inhalt " * 50, "status": "done"}
            for nummer in range(nachrichten)
        ],
        "history": [{"role": "user", "content": "Inhalt"}],
    }


class Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        datenordner = Path(self.temp.name) / "data"
        datenordner.mkdir()
        self.db_patches = [
            patch.object(database, "DATA_DIR", datenordner),
            patch.object(database, "DB_PATH", datenordner / "mini-llm.sqlite3"),
        ]
        for db_patch in self.db_patches:
            db_patch.start()
        init_db()
        self.user_id = "pruefnutzer"
        with connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO users (id, name, email, password_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.user_id, "Prüfung", f"{self.user_id}@example.invalid", "x", 0),
            )
            connection.execute("DELETE FROM chats WHERE user_id = ?", (self.user_id,))
            connection.execute("DELETE FROM workspace_meta WHERE user_id = ?", (self.user_id,))
            connection.execute("DELETE FROM workspaces WHERE user_id = ?", (self.user_id,))

    def tearDown(self) -> None:
        for db_patch in reversed(self.db_patches):
            db_patch.stop()
        self.temp.cleanup()


class ChatStorageTests(Grundlage):
    def test_the_index_carries_no_messages(self):
        save_chat(self.user_id, beispielchat("a", "Erster", nachrichten=6))
        save_workspace_meta(self.user_id, {"folders": [], "activeChatId": "a", "order": ["a"]})

        _, index = load_workspace_index(self.user_id)
        eintrag = index["chats"][0]
        self.assertNotIn("messages", eintrag)
        self.assertNotIn("history", eintrag, "Der Verlauf ist genauso schwer wie die Nachrichten.")
        self.assertEqual(eintrag["messageCount"], 6)
        self.assertEqual(eintrag["title"], "Erster")

    def test_the_full_chat_is_fetched_separately(self):
        save_chat(self.user_id, beispielchat("a", "Erster", nachrichten=4))
        voll = load_chat(self.user_id, "a")
        self.assertEqual(len(voll["messages"]), 4)
        self.assertIsNone(load_chat(self.user_id, "gibtesnicht"))

    def test_saving_one_chat_leaves_the_others_untouched(self):
        save_chat(self.user_id, beispielchat("a", "Erster"))
        save_chat(self.user_id, beispielchat("b", "Zweiter"))
        vorher = load_chat(self.user_id, "b")

        geaendert = beispielchat("a", "Erster, geändert", nachrichten=8)
        save_chat(self.user_id, geaendert)

        self.assertEqual(load_chat(self.user_id, "b"), vorher)
        self.assertEqual(len(load_chat(self.user_id, "a")["messages"]), 8)

    def test_a_deleted_chat_is_gone(self):
        save_chat(self.user_id, beispielchat("a", "Erster"))
        delete_chat(self.user_id, "a")
        self.assertIsNone(load_chat(self.user_id, "a"))

    def test_the_order_of_the_sidebar_survives(self):
        for kennung in ("a", "b", "c"):
            save_chat(self.user_id, beispielchat(kennung, kennung.upper()))
        save_workspace_meta(
            self.user_id, {"folders": [], "activeChatId": "b", "order": ["c", "a", "b"]}
        )
        _, index = load_workspace_index(self.user_id)
        self.assertEqual([eintrag["id"] for eintrag in index["chats"]], ["c", "a", "b"])
        self.assertEqual(index["activeChatId"], "b")

    def test_a_chat_missing_from_the_order_still_appears(self):
        save_chat(self.user_id, beispielchat("a", "A"))
        save_chat(self.user_id, beispielchat("neu", "Neu"))
        save_workspace_meta(self.user_id, {"folders": [], "activeChatId": "a", "order": ["a"]})
        _, index = load_workspace_index(self.user_id)
        self.assertEqual({eintrag["id"] for eintrag in index["chats"]}, {"a", "neu"})

    def test_an_open_job_is_visible_without_loading_the_chat(self):
        chat = beispielchat("a", "Läuft")
        chat["messages"].append(
            {"id": "m9", "role": "assistant", "content": "", "status": "generating",
             "requestId": "auftrag-1"}
        )
        save_chat(self.user_id, chat)
        _, index = load_workspace_index(self.user_id)
        self.assertEqual(index["chats"][0]["pendingRequestIds"], ["auftrag-1"])

    def test_the_summary_of_a_chat_without_messages_is_harmless(self):
        kurz = chat_summary({"id": "a", "title": "Leer"})
        self.assertEqual(kurz["messageCount"], 0)
        self.assertEqual(kurz["pendingRequestIds"], [])


class WorkspaceMigrationTests(Grundlage):
    """Ein vorhandener Gesamtdatensatz wird beim ersten Zugriff aufgeteilt."""

    def altbestand(self, chats: int = 3) -> dict:
        payload = {
            "folders": [{"id": "o1", "name": "Ordner"}],
            "activeChatId": "chat-1",
            "chats": [beispielchat(f"chat-{n}", f"Chat {n}", nachrichten=4) for n in range(chats)],
        }
        with connect() as connection:
            connection.execute(
                "INSERT INTO workspaces (user_id, payload, updated_at) VALUES (?, ?, ?)",
                (self.user_id, json.dumps(payload), 0),
            )
        return payload

    def test_the_old_record_is_split_into_single_chats(self):
        alt = self.altbestand()
        exists, index = load_workspace_index(self.user_id)

        self.assertTrue(exists)
        self.assertEqual(len(index["chats"]), 3)
        self.assertEqual(index["folders"], alt["folders"])
        self.assertEqual(index["activeChatId"], "chat-1")
        for original in alt["chats"]:
            self.assertEqual(
                load_chat(self.user_id, original["id"])["messages"], original["messages"]
            )

    def test_the_old_record_stays_as_a_fallback(self):
        self.altbestand()
        load_workspace_index(self.user_id)
        with connect() as connection:
            uebrig = connection.execute(
                "SELECT count(*) FROM workspaces WHERE user_id = ?", (self.user_id,)
            ).fetchone()[0]
        self.assertEqual(uebrig, 1, "Der alte Bestand ist die Rückfallebene.")

    def test_the_split_happens_only_once(self):
        self.altbestand()
        load_workspace_index(self.user_id)
        save_chat(self.user_id, beispielchat("chat-1", "Umbenannt", nachrichten=9))
        _, index = load_workspace_index(self.user_id)
        eintrag = next(e for e in index["chats"] if e["id"] == "chat-1")
        self.assertEqual(eintrag["title"], "Umbenannt", "Die Umstellung lief ein zweites Mal.")
        self.assertEqual(eintrag["messageCount"], 9)


class BackgroundJobTests(Grundlage):
    """Eine Antwort im Hintergrund schreibt nur ihren eigenen Chat."""

    def test_a_finished_job_updates_only_its_own_chat(self):
        chat = beispielchat("a", "Mit Auftrag")
        chat["messages"].append(
            {"id": "m9", "role": "assistant", "content": "", "status": "generating",
             "requestId": "auftrag-1"}
        )
        save_chat(self.user_id, chat)
        save_chat(self.user_id, beispielchat("b", "Unbeteiligt"))
        unbeteiligt = load_chat(self.user_id, "b")

        erfolg = update_workspace_chat_job(
            self.user_id, "a", "m9", "auftrag-1",
            {"content": "Fertige Antwort", "status": "done"},
        )

        self.assertTrue(erfolg)
        aktualisiert = load_chat(self.user_id, "a")
        letzte = aktualisiert["messages"][-1]
        self.assertEqual(letzte["content"], "Fertige Antwort")
        self.assertEqual(letzte["status"], "done")
        self.assertEqual(load_chat(self.user_id, "b"), unbeteiligt)

    def test_a_job_for_an_unknown_chat_changes_nothing(self):
        self.assertFalse(
            update_workspace_chat_job(
                self.user_id, "gibtesnicht", "m", "auftrag", {"content": "x"}
            )
        )


if __name__ == "__main__":
    unittest.main()
