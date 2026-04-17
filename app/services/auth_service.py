from __future__ import annotations

import hashlib
import random
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from passlib.context import CryptContext

from app.core.config import settings
from app.core.database import db_cursor


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


class AuthService:
    def _normalize_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(self._normalize_password(password))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(self._normalize_password(plain_password), hashed_password)

    def create_user(self, name: str, email: str, password: str) -> int:
        hashed_password = self.hash_password(password)
        with db_cursor() as (_, cursor):
            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                raise ValueError("An account with this email already exists.")

            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (name, email, hashed_password),
            )
            return cursor.lastrowid

    def login(self, email: str, password: str) -> dict | None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "SELECT id, name, email, password_hash, preferred_mode FROM users WHERE email = %s",
                (email,),
            )
            user = cursor.fetchone()
            if not user:
                return None
            if not self.verify_password(password, user["password_hash"]):
                return None
            return user

    def generate_otp(self, email: str) -> str:
        otp = f"{random.randint(100000, 999999)}"
        expires_at = datetime.now() + timedelta(minutes=10)
        with db_cursor() as (_, cursor):
            cursor.execute("DELETE FROM otp_verification WHERE email = %s", (email,))
            cursor.execute(
                """
                INSERT INTO otp_verification (email, otp_code, expires_at)
                VALUES (%s, %s, %s)
                """,
                (email, otp, expires_at),
            )
        self.send_otp_email(email, otp)
        return otp

    def send_otp_email(self, email: str, otp: str) -> None:
        if not settings.smtp_email or not settings.smtp_password:
            raise ValueError("SMTP settings are missing in the .env file.")

        message = MIMEText(
            f"Your StudyBuddy password reset OTP is {otp}. It expires in 10 minutes."
        )
        message["Subject"] = "StudyBuddy Password Reset OTP"
        message["From"] = settings.smtp_email
        message["To"] = email

        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_email, settings.smtp_password)
            server.send_message(message)

    def verify_otp(self, email: str, otp: str) -> bool:
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                SELECT id
                FROM otp_verification
                WHERE email = %s AND otp_code = %s AND expires_at >= NOW() AND is_used = 0
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (email, otp),
            )
            row = cursor.fetchone()
            if not row:
                return False

            cursor.execute(
                "UPDATE otp_verification SET is_used = 1 WHERE id = %s",
                (row["id"],),
            )
            return True

    def reset_password(self, email: str, new_password: str) -> None:
        hashed_password = self.hash_password(new_password)
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE email = %s",
                (hashed_password, email),
            )

    def update_user_mode(self, user_id: int, mode: str) -> None:
        with db_cursor() as (_, cursor):
            cursor.execute(
                "UPDATE users SET preferred_mode = %s WHERE id = %s",
                (mode, user_id),
            )
