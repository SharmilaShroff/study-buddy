"""Database abstraction layer — MySQL (local) / SQLite (cloud) dual support.

When MySQL is available and configured, the app uses MySQL.
Otherwise it falls back transparently to a local SQLite database,
enabling deployment on Streamlit Cloud without a managed MySQL instance.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager

from app.core.config import settings

# ── Try importing mysql-connector ──
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError

    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False
    MySQLError = Exception  # type: ignore[misc,assignment]

# ── Detect database mode ──
_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "studybuddy.db",
)


def _detect_db_mode() -> str:
    """Return 'mysql' if a MySQL connection can be established, else 'sqlite'."""
    if not HAS_MYSQL or not settings.mysql_password:
        return "sqlite"
    try:
        conn = mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
        )
        conn.close()
        return "mysql"
    except Exception:
        return "sqlite"


DB_MODE: str = _detect_db_mode()


# ═══════════════════════════════════════════════════════════════
#  SQLite Helpers
# ═══════════════════════════════════════════════════════════════

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    preferred_mode TEXT DEFAULT 'Student Mode',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS otp_verification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    is_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notebooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'Untitled notebook',
    emoji TEXT DEFAULT '📓',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notebook_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notebook_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_value TEXT NOT NULL,
    extracted_text TEXT,
    word_count INTEGER DEFAULT 0,
    is_enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notebook_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    cited_sources TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notebook_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notebook_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'New note',
    content TEXT NOT NULL,
    note_type TEXT DEFAULT 'manual',
    is_pinned INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notebook_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    notebook_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS uploaded_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_value TEXT NOT NULL,
    extracted_text TEXT,
    topic TEXT DEFAULT '',
    is_public INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generated_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    output_type TEXT NOT NULL,
    content TEXT NOT NULL,
    difficulty_level TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS quiz_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    score INTEGER NOT NULL,
    total_questions INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    action_name TEXT NOT NULL,
    action_details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leaderboard (
    user_id INTEGER PRIMARY KEY,
    total_score INTEGER NOT NULL DEFAULT 0,
    games_played INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS public_textbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    textbook_name TEXT NOT NULL,
    topic TEXT DEFAULT '',
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES uploaded_sources(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    likes_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS community_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES community_posts(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS study_rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    room_name TEXT NOT NULL,
    room_code TEXT NOT NULL UNIQUE,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS study_room_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES study_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (room_id, user_id)
);

CREATE TABLE IF NOT EXISTS study_room_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES study_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exam_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    year TEXT DEFAULT '',
    question_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS predicted_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    predicted_question TEXT NOT NULL,
    confidence TEXT DEFAULT 'Medium',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS study_room_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT DEFAULT '',
    file_data BLOB,
    file_text TEXT,
    file_size INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES study_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS study_room_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT 'Shared Note',
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES study_rooms(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _init_sqlite():
    """Create the SQLite database and all tables if they don't exist."""
    conn = sqlite3.connect(_SQLITE_PATH)
    conn.executescript(_SQLITE_SCHEMA)
    conn.commit()
    conn.close()


def _dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _translate_query(query: str) -> str:
    """Convert MySQL-style query to SQLite-compatible query."""
    # %s → ?
    q = query.replace("%s", "?")
    # NOW() → datetime('now')
    q = re.sub(r"\bNOW\(\)", "datetime('now')", q, flags=re.IGNORECASE)
    # LIKE %s already handled by %s → ?
    return q


