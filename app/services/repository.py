from __future__ import annotations

import random
import string

from app.core.database import db_cursor


class NotebookRepository:
    """Data-access layer for the NotebookLM-style notebook system."""

    # ── Notebooks ──────────────────────────────────────────────

    def create_notebook(self, user_id: int, title: str = "Untitled notebook", emoji: str = "📓") -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO notebooks (user_id, title, emoji) VALUES (%s, %s, %s)",
                (user_id, title, emoji),
            )
            return cursor.lastrowid

    def rename_notebook(self, notebook_id: int, title: str) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("UPDATE notebooks SET title = %s WHERE id = %s", (title, notebook_id))

    def delete_notebook(self, notebook_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM notebooks WHERE id = %s", (notebook_id,))

    def fetch_notebooks(self, user_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT n.id, n.title, n.emoji, n.created_at, n.updated_at,
                       COUNT(ns.id) AS source_count
                FROM notebooks n
                LEFT JOIN notebook_sources ns ON ns.notebook_id = n.id
                WHERE n.user_id = %s
                GROUP BY n.id
                ORDER BY n.updated_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall()

    def get_notebook(self, notebook_id: int) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT * FROM notebooks WHERE id = %s", (notebook_id,))
            return cursor.fetchone()

    # ── Sources ────────────────────────────────────────────────

    def add_source(
        self,
        notebook_id: int,
        user_id: int,
        source_type: str,
        source_name: str,
        source_value: str,
        extracted_text: str,
    ) -> int:
        word_count = len(extracted_text.split()) if extracted_text else 0
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO notebook_sources
                (notebook_id, user_id, source_type, source_name, source_value, extracted_text, word_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (notebook_id, user_id, source_type, source_name, source_value, extracted_text, word_count),
            )
            # Touch notebook updated_at
            cursor.execute("UPDATE notebooks SET updated_at = NOW() WHERE id = %s", (notebook_id,))
            return cursor.lastrowid

    def delete_source(self, source_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM notebook_sources WHERE id = %s", (source_id,))

    def toggle_source(self, source_id: int, is_enabled: bool) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE notebook_sources SET is_enabled = %s WHERE id = %s",
                (1 if is_enabled else 0, source_id),
            )

    def fetch_sources(self, notebook_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id, source_type, source_name, source_value,
                       word_count, is_enabled, created_at
                FROM notebook_sources
                WHERE notebook_id = %s
                ORDER BY created_at ASC
                """,
                (notebook_id,),
            )
            return cursor.fetchall()

    def fetch_source_text(self, source_id: int) -> str:
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT extracted_text FROM notebook_sources WHERE id = %s", (source_id,))
            row = cursor.fetchone()
            return row["extracted_text"] if row else ""

    def build_knowledge_base(self, notebook_id: int) -> str:
        """Concatenate all enabled source texts into one knowledge base."""
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT source_name, extracted_text
                FROM notebook_sources
                WHERE notebook_id = %s AND is_enabled = 1
                ORDER BY created_at ASC
                """,
                (notebook_id,),
            )
            rows = cursor.fetchall()
            parts = []
            for row in rows:
                parts.append(f"[Source: {row['source_name']}]\n{row['extracted_text']}")
            return "\n\n---\n\n".join(parts)

    # ── Chat ───────────────────────────────────────────────────

    def save_chat_message(
        self, notebook_id: int, user_id: int, role: str, content: str, cited_sources: str = ""
    ) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO chat_messages (notebook_id, user_id, role, content, cited_sources)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (notebook_id, user_id, role, content, cited_sources),
            )
            return cursor.lastrowid

    def fetch_chat_history(self, notebook_id: int, limit: int = 50) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT role, content, cited_sources, created_at
                FROM chat_messages
                WHERE notebook_id = %s
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (notebook_id, limit),
            )
            return cursor.fetchall()

    def clear_chat(self, notebook_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM chat_messages WHERE notebook_id = %s", (notebook_id,))

    # ── Notes ──────────────────────────────────────────────────

    def create_note(self, notebook_id: int, user_id: int, title: str, content: str, note_type: str = "manual") -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO notebook_notes (notebook_id, user_id, title, content, note_type)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (notebook_id, user_id, title, content, note_type),
            )
            return cursor.lastrowid

    def update_note(self, note_id: int, title: str, content: str) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE notebook_notes SET title = %s, content = %s WHERE id = %s",
                (title, content, note_id),
            )

    def delete_note(self, note_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM notebook_notes WHERE id = %s", (note_id,))

    def toggle_pin_note(self, note_id: int, pinned: bool) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE notebook_notes SET is_pinned = %s WHERE id = %s",
                (1 if pinned else 0, note_id),
            )

    def fetch_notes(self, notebook_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id, title, content, note_type, is_pinned, created_at, updated_at
                FROM notebook_notes
                WHERE notebook_id = %s
                ORDER BY is_pinned DESC, updated_at DESC
                """,
                (notebook_id,),
            )
            return cursor.fetchall()

    # ── Artifacts ──────────────────────────────────────────────

    def save_artifact(self, notebook_id: int, user_id: int, artifact_type: str, content: str) -> int:
        with db_cursor() as (_, cursor):
            # Replace existing artifact of same type
            cursor.execute(
                "DELETE FROM notebook_artifacts WHERE notebook_id = %s AND artifact_type = %s",
                (notebook_id, artifact_type),
            )
            cursor.execute(
                """
                INSERT INTO notebook_artifacts (notebook_id, user_id, artifact_type, content)
                VALUES (%s, %s, %s, %s)
                """,
                (notebook_id, user_id, artifact_type, content),
            )
            return cursor.lastrowid

    def fetch_artifacts(self, notebook_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id, artifact_type, content, created_at
                FROM notebook_artifacts
                WHERE notebook_id = %s
                ORDER BY created_at DESC
                """,
                (notebook_id,),
            )
            return cursor.fetchall()

    def fetch_artifact(self, notebook_id: int, artifact_type: str) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id, artifact_type, content, created_at
                FROM notebook_artifacts
                WHERE notebook_id = %s AND artifact_type = %s
                LIMIT 1
                """,
                (notebook_id, artifact_type),
            )
            return cursor.fetchone()

    # ═══════════════════════════════════════════════════════════
    #  COMMUNITY POSTS
    # ═══════════════════════════════════════════════════════════

    def create_community_post(self, user_id: int, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO community_posts (user_id, content) VALUES (%s, %s)",
                (user_id, content),
            )
            return cursor.lastrowid

    def fetch_community_posts(self, limit: int = 50) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT cp.id, cp.content, cp.likes_count, cp.created_at,
                       u.name AS author_name, u.email AS author_email,
                       (SELECT COUNT(*) FROM community_replies cr WHERE cr.post_id = cp.id) AS reply_count
                FROM community_posts cp
                JOIN users u ON u.id = cp.user_id
                ORDER BY cp.created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cursor.fetchall()

    def like_post(self, post_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE community_posts SET likes_count = likes_count + 1 WHERE id = %s",
                (post_id,),
            )

    def create_reply(self, post_id: int, user_id: int, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO community_replies (post_id, user_id, content) VALUES (%s, %s, %s)",
                (post_id, user_id, content),
            )
            return cursor.lastrowid

    def fetch_replies(self, post_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT cr.id, cr.content, cr.created_at,
                       u.name AS author_name
                FROM community_replies cr
                JOIN users u ON u.id = cr.user_id
                WHERE cr.post_id = %s
                ORDER BY cr.created_at ASC
                """,
                (post_id,),
            )
            return cursor.fetchall()

    # ═══════════════════════════════════════════════════════════
    #  STUDY ROOMS (Learn Together)
    # ═══════════════════════════════════════════════════════════

    def _generate_room_code(self) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def create_study_room(self, owner_id: int, room_name: str, description: str = "") -> dict:
        code = self._generate_room_code()
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO study_rooms (owner_id, room_name, room_code, description) VALUES (%s, %s, %s, %s)",
                (owner_id, room_name, code, description),
            )
            room_id = cursor.lastrowid
            # Auto-join owner
            cursor.execute(
                "INSERT INTO study_room_members (room_id, user_id) VALUES (%s, %s)",
                (room_id, owner_id),
            )
            return {"id": room_id, "room_code": code}

    def join_study_room(self, room_code: str, user_id: int) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT id, room_name FROM study_rooms WHERE room_code = %s AND is_active = 1", (room_code,))
            room = cursor.fetchone()
            if not room:
                return None
            try:
                cursor.execute(
                    "INSERT INTO study_room_members (room_id, user_id) VALUES (%s, %s)",
                    (room["id"], user_id),
                )
            except Exception:
                pass  # Already a member
            return room

    def fetch_user_rooms(self, user_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT sr.id, sr.room_name, sr.room_code, sr.description, sr.created_at,
                       (SELECT COUNT(*) FROM study_room_members srm WHERE srm.room_id = sr.id) AS member_count
                FROM study_rooms sr
                JOIN study_room_members srm ON srm.room_id = sr.id
                WHERE srm.user_id = %s AND sr.is_active = 1
                ORDER BY sr.created_at DESC
                """,
                (user_id,),
            )
            return cursor.fetchall()

    def fetch_room_members(self, room_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT u.name, u.email, srm.joined_at
                FROM study_room_members srm
                JOIN users u ON u.id = srm.user_id
                WHERE srm.room_id = %s
                ORDER BY srm.joined_at ASC
                """,
                (room_id,),
            )
            return cursor.fetchall()

    def send_room_message(self, room_id: int, user_id: int, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO study_room_messages (room_id, user_id, content) VALUES (%s, %s, %s)",
                (room_id, user_id, content),
            )
            return cursor.lastrowid

    def fetch_room_messages(self, room_id: int, limit: int = 100) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT srm.content, srm.created_at, u.name AS author_name
                FROM study_room_messages srm
                JOIN users u ON u.id = srm.user_id
                WHERE srm.room_id = %s
                ORDER BY srm.created_at ASC
                LIMIT %s
                """,
                (room_id, limit),
            )
            return cursor.fetchall()

    # ── Study Room Files ───────────────────────────────────────

    def upload_room_file(
        self, room_id: int, user_id: int, file_name: str,
        file_type: str, file_data: bytes, file_text: str, file_size: int
    ) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO study_room_files
                (room_id, user_id, file_name, file_type, file_data, file_text, file_size)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (room_id, user_id, file_name, file_type, file_data, file_text, file_size),
            )
            return cursor.lastrowid

    def fetch_room_files(self, room_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT srf.id, srf.file_name, srf.file_type, srf.file_size,
                       srf.created_at, srf.user_id,
                       u.name AS uploader_name
                FROM study_room_files srf
                JOIN users u ON u.id = srf.user_id
                WHERE srf.room_id = %s
                ORDER BY srf.created_at DESC
                """,
                (room_id,),
            )
            return cursor.fetchall()

    def get_room_file_data(self, file_id: int) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "SELECT id, file_name, file_type, file_data, file_text FROM study_room_files WHERE id = %s",
                (file_id,),
            )
            return cursor.fetchone()

    def delete_room_file(self, file_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM study_room_files WHERE id = %s", (file_id,))

    # ── Study Room Shared Notes ────────────────────────────────

    def add_room_note(self, room_id: int, user_id: int, title: str, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO study_room_notes (room_id, user_id, title, content) VALUES (%s, %s, %s, %s)",
                (room_id, user_id, title, content),
            )
            return cursor.lastrowid

    def fetch_room_notes(self, room_id: int) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT srn.id, srn.title, srn.content, srn.created_at,
                       srn.user_id, u.name AS author_name
                FROM study_room_notes srn
                JOIN users u ON u.id = srn.user_id
                WHERE srn.room_id = %s
                ORDER BY srn.created_at DESC
                """,
                (room_id,),
            )
            return cursor.fetchall()

    def delete_room_note(self, note_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM study_room_notes WHERE id = %s", (note_id,))


    def add_exam_question(self, user_id: int, subject: str, year: str, question_text: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO exam_questions (user_id, subject, year, question_text) VALUES (%s, %s, %s, %s)",
                (user_id, subject, year, question_text),
            )
            return cursor.lastrowid

    def fetch_exam_questions(self, user_id: int, subject: str = "") -> list[dict]:
        with db_cursor() as (_, cursor):
            if subject:
                cursor.execute(
                    "SELECT * FROM exam_questions WHERE user_id = %s AND subject = %s ORDER BY year DESC",
                    (user_id, subject),
                )
            else:
                cursor.execute(
                    "SELECT * FROM exam_questions WHERE user_id = %s ORDER BY year DESC",
                    (user_id,),
                )
            return cursor.fetchall()

    def save_predicted_questions(self, user_id: int, subject: str, predictions: list[dict]) -> None:
        with db_cursor() as (_, cursor):
            # Clear old predictions for this subject
            cursor.execute(
                "DELETE FROM predicted_questions WHERE user_id = %s AND subject = %s",
                (user_id, subject),
            )
            for pred in predictions:
                cursor.execute(
                    "INSERT INTO predicted_questions (user_id, subject, predicted_question, confidence) VALUES (%s, %s, %s, %s)",
                    (user_id, subject, pred.get("question", ""), pred.get("confidence", "Medium")),
                )

    def fetch_predicted_questions(self, user_id: int, subject: str = "") -> list[dict]:
        with db_cursor() as (_, cursor):
            if subject:
                cursor.execute(
                    "SELECT * FROM predicted_questions WHERE user_id = %s AND subject = %s ORDER BY confidence DESC",
                    (user_id, subject),
                )
            else:
                cursor.execute(
                    "SELECT * FROM predicted_questions WHERE user_id = %s ORDER BY created_at DESC",
                    (user_id,),
                )
            return cursor.fetchall()

    # ═══════════════════════════════════════════════════════════
    #  TEXTBOOK SEARCH
    # ═══════════════════════════════════════════════════════════

    def share_as_textbook(self, source_id: int, user_id: int, textbook_name: str, topic: str, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO public_textbooks (source_id, user_id, textbook_name, topic, content)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE textbook_name = %s, topic = %s, content = %s
                """,
                (source_id, user_id, textbook_name, topic, content, textbook_name, topic, content),
            )
            return cursor.lastrowid

    def search_textbooks(self, query: str) -> list[dict]:
        with db_cursor() as (_, cursor):
            search = f"%{query}%"
            cursor.execute(
                """
                SELECT pt.id, pt.textbook_name, pt.topic, pt.created_at,
                       u.name AS shared_by
                FROM public_textbooks pt
                JOIN users u ON u.id = pt.user_id
                WHERE pt.textbook_name LIKE %s OR pt.topic LIKE %s
                ORDER BY pt.created_at DESC
                LIMIT 20
                """,
                (search, search),
            )
            return cursor.fetchall()

    def get_textbook_content(self, textbook_id: int) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT pt.*, u.name AS shared_by
                FROM public_textbooks pt
                JOIN users u ON u.id = pt.user_id
                WHERE pt.id = %s
                """,
                (textbook_id,),
            )
            return cursor.fetchone()

    # ═══════════════════════════════════════════════════════════
    #  UPLOADED SOURCES (legacy / session-based for dashboard)
    # ═══════════════════════════════════════════════════════════

    def add_uploaded_source(
        self, user_id: int, session_id: str, source_type: str,
        source_name: str, source_value: str, extracted_text: str, topic: str = ""
    ) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO uploaded_sources
                (user_id, session_id, source_type, source_name, source_value, extracted_text, topic)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, session_id, source_type, source_name, source_value, extracted_text, topic),
            )
            return cursor.lastrowid

    def fetch_session_sources(self, user_id: int, session_id: str) -> list[dict]:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id, source_type, source_name, source_value, extracted_text, topic, created_at
                FROM uploaded_sources
                WHERE user_id = %s AND session_id = %s
                ORDER BY created_at ASC
                """,
                (user_id, session_id),
            )
            return cursor.fetchall()

    def build_session_knowledge_base(self, user_id: int, session_id: str) -> str:
        sources = self.fetch_session_sources(user_id, session_id)
        parts = []
        for src in sources:
            if src.get("extracted_text"):
                parts.append(f"[Source: {src['source_name']}]\n{src['extracted_text']}")
        return "\n\n---\n\n".join(parts)

    def delete_uploaded_source(self, source_id: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM uploaded_sources WHERE id = %s", (source_id,))

    # ── Generated Outputs ──

    def save_generated_output(self, user_id: int, session_id: str, output_type: str, content: str) -> int:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO generated_outputs (user_id, session_id, output_type, content) VALUES (%s, %s, %s, %s)",
                (user_id, session_id, output_type, content),
            )
            return cursor.lastrowid

    # ── Quiz Scores ──

    def save_quiz_score(self, user_id: int, session_id: str, topic: str, score: int, total: int) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "INSERT INTO quiz_scores (user_id, session_id, topic, score, total_questions) VALUES (%s, %s, %s, %s, %s)",
                (user_id, session_id, topic, score, total),
            )
            # Update leaderboard
            cursor.execute(
                """
                INSERT INTO leaderboard (user_id, total_score, games_played)
                VALUES (%s, %s, 1)
                ON DUPLICATE KEY UPDATE total_score = total_score + %s, games_played = games_played + 1
                """,
                (user_id, score, score),
            )
