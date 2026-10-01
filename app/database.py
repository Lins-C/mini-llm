# Mini LLM – powered by AI-Implements · C. Lins
# Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
# Dieser Code darf frei verwendet, verändert und erweitert werden.
# Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
from __future__ import annotations

import hashlib
import json
import os
import sys
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = (
    Path.home() / "Library" / "Application Support" / "MiniLLM" / "data"
    if os.uname().sysname == "Darwin"
    else ROOT / "data"
)
# Tests schreiben nie in die echten Daten: Läuft unittest ohne eigenen
# MINI_LLM_DATA_DIR, bekommt es einen Wegwerf-Ordner. (Gefunden am 29.09.2026:
# ein Testlauf ohne Variable legte rund 100 Test-Aufträge in der Live-Datenbank an.)
if not os.getenv("MINI_LLM_DATA_DIR") and (
        "unittest" in (sys.argv[0] if sys.argv else "") or "pytest" in (sys.argv[0] if sys.argv else "")):
    import tempfile
    os.environ["MINI_LLM_DATA_DIR"] = tempfile.mkdtemp(prefix="minillm-test-")
DATA_DIR = Path(os.path.expanduser(os.getenv("MINI_LLM_DATA_DIR", str(DEFAULT_DATA_DIR))))
DATA_DIR.mkdir(parents=True, exist_ok=True)
try:
    os.chmod(DATA_DIR, 0o700)
except OSError:
    pass
DB_PATH = DATA_DIR / "mini-llm.sqlite3"

SESSION_DAYS = int(os.getenv("SESSION_DAYS", "365"))
ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").lower() in {"1", "true", "yes", "on"}
MAX_WORKSPACE_BYTES = int(os.getenv("MAX_WORKSPACE_MB", "30")) * 1024 * 1024
MAX_PROFILE_BYTES = int(os.getenv("MAX_PROFILE_KB", "64")) * 1024

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=15)
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_login_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);

            CREATE TABLE IF NOT EXISTS workspaces (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            -- Jeder Chat steht für sich. Früher lag der gesamte Bereich in
            -- einem einzigen Datensatz: Jede Änderung schrieb alle Chats neu,
            -- und der Browser musste sie alle laden.
            CREATE TABLE IF NOT EXISTS chats (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                chat_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                summary TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );
            CREATE INDEX IF NOT EXISTS chats_user_updated ON chats(user_id, updated_at);

            -- Ordner, Reihenfolge und der zuletzt geöffnete Chat.
            CREATE TABLE IF NOT EXISTS workspace_meta (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            -- Sitzungen des früheren Coding-Harness (durch JOSHI ersetzt). Die
            -- Tabelle bleibt, damit vorhandene Daten nicht verloren gehen.
            CREATE TABLE IF NOT EXISTS coding_sessions (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_id TEXT NOT NULL,
                project_path TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, session_id)
            );
            CREATE INDEX IF NOT EXISTS coding_sessions_user ON coding_sessions(user_id, updated_at);

            CREATE TABLE IF NOT EXISTS user_contexts (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                context_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, context_id)
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                payload TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
    for database_file in (DB_PATH, DB_PATH.with_name(f"{DB_PATH.name}-wal"), DB_PATH.with_name(f"{DB_PATH.name}-shm")):
        if database_file.exists():
            try:
                os.chmod(database_file, 0o600)
            except OSError:
                pass


def user_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def create_user(name: str, email: str, password: str) -> dict[str, Any]:
    name = " ".join(name.split()).strip()[:80]
    email = email.strip().lower()[:254]
    if not name:
        raise ValueError("Bitte einen Namen eingeben.")
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("Bitte eine gültige E-Mail-Adresse eingeben.")
    if len(password) < 6:
        raise ValueError("Das Passwort muss mindestens 6 Zeichen lang sein.")

    user_id = str(uuid.uuid4())
    now = int(time.time())
    try:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO users (id, name, email, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name, email, password_hasher.hash(password), now),
            )
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Für diese E-Mail-Adresse existiert bereits ein Nutzer.") from exc
    assert row is not None
    return user_payload(row)