def _translate_on_duplicate_key(query: str, params: tuple) -> tuple[str, tuple]:
    """Convert MySQL ON DUPLICATE KEY UPDATE to SQLite INSERT OR REPLACE.

    This is a simplified conversion that handles the patterns used in this app.
    Returns (translated_query, possibly_adjusted_params).
    """
    if "ON DUPLICATE KEY UPDATE" not in query.upper():
        return query, params

    # For leaderboard upsert (special case with total_score + ?)
    if "leaderboard" in query.lower() and "total_score + " in query:
        # Use INSERT OR IGNORE + separate UPDATE approach
        insert_q = """INSERT OR IGNORE INTO leaderboard (user_id, total_score, games_played) VALUES (?, ?, 1)"""
        update_q = """UPDATE leaderboard SET total_score = total_score + ?, games_played = games_played + 1 WHERE user_id = ?"""
        # Return a special marker — handled in the cursor wrapper
        return f"__LEADERBOARD_UPSERT__{insert_q}||{update_q}", params

    # For public_textbooks upsert
    if "public_textbooks" in query.lower():
        q = """INSERT OR REPLACE INTO public_textbooks
               (source_id, user_id, textbook_name, topic, content)
               VALUES (?, ?, ?, ?, ?)"""
        # Original has 8 params (5 for insert + 3 for update), we only need 5
        return q, params[:5]

    return query, params


class SQLiteCursorWrapper:
    """Wraps a SQLite cursor to provide MySQL-compatible interface."""

    def __init__(self, cursor: sqlite3.Cursor, connection: sqlite3.Connection):
        self._cursor = cursor
        self._connection = connection

    def execute(self, query: str, params: tuple | list | None = None):
        q = _translate_query(query)
        p = params or ()

        q, p = _translate_on_duplicate_key(q, p)

        # Handle special leaderboard upsert
        if q.startswith("__LEADERBOARD_UPSERT__"):
            parts = q.replace("__LEADERBOARD_UPSERT__", "").split("||")
            insert_q, update_q = parts[0], parts[1]
            # p = (user_id, score, score) from the original call
            user_id, score = p[0], p[1]
            self._cursor.execute(insert_q, (user_id, score))
            self._cursor.execute(update_q, (score, user_id))
            return

        # Handle SHOW DATABASES (not applicable in SQLite)
        if "SHOW DATABASES" in query.upper():
            self._cursor.execute("SELECT 1")
            return

        self._cursor.execute(q, p)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def close(self):
        self._cursor.close()


# ═══════════════════════════════════════════════════════════════
#  MySQL Functions (original)
# ═══════════════════════════════════════════════════════════════

def get_connection():
    if DB_MODE == "mysql":
        return mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            autocommit=False,
        )
    else:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def get_server_connection():
    if DB_MODE == "mysql":
        return mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            autocommit=True,
        )
    else:
        conn = sqlite3.connect(_SQLITE_PATH)
        conn.row_factory = _dict_factory
        return conn


def check_database_status() -> tuple[bool, str]:
    if DB_MODE == "sqlite":
        try:
            _init_sqlite()
            return True, f"SQLite database ready at {_SQLITE_PATH}"
        except Exception as exc:
            return False, f"SQLite init failed: {exc}"

    # MySQL mode
    try:
        server_connection = get_server_connection()
    except MySQLError as exc:
        return False, f"MySQL login failed: {exc}"

    try:
        cursor = server_connection.cursor()
        cursor.execute("SHOW DATABASES LIKE %s", (settings.mysql_database,))
        database_exists = cursor.fetchone() is not None
        if not database_exists:
            return (
                False,
                f"Database '{settings.mysql_database}' was not found. Run database/schema.sql first.",
            )
    finally:
        cursor.close()
        server_connection.close()

    try:
        app_connection = get_connection()
        app_connection.close()
        return True, "Database connection successful."
    except MySQLError as exc:
        return False, f"MySQL database check failed: {exc}"


@contextmanager
def db_cursor(dictionary: bool = True):
    connection = None
    cursor = None
    try:
        connection = get_connection()

        if DB_MODE == "sqlite":
            raw_cursor = connection.cursor()
            cursor = SQLiteCursorWrapper(raw_cursor, connection)
            yield connection, cursor
            connection.commit()
        else:
            cursor = connection.cursor(dictionary=dictionary)
            yield connection, cursor
            connection.commit()
    except Exception:
        if connection:
            connection.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if connection:
            try:
                connection.close()
            except Exception:
                pass
