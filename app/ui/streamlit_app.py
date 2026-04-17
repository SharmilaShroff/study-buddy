from __future__ import annotations

import io
import json
import uuid
import warnings
import streamlit.components.v1 as components

import streamlit as st

# Suppress the RequestsDependencyWarning about urllib3/chardet/charset-normalizer versions
warnings.filterwarnings("ignore", message=".*urllib3.*chardet.*charset_normalizer.*doesn't match a supported version.*")

# ── Translation (Multi-Language Support) ──
from deep_translator import GoogleTranslator

# ── Voice Input (Mic) ──
try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    from audio_recorder_streamlit import audio_recorder
except ImportError:
    audio_recorder = None

from app.core.config import settings
from app.core.database import check_database_status
from app.services.ai_service import AIService
from app.services.auth_service import AuthService
from app.services.content_service import ContentService
from app.services.export_service import ExportService
from app.services.recommendation_service import RecommendationService
from app.services.repository import NotebookRepository
from app.utils.helpers import extract_json_block


# ── Service singletons ──
auth_service = AuthService()
content_service = ContentService()
ai_service = AIService()
repo = NotebookRepository()
export_service = ExportService()
rec_service = RecommendationService()


# ═══════════════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════════════

def init_state() -> None:
    defaults = {
        "user": None,
        "page": "dashboard",          # dashboard | exam_predictor | revision | learn_together | textbook_search | community
        "notebook_id": None,
        "session_id": None,
        "chat_input_key": 0,
        "source_processing": False,
        "quiz_state": None,           # holds active quiz data
        "quiz_answers": {},
        "quiz_submitted": False,
        "flashcard_index": 0,
        "flashcard_flipped": False,
        "auth_view": "login",         # login | signup | forgot
        "forgot_step": "email",       # email | otp | reset
        "forgot_email": "",
        "room_id": None,              # active study room
        "selected_language": "English",  # multi-language support
        "voice_text": "",               # mic input transcription
        "pdf_titles": [],               # extracted PDF titles for YouTube recs
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # Generate session ID for uploads if missing
    if not st.session_state.session_id:
        st.session_state.session_id = str(uuid.uuid4())[:8]


# ═══════════════════════════════════════════════════════════════
#  TRANSLATION HELPER (Multi-Language Support)
# ═══════════════════════════════════════════════════════════════

# Language codes for deep-translator (Google Translate NLP)
LANGUAGE_MAP = {
    "English": "en",
    "Kannada": "kn",
    "Telugu": "te",
    "Tamil": "ta",
    "Hindi": "hi",
}


@st.cache_data(ttl=3600, show_spinner=False)
def _translate_cached(text: str, target_lang_code: str) -> str:
    """Translate text using Google Translate via deep-translator (NLP-based).

    Cached for 1 hour to avoid repeated API calls for the same text.
    """
    if target_lang_code == "en" or not text.strip():
        return text
    try:
        result = GoogleTranslator(source="en", target=target_lang_code).translate(text)
        return result if result else text
    except Exception:
        return text  # Fallback: return original text if translation fails


def _t(text: str) -> str:
    """Translate a UI string based on the user's selected language.

    Wrap any UI label with _t("text") to enable multi-language support.
    """
    lang = st.session_state.get("selected_language", "English")
    code = LANGUAGE_MAP.get(lang, "en")
    if code == "en":
        return text
    return _translate_cached(text, code)


def _render_language_selector():
    """Render a language selector dropdown in the top-right corner."""
    _, lang_col = st.columns([6, 1])
    with lang_col:
        current = st.session_state.get("selected_language", "English")
        languages = list(LANGUAGE_MAP.keys())
        idx = languages.index(current) if current in languages else 0
        selected = st.selectbox(
            "🌐",
            languages,
            index=idx,
            key="language_picker",
            label_visibility="collapsed",
        )
        if selected != current:
            st.session_state["selected_language"] = selected
            st.rerun()


# ═══════════════════════════════════════════════════════════════
#  THEME / CSS
# ═══════════════════════════════════════════════════════════════

def inject_css() -> None:
    st.markdown(
        """<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">""",
        unsafe_allow_html=True,
    )
    css = """
    <style>
    /* ── Global ── */
    .stApp {
        background: #0f0f1a !important;
        color: #e2e8f0 !important;
        font-family: 'Inter', sans-serif !important;
    }
    .stApp p, .stApp span, .stApp label, .stApp div,
    .stApp .stMarkdown p {
        color: #e2e8f0 !important;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #f1f5f9 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d0d1f 0%, #141428 100%) !important;
        border-right: 1px solid rgba(124,58,237,0.1) !important;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] div {
        color: #cbd5e1 !important;
    }

    /* ── Inputs ── */
    .stTextInput input, .stTextArea textarea {
        background: #1a1a30 !important;
        color: #e2e8f0 !important;
        border: 1px solid rgba(124,58,237,0.2) !important;
        border-radius: 12px !important;
        font-family: 'Inter', sans-serif !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #7c3aed !important;
        box-shadow: 0 0 0 3px rgba(124,58,237,0.15) !important;
    }
    .stTextInput label, .stTextArea label,
    .stSelectbox label, .stMultiSelect label {
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
    }

    /* ── Buttons ── */
    .stButton button,
    .stFormSubmitButton button {
        background: linear-gradient(135deg, #6d28d9, #7c3aed, #8b5cf6) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.55rem 1.3rem !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        box-shadow: 0 4px 14px rgba(124,58,237,0.3) !important;
        transition: all 0.25s ease !important;
        font-family: 'Inter', sans-serif !important;
    }
    .stButton button:hover,
    .stFormSubmitButton button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(124,58,237,0.45) !important;
    }
    .stDownloadButton button {
        background: transparent !important;
        color: #a78bfa !important;
        border: 1.5px solid rgba(124,58,237,0.4) !important;
        border-radius: 12px !important;
        box-shadow: none !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px !important;
        background: #141428 !important;
        border-radius: 12px !important;
        padding: 3px !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        color: #94a3b8 !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6d28d9, #7c3aed) !important;
        color: #ffffff !important;
    }

    /* ── Forms ── */
    [data-testid="stForm"] {
        background: #141428 !important;
        border: 1px solid rgba(124,58,237,0.1) !important;
        border-radius: 16px !important;
        padding: 1.5rem !important;
    }

    /* ── Login card ── */
    .login-card {
        max-width: 440px;
        margin: 2rem auto;
        padding: 2.5rem;
        background: linear-gradient(145deg, #141428 0%, #1a1a35 100%);
        border: 1px solid rgba(124,58,237,0.15);
        border-radius: 24px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }
    .login-title {
        text-align: center;
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #a78bfa, #7c3aed, #6d28d9);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }
    .login-subtitle {
        text-align: center;
        color: #64748b !important;
        font-size: 0.92rem;
        margin-bottom: 2rem;
    }

    /* ── Feature cards ── */
    .feature-card {
        background: linear-gradient(145deg, #1a1a35 0%, #1e1e3a 100%);
        border: 1px solid rgba(124,58,237,0.1);
        border-radius: 16px;
        padding: 1.2rem;
        text-align: center;
        transition: all 0.3s ease;
        cursor: pointer;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .feature-card:hover {
        border-color: #7c3aed;
        transform: translateY(-4px);
        box-shadow: 0 8px 30px rgba(124,58,237,0.2);
    }
    .feature-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    .feature-label {
        font-size: 0.82rem;
        font-weight: 600;
        color: #cbd5e1 !important;
    }

    /* ── Right sidebar icon buttons ── */
    .tool-icon-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 48px;
        height: 48px;
        border-radius: 14px;
        background: #1a1a35;
        border: 1px solid rgba(124,58,237,0.15);
        font-size: 1.3rem;
        margin: 0.4rem auto;
        cursor: pointer;
        transition: all 0.25s ease;
    }
    .tool-icon-btn:hover {
        background: rgba(124,58,237,0.15);
        border-color: #7c3aed;
        transform: scale(1.1);
    }

    /* ── Chat ── */
    .chat-msg {
        padding: 1rem 1.2rem;
        border-radius: 16px;
        margin-bottom: 0.6rem;
        line-height: 1.65;
        font-size: 0.92rem;
    }
    .chat-user {
        background: #1a1a35;
        border: 1px solid rgba(255,255,255,0.06);
        margin-left: 2rem;
    }
    .chat-ai {
        background: rgba(124,58,237,0.08);
        border: 1px solid rgba(124,58,237,0.15);
        margin-right: 1rem;
    }
    .chat-role {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 0.4rem;
        color: #a78bfa !important;
    }

    /* ── Source chips ── */
    .source-chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 0.8rem;
        border-radius: 10px;
        background: #1a1a35;
        border: 1px solid rgba(124,58,237,0.1);
        margin: 0.2rem 0;
        font-size: 0.82rem;
        color: #cbd5e1 !important;
        transition: all 0.15s ease;
        width: 100%;
    }
    .source-chip-enabled { border-color: rgba(124,58,237,0.35); background: rgba(124,58,237,0.08); }

    /* ── Community post ── */
    .post-card {
        background: #141428;
        border: 1px solid rgba(124,58,237,0.1);
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.8rem;
    }
    .post-author {
        font-weight: 700;
        font-size: 0.88rem;
        color: #a78bfa !important;
    }
    .post-time {
        font-size: 0.72rem;
        color: #475569 !important;
    }

    /* ── Flashcard ── */
    .flashcard {
        background: linear-gradient(145deg, #1e1e3a, #252547);
        border: 1px solid rgba(124,58,237,0.2);
        border-radius: 20px;
        padding: 2.5rem;
        text-align: center;
        min-height: 200px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        transition: all 0.3s ease;
    }
    .flashcard-q { font-size: 1.1rem; font-weight: 600; color: #f1f5f9 !important; }
    .flashcard-a { font-size: 1rem; color: #a78bfa !important; }

    /* ── Quiz option ── */
    .quiz-option {
        padding: 0.8rem 1.2rem;
        border-radius: 12px;
        background: #1a1a35;
        border: 1px solid rgba(255,255,255,0.08);
        margin: 0.3rem 0;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .quiz-option:hover { border-color: #7c3aed; }
    .quiz-correct { border-color: #22c55e !important; background: rgba(34,197,94,0.1) !important; }
    .quiz-wrong { border-color: #ef4444 !important; background: rgba(239,68,68,0.1) !important; }

    /* ── Section titles ── */
    .section-title {
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #64748b !important;
        margin-bottom: 0.8rem;
    }

    /* ── Misc ── */
    .source-count {
        display: inline-flex; align-items: center; justify-content: center;
        background: #7c3aed; color: #fff !important; border-radius: 99px;
        width: 22px; height: 22px; font-size: 0.72rem; font-weight: 700;
    }
    .stCaption, small { color: #64748b !important; }
    hr { border-color: rgba(124,58,237,0.1) !important; }
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-thumb { background: rgba(124,58,237,0.2); border-radius: 99px; }

    /* ── Mode badge ── */
    .mode-badge {
        display: inline-flex; align-items: center; gap: 0.4rem;
        padding: 0.35rem 0.8rem; border-radius: 99px;
        font-size: 0.75rem; font-weight: 700;
    }
    .mode-student { background: rgba(34,197,94,0.15); color: #22c55e !important; border: 1px solid rgba(34,197,94,0.3); }
    .mode-developer { background: rgba(249,115,22,0.15); color: #f97316 !important; border: 1px solid rgba(249,115,22,0.3); }

    /* ── Page header ── */
    .page-header {
        padding: 1.5rem 0;
        border-bottom: 1px solid rgba(124,58,237,0.1);
        margin-bottom: 1.5rem;
    }
    .page-header h2 {
        margin: 0 !important;
        font-size: 1.5rem !important;
    }

    /* ── Prediction card ── */
    .pred-card {
        background: #141428;
        border: 1px solid rgba(124,58,237,0.1);
        border-radius: 14px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.6rem;
    }
    .confidence-high { border-left: 3px solid #22c55e; }
    .confidence-medium { border-left: 3px solid #f59e0b; }
    .confidence-low { border-left: 3px solid #ef4444; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  AUTH SCREEN — Login / Signup / Forgot Password
# ═══════════════════════════════════════════════════════════════

def render_auth() -> None:
    # Center the login card
    _, col_center, _ = st.columns([1, 1.5, 1])
    with col_center:
        st.markdown(
            """
            <div style="text-align:center; margin-top:3rem;">
                <div style="font-size:3rem; margin-bottom:0.5rem;">🎓</div>
                <div class="login-title">StudyBuddy AI</div>
                <div class="login-subtitle">Your AI-Powered Smart Learning Assistant</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── LOGIN VIEW ──
        if st.session_state.auth_view == "login":
            with st.form("login_form"):
                email = st.text_input("Login ID (Email)", placeholder="you@example.com")
                password = st.text_input("Password", type="password", placeholder="Enter password")
                submitted = st.form_submit_button("🔓 Login", use_container_width=True)

            if submitted:
                if not email.strip() or not password:
                    st.error("Please enter both email and password.")
                else:
                    try:
                        user = auth_service.login(email.strip(), password)
                        if user:
                            st.session_state.user = user
                            st.session_state.page = "dashboard"
                            st.rerun()
                        else:
                            st.error("❌ Invalid email or password.")
                    except Exception as exc:
                        st.error(f"Login failed: {exc}")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔑 Forgot Password", use_container_width=True):
                    st.session_state.auth_view = "forgot"
                    st.rerun()
            with c2:
                if st.button("✨ Create New Account", use_container_width=True):
                    st.session_state.auth_view = "signup"
                    st.rerun()

        # ── SIGNUP VIEW ──
        elif st.session_state.auth_view == "signup":
            st.markdown("### Create New Account")
            with st.form("signup_form"):
                name = st.text_input("Full Name", placeholder="John Doe")
                email2 = st.text_input("Email Address", placeholder="you@example.com")
                pwd = st.text_input("Password", type="password", placeholder="Min 6 characters")
                pwd2 = st.text_input("Confirm Password", type="password", placeholder="Re-enter password")
                submitted2 = st.form_submit_button("📝 Create Account", use_container_width=True)

            if submitted2:
                if not name.strip() or not email2.strip() or not pwd:
                    st.error("Please fill all fields.")
                elif len(pwd) < 6:
                    st.error("Password must be at least 6 characters.")
                elif pwd != pwd2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        auth_service.create_user(name.strip(), email2.strip(), pwd)
                        st.success("✅ Account created! Please sign in.")
                        st.session_state.auth_view = "login"
                    except Exception as exc:
                        st.error(f"Signup failed: {exc}")

            if st.button("← Back to Login", use_container_width=True):
                st.session_state.auth_view = "login"
                st.rerun()

        # ── FORGOT PASSWORD VIEW ──
        elif st.session_state.auth_view == "forgot":
            st.markdown("### Forgot Password")

            if st.session_state.forgot_step == "email":
                with st.form("forgot_email_form"):
                    email3 = st.text_input("Enter your registered email", placeholder="you@example.com")
                    send_otp = st.form_submit_button("📧 Send OTP", use_container_width=True)
                if send_otp and email3.strip():
                    try:
                        auth_service.generate_otp(email3.strip())
                        st.session_state.forgot_email = email3.strip()
                        st.session_state.forgot_step = "otp"
                        st.success("OTP sent to your email!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to send OTP: {exc}")

            elif st.session_state.forgot_step == "otp":
                st.info(f"OTP sent to: {st.session_state.forgot_email}")
                with st.form("verify_otp_form"):
                    otp = st.text_input("Enter 6-digit OTP", placeholder="123456")
                    verify = st.form_submit_button("✅ Verify OTP", use_container_width=True)
                if verify and otp.strip():
                    if auth_service.verify_otp(st.session_state.forgot_email, otp.strip()):
                        st.session_state.forgot_step = "reset"
                        st.success("OTP verified!")
                        st.rerun()
                    else:
                        st.error("Invalid or expired OTP.")

            elif st.session_state.forgot_step == "reset":
                with st.form("reset_pwd_form"):
                    new_pwd = st.text_input("New Password", type="password", placeholder="Min 6 characters")
                    new_pwd2 = st.text_input("Confirm New Password", type="password")
                    reset = st.form_submit_button("🔄 Reset Password", use_container_width=True)
                if reset:
                    if len(new_pwd) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif new_pwd != new_pwd2:
                        st.error("Passwords do not match.")
                    else:
                        auth_service.reset_password(st.session_state.forgot_email, new_pwd)
                        st.success("✅ Password reset! Please login.")
                        st.session_state.forgot_step = "email"
                        st.session_state.forgot_email = ""
                        st.session_state.auth_view = "login"
                        st.rerun()

            if st.button("← Back to Login", use_container_width=True, key="back_forgot"):
                st.session_state.auth_view = "login"
                st.session_state.forgot_step = "email"
                st.rerun()


# ═══════════════════════════════════════════════════════════════
#  DASHBOARD — Main 3-panel layout
# ═══════════════════════════════════════════════════════════════

def render_dashboard() -> None:
    # ── Language selector in top-right corner ──
    _render_language_selector()

    user = st.session_state.user
    user_id = user["id"]
    session_id = st.session_state.session_id
    mode = user.get("preferred_mode", "Student Mode")

    # Build knowledge base from session uploads
    kb = repo.build_session_knowledge_base(user_id, session_id)
    sources = repo.fetch_session_sources(user_id, session_id)

    # ── LEFT SIDEBAR ──
    with st.sidebar:
        # User header
        st.markdown(
            f"""
            <div style="text-align:center; margin:0.5rem 0 1rem;">
                <div style="font-size:2rem;">🎓</div>
                <div style="font-weight:700; font-size:1.05rem;">StudyBuddy AI</div>
                <div style="font-size:0.78rem; color:#64748b; margin-top:0.2rem;">
                    {_t('Welcome')}, {user['name']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Mode toggle
        mode_class = "mode-student" if mode == "Student Mode" else "mode-developer"
        mode_icon = "🎒" if mode == "Student Mode" else "⚙️"
        st.markdown(f'<div class="mode-badge {mode_class}">{mode_icon} {_t(mode)}</div>', unsafe_allow_html=True)

        new_mode = st.selectbox(
            _t("Switch Mode"),
            ["Student Mode", "Developer Mode"],
            index=0 if mode == "Student Mode" else 1,
            label_visibility="collapsed",
        )
        if new_mode != mode:
            auth_service.update_user_mode(user_id, new_mode)
            st.session_state.user["preferred_mode"] = new_mode
            st.rerun()

        st.markdown("---")

        # ── Upload Documents ──
        st.markdown(f'<div class="section-title">📄 {_t("Upload Documents")}</div>', unsafe_allow_html=True)
        uploaded_files = st.file_uploader(
            _t("Choose files"),
            type=["pdf", "docx", "txt", "ppt", "pptx"],
            accept_multiple_files=True,
            key="doc_uploader",
            label_visibility="collapsed",
        )

        # ── Upload Website Links ──
        st.markdown(f'<div class="section-title">🌐 {_t("Website Links")}</div>', unsafe_allow_html=True)
        web_links = st.text_area(
            _t("Paste URLs (one per line)"),
            placeholder="https://example.com/article\nhttps://another-site.com",
            height=80,
            key="web_links",
            label_visibility="collapsed",
        )

        # ── Upload YouTube Links ──
        st.markdown(f'<div class="section-title">🎬 {_t("YouTube Links")}</div>', unsafe_allow_html=True)
        yt_links = st.text_area(
            _t("Paste YouTube URLs (one per line)"),
            placeholder="https://youtube.com/watch?v=...\nhttps://youtu.be/...",
            height=80,
            key="yt_links",
            label_visibility="collapsed",
        )

        # Submit button
        if st.button("🚀 Submit & Process", use_container_width=True):
            _process_uploads(user_id, session_id, uploaded_files, web_links, yt_links)

        st.markdown("---")

        # Uploaded sources list
        if sources:
            st.markdown(
                f'<div class="section-title">Sources <span class="source-count">{len(sources)}</span></div>',
                unsafe_allow_html=True,
            )
            for src in sources:
                icon = {"file": "📄", "youtube": "🎬", "website": "🌐"}.get(src["source_type"], "📝")
                st.markdown(
                    f'<div class="source-chip source-chip-enabled">{icon} {src["source_name"][:30]}</div>',
                    unsafe_allow_html=True,
                )
                if st.button("🗑", key=f"del_src_{src['id']}", help="Remove source"):
                    repo.delete_uploaded_source(src["id"])
                    st.rerun()

        st.markdown("---")
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ── MAIN LAYOUT: Center + Right sidebar ──
    center_col, right_col = st.columns([5, 1])

    # ─────────────────────────────────────────
    #  CENTER SECTION
    # ─────────────────────────────────────────
    with center_col:
        # ── Feature icons grid (3x2) ──
        st.markdown("### ✨ Learning Tools")

        features = [
            ("📊", _t("PPT Generator"), "ppt"),
            ("🃏", _t("Flashcards"), "flashcards"),
            ("🖼️", _t("Poster"), "poster"),
            ("🧠", _t("Mind Map"), "mindmap"),
            ("❓", _t("Quiz"), "quiz"),
            ("🔊", _t("Audio Overview"), "audio"),
        ]

        row1 = st.columns(3)
        row2 = st.columns(3)
        all_cols = row1 + row2

        for i, (icon, label, key) in enumerate(features):
            with all_cols[i]:
                st.markdown(
                    f"""
                    <div class="feature-card">
                        <div class="feature-icon">{icon}</div>
                        <div class="feature-label">{label}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"Generate", key=f"feat_{key}", use_container_width=True):
                    if not kb.strip():
                        st.warning("⚠️ Please upload sources first!")
                    else:
                        _handle_feature(key, kb, user_id, session_id, mode)

        st.markdown("---")

        # ── Question Box with Mic Input ──
        st.markdown(f"### 💬 {_t('Ask a Question')}")
        st.caption(_t("Ask any question about your uploaded content"))

        # ── Mic Input (Voice to Text) ─ English Only ──
        voice_text = st.session_state.get("voice_text", "")
        if audio_recorder is not None and sr is not None:
            st.markdown(f"🎤 {_t('Click mic to record (English only)')}")
            audio_bytes = audio_recorder(
                text="",
                recording_color="#ef4444",
                neutral_color="#7c3aed",
                icon_size="2x",
                key="voice_recorder",
            )
            if audio_bytes:
                with st.spinner(_t("Transcribing speech...")):
                    try:
                        recognizer = sr.Recognizer()
                        audio_file = io.BytesIO(audio_bytes)
                        with sr.AudioFile(audio_file) as source:
                            audio_data = recognizer.record(source)
                        voice_text = recognizer.recognize_google(audio_data, language="en-US")
                        st.session_state["voice_text"] = voice_text
                        st.success(f"🎤 {_t('Heard')}: {voice_text}")
                    except sr.UnknownValueError:
                        st.warning(_t("Could not understand the audio. Please try again."))
                    except Exception as exc:
                        st.error(f"{_t('Voice error')}: {exc}")

        with st.form("question_form", clear_on_submit=True):
            default_q = voice_text if voice_text else ""
            question = st.text_input(
                _t("Your question"),
                value=default_q,
                placeholder=_t("Type your question or use mic above..."),
                label_visibility="collapsed",
            )
            ask_btn = st.form_submit_button(f"🔍 {_t('Ask AI')}", use_container_width=True)

        if ask_btn and question.strip():
            st.session_state["voice_text"] = ""  # Clear voice text after use
            if not kb.strip():
                st.warning(_t("Upload sources first before asking questions."))
            else:
                with st.spinner(_t("Thinking...")):
                    try:
                        answer = ai_service.answer_question(kb, question.strip(), mode)
                        st.markdown("---")
                        st.markdown(f"#### 🤖 {_t('AI Answer')}")
                        st.markdown(answer)
                    except Exception as exc:
                        st.error(f"{_t('Error')}: {exc}")

        # ── Show generated content below ──
        _render_generated_content()

    # ─────────────────────────────────────────
    #  RIGHT SIDEBAR (icon + text label)
    # ─────────────────────────────────────────
    with right_col:
        st.markdown('<div class="section-title" style="text-align:center;">Tools</div>', unsafe_allow_html=True)

        tool_icons = [
            ("🎯", _t("Exam Predictor"), "exam_predictor"),
            ("📝", _t("Revision"), "revision"),
            ("👥", _t("Learn Together"), "learn_together"),
            ("📚", _t("Textbooks"), "textbook_search"),
            ("💬", _t("Community"), "community"),
        ]

        for icon, label, page_key in tool_icons:
            st.markdown(
                f"""
                <div style="text-align:center; margin-bottom:0.3rem;">
                    <div class="tool-icon-btn">{icon}</div>
                    <div style="font-size:0.68rem; font-weight:600; color:#94a3b8; margin-top:-0.2rem;">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"{label}", key=f"nav_{page_key}", help=label, use_container_width=True):
                st.session_state.page = page_key
                st.rerun()


# ═══════════════════════════════════════════════════════════════
#  UPLOAD PROCESSING
# ═══════════════════════════════════════════════════════════════

def _process_uploads(user_id, session_id, files, web_links, yt_links):
    added = 0

    # Files
    for f in (files or []):
        try:
            file_bytes = f.read()
            text = content_service.extract_text_from_upload(f.name, file_bytes)
            if text:
                repo.add_uploaded_source(user_id, session_id, "file", f.name, f.name, text)
                added += 1
                # Extract PDF title for YouTube recommendations (Feature 4)
                if f.name.lower().endswith(".pdf"):
                    pdf_title = content_service.extract_pdf_title(file_bytes)
                    if pdf_title and pdf_title != "Untitled Document":
                        st.session_state.setdefault("pdf_titles", []).append(pdf_title)
        except Exception as exc:
            st.error(f"Failed: {f.name} — {exc}")

    # Websites
    for link in (web_links or "").strip().splitlines():
        link = link.strip()
        if not link:
            continue
        try:
            text = content_service.extract_website_content(link)
            if text:
                repo.add_uploaded_source(user_id, session_id, "website", link[:80], link, text)
                added += 1
        except Exception as exc:
            st.error(f"Failed: {link} — {exc}")

    # YouTube
    for link in (yt_links or "").strip().splitlines():
        link = link.strip()
        if not link:
            continue
        try:
            text = content_service.extract_youtube_transcript(link)
            if text:
                repo.add_uploaded_source(user_id, session_id, "youtube", link[:80], link, text)
                added += 1
        except Exception as exc:
            st.error(f"Failed: {link} — {exc}")

    # Auto-fetch YouTube recommendations for uploaded PDF titles (Feature 4)
    pdf_titles = st.session_state.get("pdf_titles", [])
    if pdf_titles:
        yt_recs = []
        for title in pdf_titles:
            try:
                videos = rec_service.recommend_videos(title, limit=3)
                if videos:
                    yt_recs.append({"topic": f"📄 {title}", "videos": videos})
            except Exception:
                pass
        if yt_recs:
            existing = st.session_state.get("gen_youtube_recs", [])
            st.session_state["gen_youtube_recs"] = existing + yt_recs
        st.session_state["pdf_titles"] = []  # Clear after processing

    if added:
        st.success(f"✅ Processed {added} source(s)!")
        st.rerun()
    elif not files and not web_links.strip() and not yt_links.strip():
        st.warning("No sources provided.")


# ═══════════════════════════════════════════════════════════════
#  FEATURE HANDLERS
# ═══════════════════════════════════════════════════════════════

def _handle_feature(feature_key, kb, user_id, session_id, mode):
    """Handle generation for each of the 8 feature icons."""
    with st.spinner(f"Generating..."):
        try:
            if feature_key == "ppt":
                content = ai_service.generate_ppt_content(kb, mode)
                ppt_bytes = export_service.export_slide_text_to_ppt("StudyBuddy Presentation", content)
                st.session_state["gen_ppt"] = ppt_bytes
                repo.save_generated_output(user_id, session_id, "ppt", content)

            elif feature_key == "flashcards":
                cards = ai_service.generate_flashcards(kb, mode)
                st.session_state["gen_flashcards"] = cards
                st.session_state["flashcard_index"] = 0
                st.session_state["flashcard_flipped"] = False

            elif feature_key == "poster":
                raw_content = ai_service.generate_poster_content(kb, mode)
                # Parse JSON from AI response
                try:
                    raw_text = raw_content.strip()
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("```")[1]
                        if raw_text.startswith("json"):
                            raw_text = raw_text[4:]
                        raw_text = raw_text.rsplit("```", 1)[0]
                    poster_data = json.loads(raw_text)
                except (json.JSONDecodeError, IndexError):
                    poster_data = {
                        "title": "Study Poster",
                        "tagline": "Key concepts from your sources",
                        "sections": [{"heading": "Summary", "points": [raw_content[:200]]}],
                        "conclusion": "Review your sources for more details.",
                    }
                pdf_bytes = export_service.export_poster_to_pdf(poster_data)
                st.session_state["gen_poster"] = pdf_bytes
                repo.save_generated_output(user_id, session_id, "poster", raw_content)

            elif feature_key == "youtube_recs":
                # Extract topics from knowledge base and fetch YouTube videos
                topics = ai_service.extract_topics(kb)
                all_videos = []
                for topic in topics[:4]:
                    videos = rec_service.recommend_videos(topic, limit=3)
                    if videos:
                        all_videos.append({"topic": topic, "videos": videos})
                st.session_state["gen_youtube_recs"] = all_videos

            elif feature_key == "mindmap":
                content = ai_service.generate_mindmap(kb, mode)
                st.session_state["gen_mindmap"] = content
                repo.save_generated_output(user_id, session_id, "mindmap", content)

            elif feature_key == "video":
                content = ai_service.generate_video_overview(kb, mode)
                st.session_state["gen_video"] = content
                repo.save_generated_output(user_id, session_id, "video", content)

            elif feature_key == "quiz":
                questions = ai_service.generate_quiz(kb, 10, mode)
                st.session_state["quiz_state"] = questions
                st.session_state["quiz_answers"] = {}
                st.session_state["quiz_submitted"] = False

            elif feature_key == "audio":
                content = ai_service.generate_audio_script(kb, mode)
                st.session_state["gen_audio"] = content
                repo.save_generated_output(user_id, session_id, "audio", content)

            st.rerun()

        except Exception as exc:
            st.error(f"Generation failed: {exc}")


def _render_generated_content():
    """Render any generated content stored in session state."""

    # ── PPT ──
    if st.session_state.get("gen_ppt"):
        st.markdown("---")
        st.markdown("### 📊 Presentation Ready!")
        st.markdown(
            """
            <div style="background: linear-gradient(145deg, #1a1a35, #1e1e3a); border: 1px solid rgba(124,58,237,0.2);
                        border-radius: 16px; padding: 2rem; text-align: center; margin: 1rem 0;">
                <div style="font-size: 3rem; margin-bottom: 0.5rem;">📊</div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #f1f5f9;">Your presentation is ready!</div>
                <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.3rem;">Professional slides with clean layout, headings, and bullet points</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.download_button(
            "📥 Download PPTX",
            data=st.session_state["gen_ppt"],
            file_name="studybuddy_presentation.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
        )
        if st.button("✖ Close", key="close_ppt"):
            del st.session_state["gen_ppt"]
            st.rerun()

    # ── Flashcards ──
    if st.session_state.get("gen_flashcards"):
        st.markdown("---")
        st.markdown("### 🃏 Flashcards")
        cards = st.session_state["gen_flashcards"]
        idx = st.session_state.get("flashcard_index", 0)
        flipped = st.session_state.get("flashcard_flipped", False)

        if idx < len(cards):
            card = cards[idx]
            if flipped:
                st.markdown(
                    f'<div class="flashcard"><div class="flashcard-a">💡 {card.get("answer", "")}</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="flashcard"><div class="flashcard-q">❓ {card.get("question", "")}</div></div>',
                    unsafe_allow_html=True,
                )

            st.caption(f"Card {idx + 1} of {len(cards)}")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("⬅ Prev", key="fc_prev", use_container_width=True) and idx > 0:
                    st.session_state["flashcard_index"] = idx - 1
                    st.session_state["flashcard_flipped"] = False
                    st.rerun()
            with c2:
                if st.button("🔄 Flip", key="fc_flip", use_container_width=True):
                    st.session_state["flashcard_flipped"] = not flipped
                    st.rerun()
            with c3:
                if st.button("➡ Next", key="fc_next", use_container_width=True) and idx < len(cards) - 1:
                    st.session_state["flashcard_index"] = idx + 1
                    st.session_state["flashcard_flipped"] = False
                    st.rerun()

        if st.button("✖ Close Flashcards", key="close_fc"):
            del st.session_state["gen_flashcards"]
            st.rerun()

    # ── Poster ──
    if st.session_state.get("gen_poster"):
        st.markdown("---")
        st.markdown("### 🖼️ Poster Ready!")
        st.markdown(
            """
            <div style="background: linear-gradient(145deg, #1a1a35, #1e1e3a); border: 1px solid rgba(124,58,237,0.2);
                        border-radius: 16px; padding: 2rem; text-align: center; margin: 1rem 0;">
                <div style="font-size: 3rem; margin-bottom: 0.5rem;">🖼️</div>
                <div style="font-size: 1.1rem; font-weight: 600; color: #f1f5f9;">Your poster is ready!</div>
                <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.3rem;">Colorful, well-designed poster with catchy taglines and visual layout</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.download_button(
            "📥 Download Poster PDF",
            data=st.session_state["gen_poster"],
            file_name="studybuddy_poster.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        if st.button("✖ Close Poster", key="close_poster"):
            del st.session_state["gen_poster"]
            st.rerun()

    # ── YouTube Recommendations ──
    if st.session_state.get("gen_youtube_recs"):
        st.markdown("---")
        st.markdown("### 🎥 Recommended YouTube Videos")
        recs = st.session_state["gen_youtube_recs"]
        for topic_group in recs:
            topic = topic_group.get("topic", "")
            videos = topic_group.get("videos", [])
            st.markdown(
                f"""
                <div style="background: linear-gradient(145deg, #1a1a35, #1e1e3a); border: 1px solid rgba(124,58,237,0.15);
                            border-radius: 14px; padding: 1rem 1.2rem; margin: 0.8rem 0;">
                    <div style="font-weight:700; color:#a78bfa; font-size:0.95rem; margin-bottom:0.6rem;">📌 {topic}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for v in videos:
                st.markdown(
                    f"""
                    <div style="background: #141428; border: 1px solid rgba(124,58,237,0.08);
                                border-radius: 12px; padding: 0.8rem 1rem; margin: 0.3rem 0;
                                display: flex; align-items: center; gap: 0.8rem;">
                        <div style="font-size: 1.5rem;">▶️</div>
                        <div>
                            <a href="{v.get('link', '#')}" target="_blank"
                               style="color: #f1f5f9; font-weight:600; font-size:0.88rem; text-decoration:none;">
                                {v.get('title', 'Video')}
                            </a>
                            <div style="font-size:0.75rem; color:#64748b; margin-top:0.2rem;">
                                {v.get('channel', '')} · {v.get('duration', '')}
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        if st.button("✖ Close Recommendations", key="close_yt_recs"):
            del st.session_state["gen_youtube_recs"]
            st.rerun()

    # ── Mind Map ──
    if st.session_state.get("gen_mindmap"):
        st.markdown("---")
        st.markdown("### 🧠 Mind Map")

        mermaid_code = st.session_state["gen_mindmap"]
        # Clean up the mermaid code
        mermaid_code = mermaid_code.strip()
        if mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("```")[1]
            if mermaid_code.startswith("mermaid"):
                mermaid_code = mermaid_code[7:]
            mermaid_code = mermaid_code.strip()

        # Render Mermaid diagram inline with built-in download button
        mermaid_html = f"""
        <div style="background: #1a1a35; border-radius: 16px; padding: 1.5rem;
                    border: 1px solid rgba(124,58,237,0.2); margin: 1rem 0;">
            <div class="mermaid" id="mm-container">
            {mermaid_code}
            </div>
        </div>
        <div style="text-align:center; margin: 0.8rem 0;">
            <button onclick="downloadMindMapPNG()" style="
                padding: 0.6rem 1.5rem;
                background: linear-gradient(135deg, #6d28d9, #7c3aed, #8b5cf6);
                color: #fff; border: none; border-radius: 12px;
                font-size: 0.9rem; font-weight: 600; cursor: pointer;
                box-shadow: 0 4px 14px rgba(124,58,237,0.3);
            ">⬇️ Download Mind Map as PNG</button>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <script>
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'dark',
                themeVariables: {{
                    primaryColor: '#7c3aed',
                    primaryTextColor: '#f1f5f9',
                    primaryBorderColor: '#8b5cf6',
                    lineColor: '#a78bfa',
                    secondaryColor: '#1a1a35',
                    tertiaryColor: '#141428',
                    fontSize: '14px'
                }}
            }});
            function downloadMindMapPNG() {{
                var svgEl = document.querySelector('#mm-container svg');
                if (!svgEl) {{ alert('Mind map not rendered yet.'); return; }}
                var svgData = new XMLSerializer().serializeToString(svgEl);
                var canvas = document.createElement('canvas');
                var ctx = canvas.getContext('2d');
                var img = new Image();
                var blob = new Blob([svgData], {{type: 'image/svg+xml;charset=utf-8'}});
                var url = URL.createObjectURL(blob);
                img.onload = function() {{
                    canvas.width = img.width * 2;
                    canvas.height = img.height * 2;
                    ctx.fillStyle = '#0f0f1a';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    URL.revokeObjectURL(url);
                    canvas.toBlob(function(b) {{
                        var a = document.createElement('a');
                        a.href = URL.createObjectURL(b);
                        a.download = 'studybuddy_mindmap.png';
                        a.click();
                    }}, 'image/png');
                }};
                img.src = url;
            }}
        </script>
        """
        components.html(mermaid_html, height=550, scrolling=True)

        # HTML file download option
        html_content = export_service.export_mindmap_to_html(mermaid_code)
        st.download_button(
            "📥 Download Mind Map (HTML)",
            data=html_content,
            file_name="studybuddy_mindmap.html",
            mime="text/html",
            use_container_width=True,
        )

        if st.button("✖ Close Mind Map", key="close_mm"):
            del st.session_state["gen_mindmap"]
            st.rerun()

    # ── Video Overview ──
    if st.session_state.get("gen_video"):
        st.markdown("---")
        st.markdown("### 🎬 Video Overview Script")
        st.markdown(st.session_state["gen_video"])
        if st.button("✖ Close Video", key="close_video"):
            del st.session_state["gen_video"]
            st.rerun()

    # ── Quiz ──
    if st.session_state.get("quiz_state"):
        st.markdown("---")
        st.markdown("### ❓ Quiz Time!")
        _render_quiz()

    # ── Audio (FIXED: audio player FIRST, then text summary) ──
    if st.session_state.get("gen_audio"):
        st.markdown("---")
        st.markdown("### 🔊 Audio Summary")

        # Audio player FIRST — immediately visible and ready to play
        audio_ready = False
        try:
            audio_path = export_service.text_to_speech_file("audio_overview", st.session_state["gen_audio"])
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            st.markdown(
                """
                <div style="background: linear-gradient(145deg, #1a1a35, #1e1e3a); border: 1px solid rgba(124,58,237,0.2);
                            border-radius: 16px; padding: 1.5rem; text-align: center; margin: 0.5rem 0 1rem;">
                    <div style="font-size: 2.5rem; margin-bottom: 0.3rem;">🎧</div>
                    <div style="font-size: 1rem; font-weight: 600; color: #a78bfa;">Audio is ready! Press play below.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.audio(audio_bytes, format="audio/mp3")
            audio_ready = True
        except Exception:
            st.warning("⚠️ Audio generation failed. Text summary is shown below.")

        # Text summary AFTER audio player
        st.markdown("#### 📝 Text Summary")
        st.markdown(st.session_state["gen_audio"])

        if st.button("✖ Close Audio", key="close_audio"):
            del st.session_state["gen_audio"]
            st.rerun()


# ═══════════════════════════════════════════════════════════════
#  QUIZ RENDERER
# ═══════════════════════════════════════════════════════════════

def _render_quiz():
    questions = st.session_state["quiz_state"]
    submitted = st.session_state.get("quiz_submitted", False)

    if not submitted:
        with st.form("quiz_form"):
            for i, q in enumerate(questions):
                st.markdown(
                    f"""
                    <div style="background: #1a1a35; border: 1px solid rgba(124,58,237,0.15);
                                border-radius: 12px; padding: 1rem 1.2rem; margin: 0.8rem 0 0.3rem;">
                        <span style="color: #a78bfa; font-weight: 700; font-size: 0.85rem;">Q{i+1}</span>
                        <span style="color: #f1f5f9; font-weight: 600; margin-left: 0.5rem;">{q.get('question', '')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                options = q.get("options", [])
                selected = st.radio(
                    f"Select answer for Q{i+1}",
                    options=options,
                    index=None,
                    key=f"quiz_q_{i}",
                    label_visibility="collapsed",
                )
                st.session_state["quiz_answers"][i] = selected

            st.markdown("")
            if st.form_submit_button("✅ Submit Quiz", use_container_width=True):
                # Check that at least one answer is selected
                answers = st.session_state.get("quiz_answers", {})
                unanswered = [k for k, v in answers.items() if v is None]
                if unanswered:
                    st.warning(f"⚠️ Please answer all questions before submitting. {len(unanswered)} question(s) unanswered.")
                else:
                    st.session_state["quiz_submitted"] = True
                    st.rerun()
    else:
        # Calculate score first
        score = 0
        total = len(questions)
        for i, q in enumerate(questions):
            user_answer = st.session_state["quiz_answers"].get(i, "")
            correct = q.get("correct_answer", "")
            if user_answer == correct:
                score += 1

        # ── Score Summary Card (shown at top) ──
        pct = int(score / total * 100) if total else 0
        if pct >= 70:
            color = "#22c55e"
            emoji = "🎉"
            msg = "Excellent work!"
        elif pct >= 40:
            color = "#f59e0b"
            emoji = "💪"
            msg = "Good effort! Review the explanations below."
        else:
            color = "#ef4444"
            emoji = "📚"
            msg = "Keep studying! Check the explanations below."

        st.markdown(
            f"""
            <div style="text-align:center; padding:2rem; background: linear-gradient(145deg, #141428, #1a1a35);
                        border-radius: 20px; border: 2px solid {color}; margin-bottom: 1.5rem;
                        box-shadow: 0 8px 32px rgba(0,0,0,0.3);">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">{emoji}</div>
                <div style="font-size: 3rem; font-weight: 800; color: {color} !important;">{score} / {total}</div>
                <div style="font-size: 1.1rem; color: #94a3b8; margin-top: 0.3rem;">Score: {pct}%</div>
                <div style="font-size: 0.9rem; color: {color} !important; margin-top: 0.5rem; font-weight: 600;">{msg}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Per-question results ──
        st.markdown("#### 📋 Detailed Results")
        for i, q in enumerate(questions):
            user_answer = st.session_state["quiz_answers"].get(i, "")
            correct = q.get("correct_answer", "")
            explanation = q.get("explanation", "")
            is_correct = user_answer == correct

            if is_correct:
                st.markdown(
                    f"""
                    <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.3);
                                border-radius: 12px; padding: 1rem 1.2rem; margin: 0.5rem 0;">
                        <div style="font-weight: 700; color: #22c55e !important; margin-bottom: 0.3rem;">✅ Q{i+1}. {q.get('question', '')}</div>
                        <div style="color: #94a3b8; font-size: 0.88rem;">Your answer: <strong style="color: #22c55e !important;">{user_answer}</strong></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3);
                                border-radius: 12px; padding: 1rem 1.2rem; margin: 0.5rem 0;">
                        <div style="font-weight: 700; color: #ef4444 !important; margin-bottom: 0.4rem;">❌ Q{i+1}. {q.get('question', '')}</div>
                        <div style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.2rem;">
                            Your answer: <span style="text-decoration: line-through; color: #ef4444 !important;">{user_answer}</span>
                        </div>
                        <div style="color: #94a3b8; font-size: 0.88rem; margin-bottom: 0.4rem;">
                            Correct answer: <strong style="color: #22c55e !important;">{correct}</strong>
                        </div>
                        <div style="background: rgba(124,58,237,0.08); border-radius: 8px; padding: 0.6rem 0.8rem;
                                    border-left: 3px solid #7c3aed; margin-top: 0.3rem;">
                            <span style="color: #a78bfa !important; font-weight: 600; font-size: 0.78rem;">💡 EXPLANATION</span><br>
                            <span style="color: #e2e8f0; font-size: 0.85rem;">{explanation}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Save score
        try:
            repo.save_quiz_score(
                st.session_state.user["id"],
                st.session_state.session_id,
                "AI Quiz",
                score,
                total,
            )
        except Exception:
            pass

        st.markdown("")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Retake Quiz", key="retake_quiz", use_container_width=True):
                st.session_state["quiz_submitted"] = False
                st.session_state["quiz_answers"] = {}
                st.rerun()
        with c2:
            if st.button("✖ Close Quiz", key="close_quiz", use_container_width=True):
                st.session_state["quiz_state"] = None
                st.session_state["quiz_submitted"] = False
                st.session_state["quiz_answers"] = {}
                st.rerun()
        return  # Skip the close button below since we included it above

    if st.button("✖ Close Quiz", key="close_quiz"):
        st.session_state["quiz_state"] = None
        st.session_state["quiz_submitted"] = False
        st.session_state["quiz_answers"] = {}
        st.rerun()


# ═══════════════════════════════════════════════════════════════
#  PAGE: EXAM QUESTION PREDICTOR
# ═══════════════════════════════════════════════════════════════

def render_exam_predictor() -> None:
    user_id = st.session_state.user["id"]
    mode = st.session_state.user.get("preferred_mode", "Student Mode")
    kb = repo.build_session_knowledge_base(user_id, st.session_state.session_id)

    _render_page_header("🎯 Exam Question Predictor", "Upload past papers and predict exam questions with AI")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### Upload Past Questions")
        with st.form("exam_upload_form"):
            subject = st.text_input("Subject", placeholder="e.g., Data Structures, Physics")
            year = st.text_input("Year", placeholder="e.g., 2024, 2023")
            q_file = st.file_uploader("Upload question paper", type=["pdf", "docx", "txt"])
            q_text = st.text_area("Or paste questions manually", height=150, placeholder="Paste past exam questions here...")
            submit = st.form_submit_button("📤 Upload Questions", use_container_width=True)

        if submit and subject.strip():
            text = q_text.strip()
            if q_file:
                try:
                    text = content_service.extract_text_from_upload(q_file.name, q_file.read())
                except Exception as exc:
                    st.error(f"Failed to read file: {exc}")
            if text:
                repo.add_exam_question(user_id, subject.strip(), year.strip(), text)
                st.success("✅ Questions uploaded!")
                st.rerun()
            else:
                st.warning("Please provide question content.")

        # Show uploaded questions
        questions = repo.fetch_exam_questions(user_id)
        if questions:
            st.markdown("### 📚 Your Uploaded Papers")
            for q in questions:
                with st.expander(f"{q['subject']} — {q['year'] or 'N/A'}"):
                    st.text(q["question_text"][:500] + ("..." if len(q["question_text"]) > 500 else ""))

    with col2:
        st.markdown("### 🔮 Predicted Questions")

        if st.button("🧠 Predict Exam Questions", use_container_width=True):
            questions = repo.fetch_exam_questions(user_id)
            if not questions:
                st.warning("Upload past papers first!")
            else:
                past_text = "\n\n".join([f"[{q['subject']} {q['year']}]\n{q['question_text']}" for q in questions])
                with st.spinner("Analyzing patterns..."):
                    try:
                        predictions = ai_service.predict_exam_questions(past_text, kb or "No study material uploaded.", mode)
                        if predictions:
                            subject = questions[0]["subject"]
                            repo.save_predicted_questions(user_id, subject, predictions)
                            st.session_state["exam_predictions"] = predictions
                            st.rerun()
                    except Exception as exc:
                        st.error(f"Prediction failed: {exc}")

        # Show predictions
        preds = st.session_state.get("exam_predictions") or repo.fetch_predicted_questions(user_id)
        if preds:
            for i, p in enumerate(preds):
                q_text = p.get("predicted_question", p.get("question", ""))
                conf = p.get("confidence", "Medium")
                conf_class = f"confidence-{conf.lower()}"
                card_html = (
                    f'<div class="pred-card {conf_class}">'
                    f'<div style="font-weight:600; font-size:0.92rem; margin-bottom:0.3rem;">Q{i+1}. {q_text}</div>'
                    f'<div style="font-size:0.78rem; color:#64748b;">'
                    f'Confidence: <strong>{conf}</strong>'
                    f'{" &middot; " + p.get("topic", "") if p.get("topic") else ""}'
                    f'</div></div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

            # ── PDF Generation + Email (Feature 5) ──
            st.markdown("---")
            st.markdown(f"### 📄 {_t('Export Predictions')}")

            # Generate PDF of predictions
            try:
                pred_subject = ""
                questions_list = repo.fetch_exam_questions(user_id)
                if questions_list:
                    pred_subject = questions_list[0].get("subject", "Exam")
                pdf_bytes = export_service.export_predictions_to_pdf(preds, subject=pred_subject or "Exam")
                st.download_button(
                    f"📥 {_t('Download Predictions as PDF')}",
                    data=pdf_bytes,
                    file_name="predicted_questions.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as exc:
                st.error(f"{_t('PDF generation failed')}: {exc}")

            # Send via Email
            st.markdown("---")
            st.markdown(f"### 📧 {_t('Send via Email')}")
            email_input = st.text_input(
                _t("Enter email address"),
                placeholder="student@example.com",
                key="pred_email_input",
            )
            if st.button(f"📧 {_t('Send PDF to Email')}", use_container_width=True, key="send_pred_email"):
                if not email_input or not email_input.strip():
                    st.warning(_t("Please enter an email address."))
                else:
                    with st.spinner(_t("Sending email...")):
                        try:
                            pred_subject = "Exam"
                            qlist = repo.fetch_exam_questions(user_id)
                            if qlist:
                                pred_subject = qlist[0].get("subject", "Exam")
                            email_pdf = export_service.export_predictions_to_pdf(preds, subject=pred_subject)
                            export_service.send_email_with_attachment(
                                to_email=email_input.strip(),
                                subject=f"StudyBuddy AI - Predicted {pred_subject} Exam Questions",
                                body=(
                                    f"Hi,\n\nPlease find attached the predicted exam questions for {pred_subject}.\n\n"
                                    f"This PDF contains {len(preds)} predicted questions with confidence levels.\n\n"
                                    "Generated by StudyBuddy AI - Smart Learning Assistant\n"
                                ),
                                attachment_bytes=email_pdf,
                                attachment_filename="predicted_questions.pdf",
                            )
                            st.success(f"✅ {_t('PDF sent to')} {email_input.strip()}!")
                        except Exception as exc:
                            st.error(f"{_t('Email failed')}: {exc}")


# ═══════════════════════════════════════════════════════════════
#  PAGE: REVISION TOOL
# ═══════════════════════════════════════════════════════════════

def render_revision() -> None:
    user_id = st.session_state.user["id"]
    mode = st.session_state.user.get("preferred_mode", "Student Mode")
    kb = repo.build_session_knowledge_base(user_id, st.session_state.session_id)

    _render_page_header("📝 Revision Tool", "Generate comprehensive revision summaries from all your content")

    if not kb.strip():
        st.info("📄 Upload some sources from the Dashboard first, then come back here to generate a revision summary.")
        return

    if st.button("🧠 Generate Revision Summary", use_container_width=True):
        with st.spinner("Creating comprehensive revision summary..."):
            try:
                summary = ai_service.generate_revision_summary(kb, mode)
                st.session_state["revision_summary"] = summary
                st.rerun()
            except Exception as exc:
                st.error(f"Failed: {exc}")

    if st.session_state.get("revision_summary"):
        st.markdown("---")
        st.markdown(st.session_state["revision_summary"])
        pdf_bytes = export_service.export_text_to_pdf("Revision Summary", st.session_state["revision_summary"])
        st.download_button("📥 Download PDF", data=pdf_bytes, file_name="revision_summary.pdf", use_container_width=True)


# ═══════════════════════════════════════════════════════════════
#  PAGE: LEARN TOGETHER
# ═══════════════════════════════════════════════════════════════

def render_learn_together() -> None:
    user_id = st.session_state.user["id"]
    user_name = st.session_state.user["name"]

    _render_page_header("👥 Learn Together", "Create or join study rooms for collaborative learning")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 🏠 Create Study Room")
        with st.form("create_room_form"):
            room_name = st.text_input("Room Name", placeholder="e.g., Physics Study Group")
            room_desc = st.text_area("Description", placeholder="What will you study?", height=80)
            create = st.form_submit_button("✨ Create Room", use_container_width=True)
        if create and room_name.strip():
            result = repo.create_study_room(user_id, room_name.strip(), room_desc.strip())
            st.success(f"Room created! Share code: **{result['room_code']}**")
            st.rerun()

    with col2:
        st.markdown("### 🔗 Join Study Room")
        with st.form("join_room_form"):
            room_code = st.text_input("Room Code", placeholder="Enter 8-character code")
            join = st.form_submit_button("🤝 Join Room", use_container_width=True)
        if join and room_code.strip():
            result = repo.join_study_room(room_code.strip().upper(), user_id)
            if result:
                st.success(f"Joined: {result['room_name']}")
                st.rerun()
            else:
                st.error("Invalid room code.")

    st.markdown("---")

    # My rooms
    rooms = repo.fetch_user_rooms(user_id)
    if rooms:
        st.markdown("### 📋 Your Study Rooms")
        for room in rooms:
            with st.expander(f"🏠 {room['room_name']}  ·  {room['member_count']} member(s)  ·  Code: {room['room_code']}"):
                if room.get("description"):
                    st.caption(room["description"])

                # Members
                members = repo.fetch_room_members(room["id"])
                member_names = ", ".join([f"👤 {m['name']}" for m in members])
                st.markdown(f"**Members:** {member_names}")

                st.markdown("---")

                # ── Two tabs: Chat, Notes ──
                tab_chat, tab_notes = st.tabs(["💬 Chat", "📋 Notes"])

                # ── TAB: Chat ──
                with tab_chat:
                    messages = repo.fetch_room_messages(room["id"])
                    if messages:
                        for msg in messages:
                            is_me = msg["author_name"] == user_name
                            align = "right" if is_me else "left"
                            bg = "rgba(124,58,237,0.12)" if is_me else "#1a1a35"
                            st.markdown(
                                f"""
                                <div style="text-align:{align}; margin:0.3rem 0;">
                                    <div style="display:inline-block; background:{bg}; border-radius:12px;
                                                padding:0.5rem 0.9rem; max-width:80%; text-align:left;
                                                border: 1px solid rgba(124,58,237,0.1);">
                                        <div style="font-size:0.72rem; font-weight:700; color:#a78bfa; margin-bottom:0.2rem;">{msg['author_name']}</div>
                                        <div style="font-size:0.88rem; color:#e2e8f0;">{msg['content']}</div>
                                        <div style="font-size:0.65rem; color:#475569; margin-top:0.2rem;">{str(msg.get('created_at', ''))[:16]}</div>
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                    else:
                        st.caption("No messages yet. Start the conversation!")

                    with st.form(f"room_msg_{room['id']}"):
                        msg_text = st.text_input("Message", placeholder="Type a message...", key=f"msg_input_{room['id']}", label_visibility="collapsed")
                        if st.form_submit_button("📤 Send", use_container_width=True) and msg_text.strip():
                            repo.send_room_message(room["id"], user_id, msg_text.strip())
                            st.rerun()


                # ── TAB: Notes ──
                with tab_notes:
                    st.markdown("##### ✏️ Add a Shared Note")
                    with st.form(f"room_note_{room['id']}"):
                        note_title = st.text_input("Note Title", placeholder="e.g., Chapter 5 Summary", key=f"note_title_{room['id']}")
                        note_content = st.text_area("Note Content", placeholder="Write your notes, key points, or summaries here...", height=120, key=f"note_content_{room['id']}")
                        if st.form_submit_button("📝 Post Note", use_container_width=True):
                            if note_title.strip() and note_content.strip():
                                repo.add_room_note(room["id"], user_id, note_title.strip(), note_content.strip())
                                st.success("Note shared!")
                                st.rerun()
                            else:
                                st.warning("Please fill both title and content.")

                    st.markdown("---")

                    # Display shared notes
                    st.markdown("##### 📋 Shared Notes")
                    notes = repo.fetch_room_notes(room["id"])
                    if notes:
                        for note in notes:
                            st.markdown(
                                f"""
                                <div style="background: linear-gradient(145deg, #1a1a35, #1e1e3a);
                                            border: 1px solid rgba(124,58,237,0.15);
                                            border-radius: 14px; padding: 1rem 1.2rem; margin: 0.5rem 0;">
                                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                                        <div style="font-weight:700; font-size:0.95rem; color:#a78bfa;">{note['title']}</div>
                                        <div style="font-size:0.7rem; color:#475569;">{str(note.get('created_at', ''))[:16]}</div>
                                    </div>
                                    <div style="font-size:0.88rem; color:#e2e8f0; line-height:1.6; white-space:pre-wrap;">{note['content']}</div>
                                    <div style="font-size:0.72rem; color:#64748b; margin-top:0.4rem;">— {note['author_name']}</div>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            if note.get("user_id") == user_id:
                                if st.button("🗑️ Delete", key=f"del_note_{note['id']}", help="Delete this note"):
                                    repo.delete_room_note(note["id"])
                                    st.rerun()
                    else:
                        st.caption("No shared notes yet. Post notes to help your study group!")
    else:
        st.info("You haven't joined any study rooms yet. Create or join one above!")


# ═══════════════════════════════════════════════════════════════
#  PAGE: TEXTBOOK SEARCH
# ═══════════════════════════════════════════════════════════════

def render_textbook_search() -> None:
    _render_page_header("📚 Textbook Search", "Search textbooks shared by other users")

    # Share a textbook
    user_id = st.session_state.user["id"]
    sources = repo.fetch_session_sources(user_id, st.session_state.session_id)

    with st.expander("📤 Share a source as textbook"):
        if sources:
            source_names = [s["source_name"] for s in sources]
            selected = st.selectbox("Select source to share", source_names)
            textbook_name = st.text_input("Textbook name", placeholder="e.g., Introduction to Physics")
            textbook_topic = st.text_input("Topic/Subject", placeholder="e.g., Physics, Calculus")
            if st.button("📤 Share", use_container_width=True):
                src = next((s for s in sources if s["source_name"] == selected), None)
                if src and textbook_name.strip():
                    repo.share_as_textbook(
                        src["id"], user_id, textbook_name.strip(),
                        textbook_topic.strip(), src.get("extracted_text", "")[:50000]
                    )
                    st.success("Textbook shared!")
        else:
            st.caption("Upload sources first to share them as textbooks.")

    st.markdown("---")

    # Search
    search_query = st.text_input("🔍 Search textbooks", placeholder="Search by name or topic...")
    if search_query.strip():
        results = repo.search_textbooks(search_query.strip())
        if results:
            for tb in results:
                with st.expander(f"📕 {tb['textbook_name']} — {tb['topic']}"):
                    st.caption(f"Shared by: {tb['shared_by']} on {str(tb['created_at'])[:10]}")
                    content = repo.get_textbook_content(tb["id"])
                    if content and content.get("content"):
                        st.text(content["content"][:2000] + "...")
        else:
            st.info("No textbooks found for your search.")


# ═══════════════════════════════════════════════════════════════
#  PAGE: COMMUNITY
# ═══════════════════════════════════════════════════════════════

def render_community() -> None:
    user_id = st.session_state.user["id"]
    user_name = st.session_state.user["name"]

    _render_page_header("💬 Community", "Share questions, insights, and discussions with other learners")

    # New post
    with st.form("new_post_form"):
        post_content = st.text_area(
            "What's on your mind?",
            placeholder="Share a question, insight, or study tip...",
            height=100,
            label_visibility="collapsed",
        )
        post_btn = st.form_submit_button("📮 Post", use_container_width=True)

    if post_btn and post_content.strip():
        repo.create_community_post(user_id, post_content.strip())
        st.success("Posted!")
        st.rerun()

    st.markdown("---")

    # Posts feed
    posts = repo.fetch_community_posts(limit=30)
    if not posts:
        st.info("No posts yet. Be the first to share something!")
        return

    for post in posts:
        st.markdown(
            f"""
            <div class="post-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem;">
                    <span class="post-author">👤 {post['author_name']}</span>
                    <span class="post-time">{str(post['created_at'])[:16]}</span>
                </div>
                <div style="font-size:0.92rem; line-height:1.6;">{post['content']}</div>
                <div style="margin-top:0.6rem; font-size:0.78rem; color:#64748b !important;">
                    ❤️ {post['likes_count']} · 💬 {post['reply_count']} replies
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button(f"❤️ Like", key=f"like_{post['id']}", use_container_width=True):
                repo.like_post(post["id"])
                st.rerun()
        with c2:
            pass  # spacer

        # Replies
        with st.expander(f"💬 {post['reply_count']} replies", expanded=False):
            replies = repo.fetch_replies(post["id"])
            for reply in replies:
                st.markdown(f"**{reply['author_name']}**: {reply['content']}")
                st.caption(str(reply["created_at"])[:16])

            with st.form(f"reply_form_{post['id']}"):
                reply_text = st.text_input("Reply", placeholder="Write a reply...", key=f"reply_input_{post['id']}", label_visibility="collapsed")
                if st.form_submit_button("Reply", use_container_width=True):
                    if reply_text.strip():
                        repo.create_reply(post["id"], user_id, reply_text.strip())
                        st.rerun()


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _render_page_header(title: str, subtitle: str = "") -> None:
    """Render a page header with back button and language selector."""
    _render_language_selector()
    if st.button(_t("← Back to Dashboard"), key="back_to_dash"):
        st.session_state.page = "dashboard"
        st.rerun()

    header_html = (
        f'<div class="page-header">'
        f'<h2>{_t(title)}</h2>'
        f'<div style="color:#64748b; font-size:0.9rem;">{_t(subtitle)}</div>'
        f'</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
#  SETUP SCREEN
# ═══════════════════════════════════════════════════════════════

def render_setup(db_message: str) -> None:
    st.markdown(
        """
        <div style="text-align:center; padding:3rem;">
            <div style="font-size:3rem; margin-bottom:1rem;">⚙️</div>
            <h2>Setup Required</h2>
            <p style="color:#64748b;">Configure your MySQL database to get started.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.error(db_message)
    st.markdown("### Steps to fix:")
    st.markdown("1. Create `.env` from `.env.example` with your MySQL password.")
    st.markdown("2. Run `schema.sql` in MySQL.")
    st.markdown("3. Restart with `python -m streamlit run app.py`.")


# ═══════════════════════════════════════════════════════════════
#  MAIN APP — Router
# ═══════════════════════════════════════════════════════════════

def run_app() -> None:
    st.set_page_config(
        page_title="StudyBuddy AI — Smart Learning Assistant",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    inject_css()

    # DB check
    db_ok, db_msg = check_database_status()
    if not db_ok:
        render_setup(db_msg)
        return

    # Auth check
    if not st.session_state.user:
        render_auth()
        return

    # Page router — right sidebar icons open separate pages
    page = st.session_state.page

    if page == "dashboard":
        render_dashboard()
    elif page == "exam_predictor":
        render_exam_predictor()
    elif page == "revision":
        render_revision()
    elif page == "learn_together":
        render_learn_together()
    elif page == "textbook_search":
        render_textbook_search()
    elif page == "community":
        render_community()
    else:
        st.session_state.page = "dashboard"
        st.rerun()