def ensure_bootstrap_user() -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute("SELECT * FROM users ORDER BY created_at LIMIT 1").fetchone()
    if row is not None:
        return user_payload(row)
    # Nie ein festes Standardpasswort (30.09.2026: „bitte-sofort-aendern“ hätte öffentlich auf
    # GitHub gestanden). Ohne BOOTSTRAP_USER_PASSWORD entsteht ein zufälliges Passwort, das nur
    # im Protokoll und in einer nur für den Besitzer lesbaren Datei im Datenordner steht.
    passwort = os.getenv("BOOTSTRAP_USER_PASSWORD", "").strip()
    email = os.getenv("BOOTSTRAP_USER_EMAIL", "admin@minillm.local").strip() or "admin@minillm.local"
    if not passwort:
        passwort = secrets.token_urlsafe(12)
        datei = DATA_DIR / "erstes-passwort.txt"
        try:
            datei.write_text(f"Erster Nutzer: {email}\nPasswort: {passwort}\n"
                             "Nach der ersten Anmeldung ändern und diese Datei löschen.\n", encoding="utf-8")
            os.chmod(datei, 0o600)
        except OSError:
            pass
        print(f"[Mini LLM] Erster Nutzer angelegt: {email} · Passwort: {passwort} "
              f"(auch in {datei})", file=sys.stderr, flush=True)
    return create_user(os.getenv("BOOTSTRAP_USER_NAME", "Admin").strip() or "Admin", email, passwort)


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
            (email.strip().lower(),),
        ).fetchone()
    if row is None:
        return None
    try:
        password_hasher.verify(row["password_hash"], password)
    except VerifyMismatchError:
        return None
    if password_hasher.check_needs_rehash(row["password_hash"]):
        with connect() as connection:
            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (password_hasher.hash(password), row["id"]),
            )
    with connect() as connection:
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (int(time.time()), row["id"]),
        )
    return user_payload(row)


def create_session(user_id: str) -> tuple[str, int]:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    expires_at = now + SESSION_DAYS * 86400
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, now, expires_at),
        )
    return token, expires_at


def get_user_for_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = int(time.time())
    with connect() as connection:
        row = connection.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    return user_payload(row) if row is not None else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def _empty_profile(name: str = "", email: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "birth_date": "",
        "email": email,
        "phone": "",
        "occupation": "",
        "organization": "",
        "address": {
            "street": "",
            "postal_code": "",
            "city": "",
            "country": "",
        },
        "bio": "",
        "family": "",
        "pets": "",
        "important_details": "",
        "global_persona": "",
    }


def load_profile(user_id: str) -> tuple[bool, dict[str, Any]]:
    with connect() as connection:
        user = connection.execute(
            "SELECT name, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        row = connection.execute(
            "SELECT payload FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    profile = _empty_profile(
        str(user["name"]) if user is not None else "",
        str(user["email"]) if user is not None else "",
    )
    if row is None:
        return False, profile
    try:
        stored = json.loads(row["payload"])
    except json.JSONDecodeError:
        stored = {}
    if isinstance(stored, dict):
        for key in profile:
            if key == "address":
                address = stored.get("address")
                if isinstance(address, dict):
                    profile["address"].update({
                        field: str(address.get(field) or "")
                        for field in profile["address"]
                    })
            elif key in stored:
                profile[key] = str(stored.get(key) or "")
    return True, profile


