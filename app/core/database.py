from contextlib import contextmanager

import mysql.connector
from mysql.connector import Error

from app.core.config import settings


def get_connection():
    return mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        autocommit=False,
    )


def get_server_connection():
    return mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        autocommit=True,
    )


def check_database_status() -> tuple[bool, str]:
    try:
        server_connection = get_server_connection()
    except Error as exc:
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
    except Error as exc:
        return False, f"MySQL database check failed: {exc}"


@contextmanager
def db_cursor(dictionary: bool = True):
    connection = None
    cursor = None
    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=dictionary)
        yield connection, cursor
        connection.commit()
    except Error:
        if connection:
            connection.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()
