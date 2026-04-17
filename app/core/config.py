from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _get_secret(key: str, default: str = "") -> str:
    """Get a config value from Streamlit secrets, then env vars, then default.

    Streamlit Cloud stores secrets in .streamlit/secrets.toml,
    accessible via st.secrets at runtime.
    """
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        val = st.secrets.get(key, None)
        if val is not None:
            return str(val)
    except Exception:
        pass

    # Fall back to environment variable
    return os.getenv(key, default)


@dataclass(frozen=True)
class Settings:
    mysql_host: str = _get_secret("MYSQL_HOST", "localhost")
    mysql_port: int = int(_get_secret("MYSQL_PORT", "3306"))
    mysql_user: str = _get_secret("MYSQL_USER", "root")
    mysql_password: str = _get_secret("MYSQL_PASSWORD", "")
    mysql_database: str = _get_secret("MYSQL_DATABASE", "studybuddy")
    openrouter_api_key: str = _get_secret("OPENROUTER_API_KEY", "")
    openrouter_model: str = _get_secret("OPENROUTER_MODEL", "google/gemini-2.0-flash-lite-001")
    smtp_email: str = _get_secret("SMTP_EMAIL", "")
    smtp_password: str = _get_secret("SMTP_PASSWORD", "")
    smtp_server: str = _get_secret("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(_get_secret("SMTP_PORT", "587"))
    app_base_url: str = _get_secret("APP_BASE_URL", "http://localhost:8501")
    export_dir: str = _get_secret("EXPORT_DIR", "exports")


settings = Settings()