def save_profile(user_id: str, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PROFILE_BYTES:
        raise ValueError("Das persönliche Profil ist zu groß.")
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO user_profiles (user_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (user_id, encoded, int(time.time())),
        )


def load_workspace(user_id: str) -> tuple[bool, dict[str, Any]]:
    with connect() as connection:
        row = connection.execute(
            "SELECT payload FROM workspaces WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return False, {"folders": [], "chats": [], "activeChatId": None}
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        payload = {}
    return True, payload if isinstance(payload, dict) else {}


def _context_ids_from_workspace(payload: dict[str, Any]) -> set[str]:
    context_ids: set[str] = set()
    chats = payload.get("chats")
    if not isinstance(chats, list):
        return context_ids
    for chat in chats[:1000]:
        if not isinstance(chat, dict):
            continue
        ids = chat.get("contextIds")
        if not isinstance(ids, list):
            continue
        for context_id in ids:
            if isinstance(context_id, str) and len(context_id) == 64:
                context_ids.add(context_id)
    return context_ids


# Diese beiden Felder machen fast den gesamten Umfang eines Chats aus. Sie
# bleiben auf dem Mac liegen, bis der Chat wirklich geöffnet wird.
SCHWERE_FELDER = ("messages", "history")


def chat_summary(chat: dict[str, Any]) -> dict[str, Any]:
    """Der Chat ohne Inhalt — gerade genug für die Liste in der Seitenleiste."""
    summary = {key: value for key, value in chat.items() if key not in SCHWERE_FELDER}
    messages = chat.get("messages")
    messages = messages if isinstance(messages, list) else []
    summary["messageCount"] = len(messages)
    # Läuft in einem geschlossenen Chat noch eine Antwort, muss der Browser
    # davon erfahren, ohne den ganzen Chat zu laden.
    summary["pendingRequestIds"] = [
        message["requestId"]
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "assistant"
        and message.get("status") == "generating"
        and isinstance(message.get("requestId"), str)
        and message["requestId"]
    ]
    return summary


def _write_chat(connection: sqlite3.Connection, user_id: str, chat: dict[str, Any]) -> None:
    chat_id = chat.get("id")
    if not isinstance(chat_id, str) or not chat_id:
        raise ValueError("Der Chat hat keine gültige Kennung.")
    encoded = json.dumps(chat, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_WORKSPACE_BYTES:
        raise ValueError("Der gespeicherte Chat ist zu groß.")
    connection.execute(
        """
        INSERT INTO chats (user_id, chat_id, payload, summary, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            payload = excluded.payload,
            summary = excluded.summary,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            chat_id,
            encoded,
            json.dumps(chat_summary(chat), ensure_ascii=False, separators=(",", ":")),
            int(time.time()),
        ),
    )


def _migrate_workspace(connection: sqlite3.Connection, user_id: str) -> bool:
    """Überführt einen alten Gesamtdatensatz einmalig in einzelne Chats.

    Der alte Datensatz bleibt unangetastet stehen — als Rückfallebene.
    """
    row = connection.execute(
        "SELECT payload FROM workspaces WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return False
    try:
        payload = json.loads(row["payload"])
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    chats = payload.get("chats")
    reihenfolge = []
    for chat in chats if isinstance(chats, list) else []:
        if not isinstance(chat, dict) or not isinstance(chat.get("id"), str):
            continue
        _write_chat(connection, user_id, chat)
        reihenfolge.append(chat["id"])
    connection.execute(
        """
        INSERT INTO workspace_meta (user_id, payload, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            payload = excluded.payload, updated_at = excluded.updated_at
        """,
        (
            user_id,
            json.dumps(
                {
                    "folders": payload.get("folders") or [],
                    "activeChatId": payload.get("activeChatId"),
                    "order": reihenfolge,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            int(time.time()),
        ),
    )
    return True


def load_workspace_index(user_id: str) -> tuple[bool, dict[str, Any]]:
    """Ordner und Chatliste ohne Nachrichten."""
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        meta_row = connection.execute(
            "SELECT payload FROM workspace_meta WHERE user_id = ?", (user_id,)
        ).fetchone()
        if meta_row is None:
            _migrate_workspace(connection, user_id)
            meta_row = connection.execute(
                "SELECT payload FROM workspace_meta WHERE user_id = ?", (user_id,)
            ).fetchone()
        zusammenfassungen = connection.execute(
            "SELECT chat_id, summary FROM chats WHERE user_id = ?", (user_id,)
        ).fetchall()
    if meta_row is None and not zusammenfassungen:
        return False, {"folders": [], "chats": [], "activeChatId": None}
    try:
        # Ein Chat kann auch ohne Gliederungsdatensatz vorliegen; dann zählt er
        # trotzdem — verschwiegen würde er sonst.
        meta = json.loads(meta_row["payload"]) if meta_row is not None else {}
    except json.JSONDecodeError:
        meta = {}
    nach_id: dict[str, Any] = {}
    for zeile in zusammenfassungen:
        try:
            nach_id[zeile["chat_id"]] = json.loads(zeile["summary"])
        except json.JSONDecodeError:
            continue
    reihenfolge = [kennung for kennung in meta.get("order") or [] if kennung in nach_id]
    reihenfolge += [kennung for kennung in nach_id if kennung not in reihenfolge]
    return True, {
        "folders": meta.get("folders") or [],
        "activeChatId": meta.get("activeChatId"),
        "chats": [nach_id[kennung] for kennung in reihenfolge],
        "lazy": True,
    }


def load_chat(user_id: str, chat_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT payload FROM chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
    if row is None:
        return None
    try:
        chat = json.loads(row["payload"])
    except json.JSONDecodeError:
        return None
    return chat if isinstance(chat, dict) else None


def save_chat(user_id: str, chat: dict[str, Any]) -> None:
    with connect() as connection:
        _write_chat(connection, user_id, chat)
        for context_id in _context_ids_from_workspace({"chats": [chat]}):
            connection.execute(
                """
                INSERT OR IGNORE INTO user_contexts (user_id, context_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, context_id, int(time.time())),
            )


def delete_chat(user_id: str, chat_id: str) -> None:
    with connect() as connection:
        connection.execute(
            "DELETE FROM chats WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)
        )


def save_workspace_meta(user_id: str, meta: dict[str, Any]) -> None:
    """Ordner, Reihenfolge und offener Chat — ohne die Chats selbst."""
    schlank = {
        "folders": meta.get("folders") or [],
        "activeChatId": meta.get("activeChatId"),
        "order": [
            kennung for kennung in (meta.get("order") or []) if isinstance(kennung, str)
        ],
    }
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO workspace_meta (user_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload, updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(schlank, ensure_ascii=False, separators=(",", ":")),
                int(time.time()),
            ),
        )


def save_workspace(user_id: str, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_WORKSPACE_BYTES:
        raise ValueError("Der gespeicherte Chatbereich ist zu groß.")
    now = int(time.time())
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO workspaces (user_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (user_id, encoded, now),
        )
        for context_id in _context_ids_from_workspace(payload):
            connection.execute(
                """
                INSERT OR IGNORE INTO user_contexts (user_id, context_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, context_id, now),
            )


def update_workspace_chat_job(
    user_id: str,
    chat_id: str,
    assistant_message_id: str,
    request_id: str,
    message_patch: dict[str, Any],
    context_ids: list[str] | None = None,
    user_message_id: str = "",
) -> bool:
    """Merge a completed background job into the latest persisted workspace.

    The browser owns the general workspace layout. A background LLM job only
    updates its own assistant message and newly created attachment contexts so
    a disconnected browser cannot accidentally lose the completed answer.
    """
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload FROM chats WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        ).fetchone()
        if row is None:
            # Ein Bereich, der noch nicht aufgeteilt wurde, wird jetzt aufgeteilt.
            if not _migrate_workspace(connection, user_id):
                return False
            row = connection.execute(
                "SELECT payload FROM chats WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            ).fetchone()
            if row is None:
                return False
        try:
            chat = json.loads(row["payload"])
        except json.JSONDecodeError:
            return False
        if not isinstance(chat, dict):
            return False
        messages = chat.get("messages")
        if not isinstance(messages, list):
            return False
        assistant = next(
            (
                item for item in messages
                if isinstance(item, dict) and item.get("id") == assistant_message_id
            ),
            None,
        )
        if assistant is None:
            return False
        stored_request_id = str(assistant.get("requestId") or "")
        if stored_request_id and stored_request_id != request_id:
            return False

        allowed_fields = {
            "content",
            "status",
            "errorMessage",
            "doneReason",
            "usage",
            "artifact",
            "model",
            "requestId",
        }
        assistant.update({
            key: value for key, value in message_patch.items()
            if key in allowed_fields
        })

        valid_context_ids = [
            value for value in (context_ids or [])
            if isinstance(value, str) and len(value) == 64
        ]
        if valid_context_ids:
            chat["contextIds"] = list(dict.fromkeys([
                *(
                    value for value in chat.get("contextIds", [])
                    if isinstance(value, str)
                ),
                *valid_context_ids,
            ]))
            if user_message_id:
                user_message = next(
                    (
                        item for item in messages
                        if isinstance(item, dict) and item.get("id") == user_message_id
                    ),
                    None,
                )
                if user_message is not None:
                    user_message["attachmentContextIds"] = list(dict.fromkeys([
                        *(
                            value for value in user_message.get("attachmentContextIds", [])
                            if isinstance(value, str)
                        ),
                        *valid_context_ids,
                    ]))

        history: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            if (
                role == "assistant"
                and message.get("status") == "error"
                and content.startswith("Fehler:")
            ):
                continue
            history.append({"role": role, "content": content})
        chat["history"] = history
        chat["updatedAt"] = int(time.time() * 1000)

        _write_chat(connection, user_id, chat)
        for context_id in valid_context_ids:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_contexts (user_id, context_id, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, context_id, int(time.time())),
            )
    return True


def grant_context(user_id: str, context_id: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO user_contexts (user_id, context_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, context_id, int(time.time())),
        )


def allowed_context_ids(user_id: str, context_ids: list[str]) -> list[str]:
    if not context_ids:
        return []
    placeholders = ",".join("?" for _ in context_ids[:80])
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT context_id FROM user_contexts
            WHERE user_id = ? AND context_id IN ({placeholders})
            """,
            (user_id, *context_ids[:80]),
        ).fetchall()
    allowed = {row["context_id"] for row in rows}
    return [context_id for context_id in context_ids if context_id in allowed]
