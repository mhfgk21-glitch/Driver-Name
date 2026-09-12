# pyrefly: ignore [missing-import]
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from io import BytesIO
from datetime import date, datetime, timedelta

try:
    import extra_streamlit_components as stx
except ImportError:
    stx = None

# ─── إعدادات الصفحة ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="نظام بيانات المندوبين",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "current_role" not in st.session_state:
    st.session_state.current_role = None
if "show_user_management" not in st.session_state:
    st.session_state.show_user_management = False
if "current_page" not in st.session_state:
    st.session_state.current_page = "home"

AUTH_USERS = {
    os.getenv("APP_ADMIN_USERNAME", "admin"): {
        "password": os.getenv("APP_ADMIN_PASSWORD", "admin123"),
        "role": "admin",
        "label": "مدير النظام",
    },
    os.getenv("APP_EMPLOYEE_USERNAME", "employee"): {
        "password": os.getenv("APP_EMPLOYEE_PASSWORD", "employee123"),
        "role": "employee",
        "label": "موظف",
    },
}


USERS_DB_PATH = os.getenv("APP_USERS_DB", "users.db")


def load_managed_users() -> dict:
    with sqlite3.connect(USERS_DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                label TEXT NOT NULL
            )
        """)
        for username, account in AUTH_USERS.items():
            connection.execute(
                """INSERT OR IGNORE INTO users (username, password, role, label)
                   VALUES (?, ?, ?, ?)""",
                (username, account["password"], account["role"], account["label"]),
            )
        rows = connection.execute(
            "SELECT username, password, role, label FROM users"
        ).fetchall()
    return {
        username: {"password": password, "role": role, "label": label}
        for username, password, role, label in rows
    }


def save_managed_user(username: str, account: dict) -> None:
    with sqlite3.connect(USERS_DB_PATH) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO users (username, password, role, label)
               VALUES (?, ?, ?, ?)""",
            (username, account["password"], account["role"], account["label"]),
        )


def delete_managed_user(username: str) -> None:
    with sqlite3.connect(USERS_DB_PATH) as connection:
        connection.execute("DELETE FROM users WHERE username = ?", (username,))


if "managed_users" not in st.session_state:
    st.session_state.managed_users = load_managed_users()

SESSION_TTL_SECONDS = 12 * 60 * 60
SESSION_SECRET = os.getenv("APP_SESSION_SECRET", "driver-number-session-secret")
MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024
PASSWORD_HASH_ITERATIONS = 310_000
cookie_manager = stx.CookieManager(key="session_cookie_manager") if stx else None


def create_session_token(username: str, role: str) -> str:
    payload = {
        "username": username,
        "role": role,
        "expires": int(time.time()) + SESSION_TTL_SECONDS,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, stored_password: str) -> bool:
    if not stored_password.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored_password)

    try:
        _, iterations_text, salt_text, digest_text = stored_password.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def restore_session_from_query() -> None:
    cookies = cookie_manager.get_all() if cookie_manager else {}
    token = st.query_params.get("auth") or cookies.get("auth")
    if not token or st.session_state.authenticated:
        return

    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(
            SESSION_SECRET.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid session signature")

        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        account = st.session_state.managed_users.get(payload["username"])
        if payload["expires"] <= int(time.time()) or not account:
            raise ValueError("expired session")
        if account["role"] != payload["role"]:
            raise ValueError("role mismatch")

        st.session_state.authenticated = True
        st.session_state.current_user = payload["username"]
        st.session_state.current_role = payload["role"]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        st.query_params.pop("auth", None)
        if cookie_manager:
            cookie_manager.delete("auth")


restore_session_from_query()

# ─── CSS مخصص ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
@import url('https://unpkg.com/primeicons@7.0.0/primeicons.css');

:root {
    --font-sans: 'Cairo', ui-sans-serif, system-ui, sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    --ink: #172033;
    --muted: #667085;
    --line: #e4e8ef;
    --surface: #ffffff;
    --surface-soft: #f8fafc;
    --brand: #0f766e;
    --brand-dark: #115e59;
    --brand-soft: #ccfbf1;
    --shadow: 0 12px 30px rgba(23, 32, 51, 0.08);

    /* PrimeNG Design Tokens */
    --surface-a: #ffffff;
    --surface-b: #f8f9fa;
    --surface-c: #e9ecef;
    --surface-d: #dee2e6;
    --surface-ground: #eff3f8;
    --surface-section: #ffffff;
    --surface-card: #ffffff;
    --surface-overlay: #ffffff;
    --surface-border: #dfe7ef;
    --surface-hover: #f6f9fc;
    --text-color: #495057;
    --text-color-secondary: #6c757d;
    --primary-color: #532BFD;
    --primary-color-text: #ffffff;
    --primary-50: #f7f7fe;
    --primary-100: #dadafc;
    --primary-200: #bcbdf9;
    --primary-300: #9ea0f6;
    --primary-400: #8183f4;
    --primary-500: #532BFD;
    --primary-600: #5457cd;
    --primary-700: #4547a9;
    --primary-800: #363885;
    --primary-900: #282960;
    --border-radius: 6px;
    --focus-ring: 0 0 0 0.2rem #C7D2FE;
    --maskbg: rgba(0, 0, 0, 0.4);
}

body, .stApp {
    font-family: var(--font-sans);
    direction: rtl;
    color: var(--ink);
}

*, p, span, div, button, input, select, textarea, label, h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-sans);
    direction: rtl;
}

[data-testid="stIconMaterial"] {
    display: none !important;
}

.stApp {
    background: #f3f6f9;
    min-height: 100vh;
}

.stat-card {
    box-sizing: border-box;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 18px 16px;
    text-align: center;
    box-shadow: var(--shadow);
    transition: transform 0.2s ease;
    height: 112px;
}

.stat-card:hover {
    transform: translateY(-2px);
    border-color: #b7d8d4;
}

.stat-value {
    color: var(--ink);
    font-size: 2rem;
    font-weight: 900;
    margin: 6px 0;
}

.stat-label {
    color: var(--muted);
    font-size: 0.9rem;
}

.stat-blue  { color: #2563eb; }
.stat-green { color: #0f766e; }
.stat-orange{ color: #c2410c; }
.stat-purple{ color: #7c3aed; }

.status-card {
    border-radius: 10px;
    padding: 18px;
    margin-bottom: 16px;
    border: 1px solid var(--line);
    background: var(--surface);
}

.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 5px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 7px;
    padding: 9px 18px;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 600;
    color: var(--muted);
    background: transparent;
    border: none;
}

.stTabs [aria-selected="true"] {
    background: var(--brand) !important;
    color: white !important;
}

[data-testid="stSidebar"] {
    background: #ffffff;
    border-left: 1px solid var(--line);
    box-shadow: -8px 0 28px rgba(23, 32, 51, 0.04);
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem;
}

[data-testid="stSidebarCollapseButton"] button,
[data-testid="collapsedControl"] button {
    width: 38px;
    height: 38px;
    margin: 8px;
    border: 1px solid #cce5e2;
    border-radius: 8px;
    background: #f0fdfa;
    color: var(--brand);
    box-shadow: 0 4px 12px rgba(15, 118, 110, 0.1);
    transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

[data-testid="stSidebarCollapseButton"] button:hover,
[data-testid="collapsedControl"] button:hover {
    background: var(--brand);
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(15, 118, 110, 0.2);
}

[data-testid="stSidebar"] .block-container {
    padding: 1.25rem 1.1rem 1.5rem;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 11px;
    width: 100%;
    box-sizing: border-box;
    min-height: 92px;
    padding: 14px 20px;
    margin-bottom: 20px;
    background: #f0fdfa;
    border: 1px solid #ccfbf1;
    border-radius: 10px;
    margin-inline: auto;
}

.sidebar-brand .brand-icon {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: var(--brand);
    color: white;
    font-size: 1.05rem;
}

.sidebar-brand strong {
    display: block;
    color: var(--ink);
    font-size: 1rem;
    line-height: 1.35;
    text-align: center;
}

.sidebar-brand small {
    display: block;
    color: var(--muted);
    font-size: 0.76rem;
    margin-top: 2px;
    text-align: center;
}

.brand-section {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #cce5e2;
    color: var(--brand-dark);
    font-size: 0.8rem;
    font-weight: 700;
}

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: var(--ink);
    font-weight: 600;
    font-size: 0.84rem;
}

[data-testid="stSidebar"] .stToggle {
    padding: 7px 9px;
    margin: 2px 0;
    border: 1px solid transparent;
    border-radius: 8px;
    transition: background 0.2s ease, border-color 0.2s ease;
}

[data-testid="stSidebar"] .stToggle:hover {
    background: var(--surface-soft);
    border-color: var(--line);
}

[data-testid="stSidebar"] .stTextInput {
    margin-top: 3px;
}

[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    margin-top: 3px;
    color: #be123c;
    border-color: #fecdd3;
    background: #fff1f2;
}

[data-testid="stSidebar"] .stButton > button:hover {
    color: #9f1239;
    border-color: #fda4af;
    background: #ffe4e6;
    box-shadow: 0 5px 14px rgba(190, 18, 60, 0.12);
}

[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--ink);
    font-size: 1rem;
}

.stButton > button {
    border-radius: 8px;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 700;
    padding: 9px 18px;
    transition: all 0.2s ease;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
}

.stButton > button:hover {
    transform: translateY(-1px);
    border-color: #8dc5bf;
    color: var(--brand-dark);
    box-shadow: 0 6px 18px rgba(15, 118, 110, 0.14);
}

.result-box {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 18px 20px;
    font-family: 'Cairo', sans-serif;
    white-space: pre-wrap;
    color: var(--ink);
    line-height: 1.8;
    max-height: 500px;
    overflow-y: auto;
    text-align: right;
    direction: rtl;
}

.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    margin: 2px;
}

.badge-delivery { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.badge-deferred { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-returned { background: #fff1f2; color: #be123c; border: 1px solid #fecdd3; }
.badge-delivered{ background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }

.stTextInput > div > div > input {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px !important;
    color: var(--ink) !important;
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
}

[data-testid="stFileUploader"] section {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
    height: 112px;
    padding: 10px 12px;
    background: linear-gradient(180deg, #ffffff 0%, #f8fffe 100%);
    border: 1px dashed #9ac9c4;
    border-radius: 12px;
    box-shadow: 0 5px 16px rgba(23, 32, 51, 0.05);
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

[data-testid="stFileUploader"] section:hover {
    border-color: var(--p-primary-color);
    background: #f0fdfa;
    box-shadow: 0 8px 20px rgba(15, 118, 110, 0.1);
}

[data-testid="stFileUploader"] section:focus-within {
    border-color: var(--p-primary-color);
    box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.14);
}

[data-testid="stFileUploader"] section > span {
    display: flex;
    justify-content: center;
}

[data-testid="stFileUploader"] section button {
    min-height: 34px;
    padding: 6px 14px;
    border: 1px solid var(--p-primary-color);
    border-radius: var(--p-border-radius-md);
    background: var(--p-primary-color);
    color: var(--p-primary-contrast-color);
    font-family: var(--font-sans);
    font-weight: 700;
    transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

[data-testid="stFileUploader"] section button:hover {
    border-color: var(--p-primary-hover-color);
    background: var(--p-primary-hover-color);
    color: var(--p-primary-contrast-color);
    transform: translateY(-1px);
    box-shadow: 0 5px 14px rgba(15, 118, 110, 0.2);
}

[data-testid="stFileUploader"] section button p {
    display: none;
}

[data-testid="stFileUploader"] section button::after {
    content: "اختيار ملف";
    font-family: var(--font-sans);
    font-size: 0.78rem;
}

[data-testid="stFileUploaderDropzoneInstructions"] {
    color: var(--muted);
    text-align: center;
    font-size: 0.75rem;
}

[data-testid="stFileUploaderDropzoneInstructions"]::before {
    content: "اسحب الملف هنا أو اختره من جهازك";
    display: block;
    margin-bottom: 3px;
    color: var(--ink);
    font-size: 0.74rem;
    font-weight: 600;
}

[data-testid="stFileUploaderDropzoneInstructions"] > div {
    display: none;
}

.stDataFrame {
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: var(--shadow);
}

hr { border-color: var(--line) !important; }

[data-testid="metric-container"] {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 9px;
    padding: 12px;
    box-shadow: var(--shadow);
}

.stSuccess, .stError, .stWarning, .stInfo, [data-testid="stAlert"] {
    border-radius: 8px;
}

.stMarkdown h3, .stMarkdown h4 {
    color: var(--ink);
    letter-spacing: 0;
}

.pi {
    font-size: 0.95em;
    vertical-align: -1px;
}

/* Fallback glyphs keep the icon visible when the external PrimeIcons font is blocked. */
.pi::before { font-family: var(--font-sans); font-weight: 700; }
.pi-bars::before { content: "☰"; }
.pi-sun::before { content: "☀"; }
.pi-moon::before { content: "☾"; }
.pi-wifi::before { content: "◉"; }
.pi-bell::before { content: "♢"; }
.pi-cog::before { content: "⚙"; }
.pi-sign-out::before { content: "⇥"; }
.pi-sliders-h::before { content: "⚙"; }
.pi-search::before { content: "⌕"; }
.pi-upload::before { content: "↑"; }
.pi-truck::before { content: "▣"; }
.pi-clock::before { content: "◷"; }
.pi-replay::before { content: "↶"; }
.pi-check-circle::before { content: "✓"; }
.pi-chart-bar::before { content: "▥"; }
.pi-users::before { content: "♟"; }
.pi-box::before { content: "□"; }
.pi-trophy::before { content: "★"; }
.pi-list::before { content: "☷"; }
.pi-file-edit::before { content: "✎"; }
.pi-file-excel::before { content: "▤"; }
.pi-table::before { content: "▦"; }
.pi-inbox::before { content: "⌑"; }
.pi-copy::before { content: "⧉"; }
.pi-check::before { content: "✓"; }

.pi-action {
    display: inline-grid;
    place-items: center;
    width: var(--p-button-icon-only-width);
    height: var(--p-button-icon-only-width);
    border-radius: var(--p-border-radius-lg);
    background: var(--brand-soft);
    color: var(--p-primary-color);
}

.section-title {
    display: flex;
    align-items: center;
    gap: 9px;
    color: var(--ink);
    font-size: 1.15rem;
    font-weight: 800;
    margin: 4px 0 14px;
}

.section-title .pi {
    color: var(--brand);
    font-size: 1.05em;
}

.sidebar-divider {
    height: 1px;
    margin: 15px 0;
    background: var(--line);
}

.upload-label {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border: 1px solid currentColor;
    border-radius: 10px;
    background: var(--status-soft, #f8fafc);
    font-weight: 700;
    margin-bottom: 6px;
    min-height: 50px;
    box-sizing: border-box;
}

.control-label {
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 24px;
    margin-bottom: 4px;
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 700;
}

.control-label .pi {
    color: var(--brand);
}

.theme-toolbar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-bottom: 8px;
    color: var(--muted);
    font-size: 0.82rem;
    font-weight: 700;
}

.theme-toolbar .pi {
    color: var(--brand);
    font-size: 1rem;
}

/* ── Topbar container ──────────────────────────────────────────── */
.st-key-app_topbar {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 14px;
    box-shadow: 0 4px 24px rgba(23,32,51,0.07), 0 1px 3px rgba(23,32,51,0.04);
    padding: 10px 18px 8px 18px;
    margin-bottom: 20px;
}

.st-key-app_topbar [data-testid="stHorizontalBlock"] {
    align-items: center !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    margin: 0 !important;
    gap: 12px;
}

.st-key-topbar_theme_slot,
.st-key-topbar_admin_slot,
.st-key-topbar_logout_slot {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 38px;
    width: 100%;
}

.st-key-topbar_theme_slot > div,
.st-key-topbar_admin_slot > div,
.st-key-topbar_logout_slot > div {
    width: 100%;
}

.st-key-topbar_theme_slot,
.st-key-topbar_admin_slot {
    max-width: 48px;
    margin-inline: auto;
}

.topbar-subdivider {
    height: 1px;
    background: var(--line);
    margin: 8px 0 10px 0;
    opacity: 0.8;
}

.topbar-opt-hint {
    font-size: 0.76rem;
    color: var(--muted);
    line-height: 1.4;
    padding: 5px 10px;
    background: var(--surface-soft);
    border-radius: 8px;
    border: 1px dashed var(--line);
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.st-key-opt_clear_all > button {
    height: 38px !important;
    min-height: 38px !important;
    font-size: 0.78rem !important;
    font-weight: 700 !important;
    border-radius: 2rem !important;
    border-color: #ffd0ce !important;
    background: #fff5f5 !important;
    color: #b32b23 !important;
    white-space: nowrap !important;
    padding: 0.5rem 1.15rem !important;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s !important;
}

.st-key-opt_clear_all > button:hover:not(:disabled) {
    border-color: #ff3d32 !important;
    background: #ffe4e6 !important;
    color: #9f1239 !important;
    box-shadow: 0 0 0 0.18rem rgba(255, 61, 50, 0.2) !important;
    transform: translateY(-1px) !important;
}

.st-key-opt_clear_all > button:disabled {
    opacity: 0.45 !important;
    border-color: var(--line) !important;
    background: var(--surface-soft) !important;
    color: var(--muted) !important;
}

.st-key-app_topbar [data-testid="stToggle"] {
    padding-top: 2px;
}

.st-key-app_topbar [data-testid="stToggle"] label {
    font-size: 0.83rem !important;
    font-weight: 600 !important;
    color: var(--ink) !important;
    cursor: pointer;
}

.st-key-app_topbar [data-testid="stDateInput"] label {
    font-size: 0.74rem !important;
    color: var(--muted) !important;
    font-weight: 600 !important;
    margin-bottom: 2px !important;
}

.st-key-app_topbar [data-testid="stDateInput"] input {
    height: 36px !important;
    min-height: 36px !important;
    font-size: 0.8rem !important;
    border-radius: 2rem !important;
    padding: 0.4rem 1rem !important;
}

/* Logo */
.topbar-logo {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 2rem;
    background: linear-gradient(135deg, #532BFD 0%, #3B58FF 100%);
    color: white;
    font-size: 0.88rem;
    font-weight: 900;
    letter-spacing: 0.04em;
    box-shadow: 0 3px 10px rgba(83, 43, 253, 0.25);
    margin: auto;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.topbar-logo:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 18px rgba(83, 43, 253, 0.35);
}

/* Notification bell */
/* User card */
.topbar-account {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 4px 12px;
    border: 1px solid var(--line);
    border-radius: 2rem;
    background: var(--surface-soft);
    white-space: nowrap;
    min-height: 38px;
    transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
    cursor: default;
}

.topbar-account:hover {
    border-color: #dadafc;
    background: #f7f7fe;
    box-shadow: 0 0 0 0.15rem rgba(83, 43, 253, 0.12);
}

.topbar-avatar {
    display: grid;
    place-items: center;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #532BFD, #3B58FF);
    color: white;
    font-weight: 900;
    font-size: 0.8rem;
    box-shadow: 0 2px 6px rgba(83, 43, 253, 0.25);
    flex-shrink: 0;
}

.topbar-user-text {
    display: flex;
    flex-direction: column;
    gap: 3px;
    line-height: 1;
}

.topbar-user-name {
    color: var(--ink);
    font-size: 0.77rem;
    font-weight: 700;
}

.topbar-role-badge {
    display: inline-flex;
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 0.6rem;
    font-weight: 700;
    width: fit-content;
}

.role-admin    { background: #ede9fe; color: #7c3aed; }
.role-employee { background: #ecfdf5; color: #047857; }

.login-page {
    display: flex;
    direction: rtl;
    min-height: 520px;
    margin: 2rem auto;
    overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 16px;
    box-shadow: var(--shadow);
}

.login-panel {
    display: flex;
    flex: 0 0 380px;
    flex-direction: column;
    justify-content: center;
    padding: 42px 34px;
    background: var(--surface);
}

.login-art {
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    min-height: 520px;
    background: linear-gradient(135deg, #f0fdfa, #e0f2fe);
    color: var(--brand-dark);
}

.login-art .pi {
    font-size: 8rem;
    opacity: 0.2;
}

.login-logo {
    display: grid;
    place-items: center;
    width: 58px;
    height: 58px;
    margin: 0 auto 18px;
    border-radius: 14px;
    background: var(--brand);
    color: white;
    font-size: 1.05rem;
    font-weight: 900;
}

.login-title {
    margin: 0 0 8px;
    color: var(--ink);
    font-size: 1.45rem;
    text-align: center;
}

.login-subtitle {
    margin: 0 0 24px;
    color: var(--muted);
    font-size: 0.82rem;
    text-align: center;
}

.login-panel .stTextInput input {
    min-height: 42px;
}

.login-panel .stFormSubmitButton button {
    width: 100%;
    min-height: 42px;
    border: 0;
    background: var(--brand);
    color: white;
}

.login-panel .stFormSubmitButton button:hover {
    background: var(--brand-dark);
}

/* Icon-only topbar buttons */
.st-key-theme_toggle > button {
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    padding: 0 !important;
    border-radius: 2rem !important;
    border-color: var(--line) !important;
    background: var(--surface-soft) !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    position: relative !important;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s !important;
}

.st-key-theme_toggle > button p {
    display: none !important;
}

.st-key-theme_toggle > button i.pi {
    font-size: 1.15rem !important;
    line-height: 1 !important;
    pointer-events: none !important;
    color: #f59e0b !important;
}

.stApp:has(.theme-dark-marker) .st-key-theme_toggle > button i.pi {
    color: #fcd34d !important;
}

.st-key-theme_toggle > button:not(:has(i.pi))::before {
    content: "☀" !important;
    font-family: var(--font-sans) !important;
    speak: none;
    font-style: normal !important;
    font-weight: normal !important;
    font-variant: normal !important;
    text-transform: none !important;
    font-size: 1.15rem !important;
    color: #f59e0b !important;
    line-height: 1 !important;
    display: inline-block !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.st-key-theme_toggle > button:hover {
    background: #fefbf3 !important;
    border-color: #faedc4 !important;
    box-shadow: 0 0 0 0.18rem rgba(234, 179, 8, 0.2) !important;
    transform: translateY(-1px) !important;
}

.st-key-theme_toggle > button:focus-visible,
.st-key-user_management_toggle > button:focus-visible,
.st-key-topbar_logout > button:focus-visible {
    outline: 3px solid rgba(83, 43, 253, 0.3) !important;
    outline-offset: 2px !important;
}

.stApp:has(.theme-dark-marker) .st-key-theme_toggle > button:not(:has(i.pi))::before {
    content: "☾" !important;
    font-family: var(--font-sans) !important;
    font-size: 1.15rem !important;
    color: #fcd34d !important;
}

.stApp:has(.theme-dark-marker) .st-key-theme_toggle > button:hover {
    background: rgba(252, 211, 77, 0.1) !important;
    border-color: #fcd34d !important;
    box-shadow: 0 0 0 0.18rem rgba(252, 211, 77, 0.2) !important;
}

.st-key-user_management_toggle > button {
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    padding: 0 !important;
    border-radius: 2rem !important;
    border-color: var(--line) !important;
    background: var(--surface-soft) !important;
    color: #532BFD !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    position: relative !important;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s !important;
}

.st-key-user_management_toggle > button p {
    display: none !important;
}

.st-key-user_management_toggle > button i.pi {
    font-size: 1.05rem !important;
    line-height: 1 !important;
    pointer-events: none !important;
    color: #532BFD !important;
}

.st-key-user_management_toggle > button:not(:has(i.pi))::before {
    content: "⚙" !important;
    font-family: var(--font-sans) !important;
    font-size: 1.1rem !important;
    color: #532BFD !important;
}

.st-key-user_management_toggle > button:hover {
    background: #f7f7fe !important;
    border-color: #532BFD !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 0 0 0.18rem rgba(83, 43, 253, 0.16) !important;
}

.st-key-topbar_logout > button {
    min-height: 38px;
    height: 38px;
    padding: 0.5rem 1.15rem !important;
    border-color: #ffd0ce !important;
    border-radius: 2rem !important;
    background: #fff5f5 !important;
    color: #b32b23 !important;
    font-size: 0.78rem !important;
    font-weight: 700 !important;
    white-space: nowrap;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s !important;
}

.st-key-topbar_logout > button::before {
    content: "⇥";
    font-family: var(--font-sans) !important;
    font-size: 0.85rem;
}

.st-key-topbar_logout > button:hover {
    border-color: #ff3d32 !important;
    background: #ffe4e6 !important;
    color: #9f1239 !important;
    box-shadow: 0 0 0 0.18rem rgba(255, 61, 50, 0.2) !important;
    transform: translateY(-1px) !important;
}

/* Keep every topbar icon at the same visual size. */
.st-key-theme_toggle > button i.pi,
.st-key-theme_toggle > button::before,
.st-key-user_management_toggle > button i.pi,
.st-key-user_management_toggle > button::before,
.st-key-topbar_logout > button::before {
    font-size: 1.05rem !important;
    line-height: 1 !important;
}

.st-key-opt_clear_all > button {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
}

.st-key-opt_clear_all > button::before {
    content: "⌫";
    font-family: var(--font-sans) !important;
    font-size: 0.85rem;
}

.st-key-back_home > button::before {
    content: "→";
    font-family: var(--font-sans) !important;
    font-size: 0.85rem;
}

.stDownloadButton > button::before {
    content: "↓";
    font-family: var(--font-sans) !important;
    font-size: 0.85rem;
}

/* Global button styling to match Prime rounded buttons */
.stButton > button, .stDownloadButton > button {
    border-radius: 2rem !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 6px !important;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s !important;
}

.stButton > button:focus, .stDownloadButton > button:focus {
    box-shadow: 0 0 0 0.18rem rgba(83, 43, 253, 0.2) !important;
}

.app-footer {
    margin-top: 28px;
    padding: 14px 0 6px;
    border-top: 1px solid var(--line);
    color: #98a2b3;
    font-size: 0.75rem;
    text-align: center;
}

.upload-label .pi {
    display: inline-grid;
    place-items: center;
    flex: 0 0 30px;
    width: 30px;
    height: 30px;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.72);
    color: inherit;
    border: 1px solid currentColor;
    font-size: 1rem;
    line-height: 1;
    box-shadow: 0 2px 6px rgba(23, 32, 51, 0.08);
}

.upload-label > span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

@media (max-width: 768px) {
    .stat-card { height: 96px; padding: 14px 10px; }
    .stat-value { font-size: 1.6rem; }
    .stTabs [data-baseweb="tab"] { padding: 8px 10px; font-size: 0.82rem; }
    .upload-label { min-height: 38px; font-size: 0.82rem; }
    [data-testid="stFileUploader"] section { height: 104px; padding: 8px; }
    .app-topbar { gap: 6px; padding: 8px; overflow-x: auto; }
    .topbar-account { display: none; }
    .login-page { margin: 0.75rem auto; }
    .login-panel { flex-basis: 100%; padding: 32px 22px; }
    .login-art { display: none; }
}

/* Dark mode is activated by the marker rendered below the theme styles. */
.stApp:has(.theme-dark-marker) {
    --ink: #e5e7eb;
    --muted: #a7b0bf;
    --line: #334155;
    --surface: #172033;
    --surface-soft: #1e293b;
    --brand-soft: #134e4a;
    background: #0f172a;
    color-scheme: dark;
    transition: background-color 0.25s ease, color 0.25s ease;
}

.stApp,
.stat-card,
.status-card,
.result-box,
.login-panel,
.stTabs [data-baseweb="tab-list"],
[data-testid="stExpander"] {
    transition: background-color 0.25s ease, border-color 0.25s ease, color 0.25s ease;
}

.stApp:has(.theme-dark-marker) [data-testid="stSidebar"],
.stApp:has(.theme-dark-marker) .stat-card,
.stApp:has(.theme-dark-marker) .status-card,
.stApp:has(.theme-dark-marker) .result-box,
.stApp:has(.theme-dark-marker) [data-testid="metric-container"],
.stApp:has(.theme-dark-marker) .stTabs [data-baseweb="tab-list"] {
    background: #172033;
    border-color: #334155;
    color: #e5e7eb;
}

.stApp:has(.theme-dark-marker) .sidebar-brand,
.stApp:has(.theme-dark-marker) [data-testid="stFileUploader"] section {
    background: #1e293b;
    border-color: #3b6470;
}

.stApp:has(.theme-dark-marker) .stTextInput > div > div > input,
.stApp:has(.theme-dark-marker) textarea,
.stApp:has(.theme-dark-marker) [data-baseweb="select"] > div,
.stApp:has(.theme-dark-marker) [data-baseweb="input"] > div,
.stApp:has(.theme-dark-marker) .stButton > button,
.stApp:has(.theme-dark-marker) [data-testid="stFileUploader"] section button {
    background: #1e293b !important;
    border-color: #475569 !important;
    color: #e5e7eb !important;
}

.stApp:has(.theme-dark-marker) [data-testid="stWidgetLabel"],
.stApp:has(.theme-dark-marker) [data-testid="stMarkdownContainer"],
.stApp:has(.theme-dark-marker) [data-testid="stCaptionContainer"],
.stApp:has(.theme-dark-marker) .section-title,
.stApp:has(.theme-dark-marker) .login-title,
.stApp:has(.theme-dark-marker) .login-subtitle {
    color: #e5e7eb !important;
}

.stApp:has(.theme-dark-marker) [data-baseweb="popover"],
.stApp:has(.theme-dark-marker) [data-baseweb="menu"],
.stApp:has(.theme-dark-marker) [role="listbox"] {
    background: #172033 !important;
    border-color: #475569 !important;
    color: #e5e7eb !important;
}

.stApp:has(.theme-dark-marker) [role="option"]:hover,
.stApp:has(.theme-dark-marker) [data-baseweb="menu"] li:hover {
    background: #334155 !important;
}

.stApp:has(.theme-dark-marker) [data-testid="stDataFrame"],
.stApp:has(.theme-dark-marker) [data-testid="stTable"],
.stApp:has(.theme-dark-marker) [data-testid="stExpander"] {
    border-color: #334155 !important;
    background: #172033 !important;
}

.stApp:has(.theme-dark-marker) .login-panel,
.stApp:has(.theme-dark-marker) .login-art {
    background: #172033;
    border-color: #334155;
}

.stApp:has(.theme-dark-marker) .stTabs [aria-selected="true"] {
    background: #0f766e !important;
    color: white !important;
}

.stApp:has(.theme-dark-marker) .app-footer,
.stApp:has(.theme-dark-marker) .sidebar-divider,
.stApp:has(.theme-dark-marker) hr {
    border-color: #334155 !important;
}

.stApp:has(.theme-dark-marker) .st-key-opt_clear_all > button {
    background: rgba(190, 18, 60, 0.15) !important;
    border-color: rgba(190, 18, 60, 0.4) !important;
    color: #fda4af !important;
}

.stApp:has(.theme-dark-marker) .st-key-opt_clear_all > button:hover:not(:disabled) {
    background: rgba(190, 18, 60, 0.28) !important;
    border-color: #f43f5e !important;
    color: #ffe4e6 !important;
}

.stApp:has(.theme-dark-marker) .topbar-opt-hint {
    background: rgba(255, 255, 255, 0.03);
    border-color: var(--line);
    color: var(--muted);
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<span class="theme-dark-marker"></span>' if st.session_state.dark_mode else '<span class="theme-light-marker"></span>',
    unsafe_allow_html=True,
)

if not st.session_state.authenticated:
    with st.container(key="login_page"):
        login_cols = st.columns([1, 1.45])
        with login_cols[0]:
            st.markdown("<div class='login-panel'>", unsafe_allow_html=True)
            st.markdown("<div class='login-logo'>م</div><h1 class='login-title'>مرحبًا بك</h1><p class='login-subtitle'>سجّل الدخول إلى لوحة بيانات المندوبين</p>", unsafe_allow_html=True)
            with st.form("login_form"):
                username = st.text_input("اسم المستخدم", placeholder="أدخل اسم المستخدم")
                password = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
                submitted = st.form_submit_button("تسجيل الدخول", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        with login_cols[1]:
            st.markdown("<div class='login-art'><i class='pi pi-chart-bar'></i></div>", unsafe_allow_html=True)

    if submitted:
        account = st.session_state.managed_users.get(username.strip())
        if account and verify_password(password, account["password"]):
            st.session_state.authenticated = True
            st.session_state.current_user = username.strip()
            st.session_state.current_role = account["role"]
            session_token = create_session_token(username.strip(), account["role"])
            st.query_params["auth"] = session_token
            if cookie_manager:
                cookie_manager.set(
                    "auth",
                    session_token,
                    expires_at=datetime.now() + timedelta(seconds=SESSION_TTL_SECONDS),
                )
            st.rerun()
        st.error("بيانات الدخول غير صحيحة")
    st.stop()

if st.session_state.current_page == "user_management" and st.session_state.current_role == "admin":
    st.markdown("<div class='section-title'><i class='pi pi-users'></i><span>إدارة المستخدمين</span></div>", unsafe_allow_html=True)
    st.caption("إدارة حسابات الموظفين وصلاحياتهم")

    if st.button("العودة إلى الصفحة الرئيسية", key="back_home"):
        st.session_state.current_page = "home"
        st.session_state.show_user_management = False
        st.rerun()

    with st.container(border=True):
        user_rows = [
            {"اسم المستخدم": username, "الدور": account["label"]}
            for username, account in st.session_state.managed_users.items()
        ]
        st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)

        with st.form("standalone_add_employee_form", clear_on_submit=True):
            add_cols = st.columns([1.2, 1.2, 1])
            with add_cols[0]:
                new_username = st.text_input("اسم الموظف", placeholder="employee2")
            with add_cols[1]:
                new_password = st.text_input("كلمة المرور", type="password")
            with add_cols[2]:
                add_employee = st.form_submit_button("إضافة موظف", use_container_width=True)

        if add_employee:
            clean_username = new_username.strip()
            if not clean_username or not new_password:
                st.warning("أدخل اسم الموظف وكلمة المرور")
            elif clean_username in st.session_state.managed_users:
                st.error("اسم المستخدم موجود مسبقًا")
            else:
                st.session_state.managed_users[clean_username] = {
                    "password": hash_password(new_password),
                    "role": "employee",
                    "label": "موظف",
                }
                save_managed_user(clean_username, st.session_state.managed_users[clean_username])
                st.success("تمت إضافة الموظف")
                st.rerun()

        removable_users = [
            username for username, account in st.session_state.managed_users.items()
            if account["role"] == "employee"
        ]
        if removable_users:
            delete_user = st.selectbox("حذف موظف", removable_users, key="standalone_delete_user")
            if st.button("حذف المستخدم المحدد", key="standalone_delete_employee", type="secondary"):
                del st.session_state.managed_users[delete_user]
                delete_managed_user(delete_user)
                st.success("تم حذف الموظف")
                st.rerun()
    st.stop()

# ─── الثوابت ──────────────────────────────────────────────────────────────────
STATUS_CONFIG = {
    "قيد التوصيل": {"icon": "🚚", "prime_icon": "pi-truck", "color": "#2563eb", "soft_color": "#eff6ff", "badge": "badge-delivery", "emoji_badge": "🔵"},
    "المؤجل":       {"icon": "⏳", "prime_icon": "pi-clock", "color": "#b45309", "soft_color": "#fffbeb", "badge": "badge-deferred", "emoji_badge": "🟡"},
    "الراجع":       {"icon": "↩️", "prime_icon": "pi-replay", "color": "#be123c", "soft_color": "#fff1f2", "badge": "badge-returned",  "emoji_badge": "🔴"},
    "تم التسليم":   {"icon": "✅", "prime_icon": "pi-check-circle", "color": "#047857", "soft_color": "#ecfdf5", "badge": "badge-delivered", "emoji_badge": "🟢"},
}

POSSIBLE_DRIVER_COLS = ['drivername', 'اسم المندوب', 'المندوب', 'driver', 'الاسم']
POSSIBLE_CODE_COLS   = ['code', 'كود', 'رقم الطلب', 'id', 'رقم كود']
POSSIBLE_DATE_COLS   = ['created_at', 'التاريخ', 'تاريخ الطلب', 'date', 'تاريخ']

# ─── دوال مساعدة ──────────────────────────────────────────────────────────────
@st.cache_data
def detect_columns(df: pd.DataFrame):
    col_driver = col_code = col_date = None
    for col in df.columns:
        col_str = str(col).lower()
        if any(p in col_str for p in POSSIBLE_DRIVER_COLS):
            col_driver = col
        if any(p in col_str for p in POSSIBLE_CODE_COLS):
            col_code = col
        if any(p in col_str for p in POSSIBLE_DATE_COLS):
            col_date = col
    return col_driver, col_code, col_date


@st.cache_data
def filter_by_date(df, col_date, start_date, end_date):
    df = df.copy()
    df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
    start = pd.Timestamp(start_date)
    end   = pd.Timestamp(end_date).replace(hour=23, minute=59, second=59)
    return df[(df[col_date] >= start) & (df[col_date] <= end)]


@st.cache_data
def process_df(df, col_driver, col_code):
    """إرجاع dict: اسم المندوب → {codes, count}"""
    result = {}
    for driver_name, group in df.groupby(col_driver):
        codes = []
        if col_code:
            codes = [str(c) for c in group[col_code].tolist() if str(c).lower() != 'nan']
        result[str(driver_name)] = {"codes": codes, "count": len(group)}
    return result


def build_text_output(drivers_data: dict, title: str) -> str:
    lines = [f"★ {title} ★", "=" * 22]
    for name in sorted(drivers_data.keys()):
        d = drivers_data[name]
        lines.append(name)
        lines.extend(d["codes"])
        lines.append(str(d["count"]))
        lines.append("-" * 15)
    return "\n".join(lines)


def render_copy_button(text: str, key: str) -> None:
    """عرض زر ينسخ النص إلى حافظة المستخدم."""
    import json

    text_json = json.dumps(text, ensure_ascii=False)
    components.html(f"""
    <style>
        .pi-copy::before {{ content: "⧉"; }}
        .pi-check::before {{ content: "✓"; }}
    </style>
    <button id="copy-{key}" style="
        width: 100%; min-height: 42px; padding: 9px 18px;
        border: 1px solid #e4e8ef; border-radius: 8px;
        background: #ffffff; color: #172033; font-family: var(--font-sans);
        font-size: 14px; font-weight: 700; cursor: pointer;
        transition: all 0.2s ease;
    ">نسخ</button>
    <script>
        const button = document.getElementById("copy-{key}");
        const text = {text_json};
        button.addEventListener("mouseenter", () => {{
            button.style.borderColor = "#8dc5bf";
            button.style.color = "#115e59";
            button.style.boxShadow = "0 6px 18px rgba(15, 118, 110, 0.14)";
        }});
        button.addEventListener("mouseleave", () => {{
            button.style.borderColor = "#e4e8ef";
            button.style.color = "#172033";
            button.style.boxShadow = "none";
        }});
        button.addEventListener("click", async () => {{
            try {{
                await navigator.clipboard.writeText(text);
            }} catch (error) {{
                const area = document.createElement("textarea");
                area.value = text;
                document.body.appendChild(area);
                area.select();
                document.execCommand("copy");
                area.remove();
            }}
            button.textContent = "تم النسخ";
            setTimeout(() => button.textContent = "نسخ", 1800);
        }});
    </script>
    """, height=48)


def to_excel_bytes(dataframes: dict) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in dataframes.items():
            if df is not None and not df.empty:
                df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return output.getvalue()


def get_top_driver(all_data: dict) -> tuple:
    """أعلى مندوب من حيث عدد الطلبات الإجمالية"""
    combined = {}
    for status, d in all_data.items():
        if d:
            for name, info in d.items():
                combined[name] = combined.get(name, 0) + info["count"]
    if combined:
        top = max(combined, key=combined.get)
        return top, combined[top]
    return "---", 0


# ─── Session State ─────────────────────────────────────────────────────────────
for key in STATUS_CONFIG:
    if f"data_{key}" not in st.session_state:
        st.session_state[f"data_{key}"] = None   # processed dict
    if f"raw_{key}" not in st.session_state:
        st.session_state[f"raw_{key}"] = None    # raw DataFrame

# ─── الشريط العلوي ─────────────────────────────────────────────────────────────
with st.container(key="app_topbar"):
    topbar_cols = st.columns([0.7, 2.55, 1.25, 1.65, 0.58, 1.65])

    # ── الشعار ──────────────────────────────────────────────────────────────────
    with topbar_cols[0]:
        st.markdown("<div class='topbar-logo' title='نظام المندوبين'>م</div>", unsafe_allow_html=True)

    # ── البحث ───────────────────────────────────────────────────────────────────
    with topbar_cols[1]:
        search_query = st.text_input(
            "بحث", placeholder="🔍  ابحث عن اسم المندوب...",
            label_visibility="collapsed", key="topbar_search"
        )

    # ── حالة الشبكة (لوحة PrimeNG مطابقة مع نافذة تفاصيل تفاعلية) ──────────────
    with topbar_cols[2]:
        components.html("""
<link rel="stylesheet" href="https://unpkg.com/primeicons@7.0.0/primeicons.css">
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@600;700;900&display=swap');
* { margin:0; padding:0; box-sizing:border-box; font-family:'Cairo',sans-serif; direction:rtl; }
body { background:transparent; overflow:hidden; }

#pill {
    display: inline-flex;
    cursor: pointer;
    user-select: none;
    align-items: center;
    justify-content: center;
    vertical-align: bottom;
    text-align: center;
    overflow: hidden;
    position: relative;
    gap: 7px;
    height: 38px;
    padding: 0.55rem 1.1rem;
    border-radius: 2rem;
    font-size: 0.8rem;
    font-weight: 700;
    white-space: nowrap;
    transition: background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s;
    background-color: #f7f7fe;
    border: 1px solid #dadafc;
    color: #532BFD;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
#pill:hover {
    border-color: #532BFD;
    background-color: #ededfd;
    box-shadow: 0 0 0 0.18rem rgba(83, 43, 253, 0.16);
}
#pill.good {
    border-color: #caf1d8; background-color: #f4fcf7; color: #188a42;
    box-shadow: 0 1px 3px rgba(24, 138, 66, 0.08);
}
#pill.good:hover {
    border-color: #22c55e;
    box-shadow: 0 0 0 0.18rem rgba(34, 197, 94, 0.2);
}
#pill.medium {
    border-color: #faedc4; background-color: #fefbf3; color: #a47d06;
    box-shadow: 0 1px 3px rgba(164, 125, 6, 0.08);
}
#pill.medium:hover {
    border-color: #eab308;
    box-shadow: 0 0 0 0.18rem rgba(234, 179, 8, 0.2);
}
#pill.slow {
    border-color: #ffd0ce; background-color: #fff5f5; color: #b32b23;
    box-shadow: 0 1px 3px rgba(179, 43, 35, 0.08);
}
#pill.slow:hover {
    border-color: #ff3d32;
    box-shadow: 0 0 0 0.18rem rgba(255, 61, 50, 0.2);
}

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
.measuring { animation: pulse 1.2s ease infinite; }
</style>

<div id="pill" class="measuring" title="انقر لعرض معلومات الشبكة التفصيلية">
    <i class="pi pi-wifi"></i>
    <span id="pill-lbl">قياس الشبكة...</span>
</div>

<script>
(function(){
    var pill = document.getElementById('pill');
    var pillLbl = document.getElementById('pill-lbl');
    var parentDoc = window.parent.document;
    var overlayId = 'prime-network-overlay-panel';
    var isDark = parentDoc.querySelector('.theme-dark-marker') !== null;

    // التأكد من تحميل أيقونات PrimeIcons في المستند الأصلي
    if (!parentDoc.getElementById('primeicons-cdn')) {
        var piLink = parentDoc.createElement('link');
        piLink.id = 'primeicons-cdn';
        piLink.rel = 'stylesheet';
        piLink.href = 'https://unpkg.com/primeicons@7.0.0/primeicons.css';
        parentDoc.head.appendChild(piLink);
    }

    // إزالة أي لوحة سابقة إن وجدت لتحديث البنية
    var existingOverlay = parentDoc.getElementById(overlayId);
    if (existingOverlay) {
        existingOverlay.remove();
    }

    // إنشاء لوحة PrimeNG OverlayPanel في المستند الأب (document.body)
    var overlay = parentDoc.createElement('div');
    overlay.id = overlayId;
    overlay.className = 'ng-trigger ng-trigger-animation p-3 p-overlaypanel p-component';
    overlay.style.cssText = [
        'position: fixed',
        'z-index: 999999',
        'display: none',
        'width: 20rem',
        'max-width: calc(100vw - 20px)',
        'padding: 1.15rem !important',
        'border-radius: 8px',
        'box-shadow: 0 6px 28px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.08)',
        'direction: rtl',
        'font-family: Cairo, -apple-system, BlinkMacSystemFont, sans-serif',
        'box-sizing: border-box',
        'transition: opacity 0.2s ease, transform 0.2s ease',
        'transform: translateY(0px)',
        'opacity: 1',
        isDark ? 'background: #172033; border: 1px solid #334155; color: #e5e7eb;' : 'background: #ffffff; border: 1px solid #dfe7ef; color: #495057;'
    ].join(';');

    overlay.innerHTML = `
        <div class="p-overlaypanel-content">
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid ${isDark ? '#334155' : '#dfe7ef'};">
                <h6 style="margin:0; color:#532BFD; font-size:0.95rem; font-weight:700; display:flex; align-items:center; gap:6px;">
                    <i class="pi pi-globe"></i> معلومات الشبكة
                </h6>
                <span id="pno-badge" style="padding:2px 8px; border-radius:6px; font-size:0.72rem; font-weight:700; background:#fef3c7; color:#b45309;">
                    متوسطة
                </span>
            </div>
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
                <i id="pno-wifi-icon" class="pi pi-wifi" style="font-size:1.4rem; color:#f59e0b;"></i>
                <div style="display:flex; flex-direction:column; line-height:1.2;">
                    <span style="font-size:0.83rem; font-weight:600; color:${isDark ? '#f1f5f9' : '#172033'};">حالة الاتصال</span>
                    <span id="pno-status-txt" style="font-size:0.74rem; color:${isDark ? '#94a3b8' : '#64748b'};"> متصل </span>
                </div>
            </div>
            <div style="display:flex; flex-direction:column; gap:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0;">
                    <span style="font-size:0.8rem; color:${isDark ? '#cbd5e1' : '#495057'};">زمن الاستجابة:</span>
                    <span id="pno-latency" style="font-size:0.84rem; font-weight:700; color:${isDark ? '#f8fafc' : '#172033'};">-- ms</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0;">
                    <span style="font-size:0.8rem; color:${isDark ? '#cbd5e1' : '#495057'};">نوع الاتصال:</span>
                    <span id="pno-conn-type" style="font-size:0.84rem; font-weight:600; color:${isDark ? '#f8fafc' : '#172033'};">غير محدد</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0;">
                    <span style="font-size:0.8rem; color:${isDark ? '#cbd5e1' : '#495057'};">نوع الشبكة:</span>
                    <span id="pno-net-type" style="font-size:0.84rem; font-weight:600; color:${isDark ? '#f8fafc' : '#172033'};">4G</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0;">
                    <span style="font-size:0.8rem; color:${isDark ? '#cbd5e1' : '#495057'};">سرعة التحميل:</span>
                    <span id="pno-downlink" style="font-size:0.84rem; font-weight:600; color:${isDark ? '#f8fafc' : '#172033'};">-- Mbps</span>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 0;">
                    <span style="font-size:0.8rem; color:${isDark ? '#cbd5e1' : '#495057'};">زمن الاستجابة RTT:</span>
                    <span id="pno-rtt" style="font-size:0.84rem; font-weight:600; color:${isDark ? '#f8fafc' : '#172033'};">-- ms</span>
                </div>
            </div>
            <div style="margin-top:10px; pt-2; border-top:1px solid ${isDark ? '#334155' : '#dfe7ef'}; padding-top:6px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:0.72rem; color:${isDark ? '#94a3b8' : '#64748b'};">آخر فحص:</span>
                    <span id="pno-last-check" style="font-size:0.72rem; color:${isDark ? '#94a3b8' : '#64748b'};">--</span>
                </div>
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
                <button id="pno-refresh-btn" type="button" style="display:inline-flex; align-items:center; gap:6px; padding:0.45rem 1.15rem; border:1px solid #532BFD; background:transparent; color:#532BFD; border-radius:2rem; font-size:0.8rem; font-weight:700; cursor:pointer; font-family:Cairo,sans-serif; transition:background-color 0.2s, color 0.2s, border-color 0.2s, box-shadow 0.2s;">
                    <span id="pno-refresh-icon" class="pi pi-refresh" style="font-size:0.78rem;"></span>
                    <span>تحديث</span>
                </button>
            </div>
        </div>
    `;

    parentDoc.body.appendChild(overlay);

    function formatTime(d) {
        var day = d.getDate();
        var month = d.getMonth() + 1;
        var year = ('' + d.getFullYear()).slice(-2);
        var hours = d.getHours();
        var minutes = d.getMinutes();
        var ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12;
        hours = hours ? hours : 12;
        minutes = minutes < 10 ? '0' + minutes : minutes;
        return month + '/' + day + '/' + year + ', ' + hours + ':' + minutes + ' ' + ampm;
    }

    function pingTarget(url) {
        return new Promise(function(resolve, reject) {
            var t0 = performance.now();
            var timer = setTimeout(function() {
                reject(new Error('timeout'));
            }, 4000);

            fetch(url, { method: 'HEAD', mode: 'no-cors', cache: 'no-store' })
                .then(function() {
                    clearTimeout(timer);
                    var duration = Math.round(performance.now() - t0);
                    resolve(duration);
                })
                .catch(function(err) {
                    clearTimeout(timer);
                    reject(err);
                });
        });
    }

    function getRealPing() {
        var cacheBust = '?_t=' + Date.now() + '_' + Math.random().toString(36).substring(2, 6);
        // اختبار النقطة السحابية الحقيقية الأقرب (Google 204 Edge)
        return pingTarget('https://www.gstatic.com/generate_204' + cacheBust)
            .catch(function() {
                // بديل سحابي حقيقي عالمي (Cloudflare Edge)
                return pingTarget('https://cloudflare.com/cdn-cgi/trace' + cacheBust);
            })
            .catch(function() {
                // بديل قياس RTT الحقيقي الخاص بالمتصفح
                var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
                if (conn && conn.rtt && conn.rtt > 0) {
                    return Promise.resolve(conn.rtt);
                }
                // في حالة انقطاع الاتصال الخارجي بالكامل
                return pingTarget(location.origin + '/?_nc=' + Date.now());
            });
    }

    function checkNetwork() {
        var conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        var refreshIcon = parentDoc.getElementById('pno-refresh-icon');
        if (refreshIcon) refreshIcon.classList.add('pi-spin');

        getRealPing()
            .then(function(ms) {
                var cls, badgeBg, badgeCol, iconCol, lbl;

                if (ms < 100) {
                    cls = 'good';
                    lbl = 'ممتازة';
                    badgeBg = '#dcfce7'; badgeCol = '#15803d'; iconCol = '#10b981';
                } else if (ms < 280) {
                    cls = 'medium';
                    lbl = 'متوسطة';
                    badgeBg = '#fef3c7'; badgeCol = '#b45309'; iconCol = '#f59e0b';
                } else {
                    cls = 'slow';
                    lbl = 'بطيئة';
                    badgeBg = '#fee2e2'; badgeCol = '#b91c1c'; iconCol = '#ef4444';
                }

                pill.className = cls;
                pillLbl.textContent = lbl + ' (' + ms + ' ms)';

                // تحديث قيم اللوحة التفصيلية
                var badgeEl = parentDoc.getElementById('pno-badge');
                if (badgeEl) {
                    badgeEl.textContent = lbl;
                    badgeEl.style.background = badgeBg;
                    badgeEl.style.color = badgeCol;
                }

                var wifiIcon = parentDoc.getElementById('pno-wifi-icon');
                if (wifiIcon) wifiIcon.style.color = iconCol;

                var latencyEl = parentDoc.getElementById('pno-latency');
                if (latencyEl) latencyEl.textContent = ms + ' ms';

                var connTypeEl = parentDoc.getElementById('pno-conn-type');
                if (connTypeEl) {
                    var typeName = 'غير محدد';
                    if (conn && conn.type) {
                        var map = {'wifi':'WiFi','ethernet':'إيثرنت','cellular':'خلوي 4G/5G','none':'غير متصل'};
                        typeName = map[conn.type] || conn.type;
                    } else {
                        typeName = 'WiFi / اتصال محلي';
                    }
                    connTypeEl.textContent = typeName;
                }

                var netTypeEl = parentDoc.getElementById('pno-net-type');
                if (netTypeEl) {
                    netTypeEl.textContent = (conn && conn.effectiveType) ? conn.effectiveType.toUpperCase() : (ms < 100 ? '4G / 5G' : (ms < 280 ? '3G' : '2G'));
                }

                var dlEl = parentDoc.getElementById('pno-downlink');
                if (dlEl) {
                    dlEl.textContent = (conn && conn.downlink) ? conn.downlink + ' Mbps' : (ms < 100 ? '15+ Mbps' : (ms < 280 ? '2.5 Mbps' : '0.5 Mbps'));
                }

                var rttEl = parentDoc.getElementById('pno-rtt');
                if (rttEl) {
                    rttEl.textContent = (conn && conn.rtt) ? conn.rtt + ' ms' : (ms * 1.5).toFixed(0) + ' ms';
                }

                var statusTxt = parentDoc.getElementById('pno-status-txt');
                if (statusTxt) statusTxt.textContent = 'متصل';

                var lastCheckEl = parentDoc.getElementById('pno-last-check');
                if (lastCheckEl) lastCheckEl.textContent = formatTime(new Date());

                if (refreshIcon) refreshIcon.classList.remove('pi-spin');
            })
            .catch(function(){
                pill.className = 'slow';
                pillLbl.textContent = 'غير متصل';

                var badgeEl = parentDoc.getElementById('pno-badge');
                if (badgeEl) {
                    badgeEl.textContent = 'غير متصل';
                    badgeEl.style.background = '#fee2e2';
                    badgeEl.style.color = '#b91c1c';
                }
                var wifiIcon = parentDoc.getElementById('pno-wifi-icon');
                if (wifiIcon) wifiIcon.style.color = '#ef4444';

                var statusTxt = parentDoc.getElementById('pno-status-txt');
                if (statusTxt) statusTxt.textContent = 'غير متصل';

                var lastCheckEl = parentDoc.getElementById('pno-last-check');
                if (lastCheckEl) lastCheckEl.textContent = formatTime(new Date());

                if (refreshIcon) refreshIcon.classList.remove('pi-spin');
            });
    }

    // زر التحديث في اللوحة
    var refreshBtn = parentDoc.getElementById('pno-refresh-btn');
    if (refreshBtn) {
        refreshBtn.onmouseenter = function() {
            this.style.backgroundColor = '#532BFD';
            this.style.color = '#ffffff';
            this.style.boxShadow = '0 0 0 0.18rem rgba(83, 43, 253, 0.25)';
        };
        refreshBtn.onmouseleave = function() {
            this.style.backgroundColor = 'transparent';
            this.style.color = '#532BFD';
            this.style.boxShadow = 'none';
        };
        refreshBtn.onclick = function(e) {
            e.stopPropagation();
            checkNetwork();
        };
    }

    // فتح / إغلاق اللوحة عند النقر على الشارة
    pill.onclick = function(e) {
        e.stopPropagation();
        if (overlay.style.display === 'block') {
            overlay.style.display = 'none';
        } else {
            var frame = window.frameElement;
            if (frame) {
                var rect = frame.getBoundingClientRect();
                overlay.style.top = (rect.bottom + 6) + 'px';
                var panelWidth = 320;
                var leftPos = rect.right - panelWidth;
                if (leftPos < 12) leftPos = 12;
                overlay.style.left = leftPos + 'px';
            }
            overlay.style.display = 'block';
        }
    };

    // إغلاق اللوحة عند النقر في أي مكان آخر
    parentDoc.addEventListener('click', function(e) {
        if (overlay && overlay.style.display === 'block') {
            if (!overlay.contains(e.target)) {
                overlay.style.display = 'none';
            }
        }
    });

    // مزامنة أيقونات PrimeIcons في عناصر الشريط العلوي
    function syncTopBarIcons() {
        try {
            if (!parentDoc) return;
            
            // التأكد من تحميل مكتبة خطوط PrimeIcons في نافذة الأصل
            if (parentDoc.head && !parentDoc.querySelector('link[href*="primeicons"]')) {
                var piLink = parentDoc.createElement('link');
                piLink.rel = 'stylesheet';
                piLink.href = 'https://unpkg.com/primeicons@7.0.0/primeicons.css';
                parentDoc.head.appendChild(piLink);
            }

            // زر تبديل الثيم: مطابقة <i class="pi pi-sun"></i> أو <i class="pi pi-moon"></i>
            var themeBtn = parentDoc.querySelector('.st-key-theme_toggle button');
            if (themeBtn) {
                var isDark = parentDoc.querySelector('.theme-dark-marker') !== null;
                var targetClass = isDark ? 'pi pi-moon' : 'pi pi-sun';
                var targetColor = isDark ? '#fcd34d' : '#f59e0b';
                var iconElem = themeBtn.querySelector('i.pi');
                if (!iconElem) {
                    themeBtn.innerHTML = '<i class="' + targetClass + '" style="font-size: 1.15rem; color: ' + targetColor + ';"></i>';
                } else {
                    if (iconElem.className !== targetClass) iconElem.className = targetClass;
                    if (iconElem.style.color !== targetColor) iconElem.style.color = targetColor;
                }
            }

            // زر إدارة المستخدمين: مطابقة <i class="pi pi-cog"></i>
            var userBtn = parentDoc.querySelector('.st-key-user_management_toggle button');
            if (userBtn) {
                var userIconElem = userBtn.querySelector('i.pi');
                if (!userIconElem) {
                    userBtn.innerHTML = '<i class="pi pi-cog" style="font-size: 1.05rem; color: #532BFD;"></i>';
                }
            }
        } catch (e) {}
    }
    syncTopBarIcons();
    setInterval(syncTopBarIcons, 300);

    // القياس التلقائي الأولي
    checkNetwork();
    // إعادة القياس دوريًا لتحديث حالة الشبكة دون تدخل المستخدم
    setInterval(checkNetwork, 10000);
})();
</script>
""", height=46)

    # ── بطاقة المستخدم ──────────────────────────────────────────────────────────
    with topbar_cols[3]:
        role_label = "مدير النظام" if st.session_state.current_role == "admin" else "موظف"
        role_cls   = "role-admin"    if st.session_state.current_role == "admin" else "role-employee"
        user_name  = st.session_state.current_user or "المستخدم"
        avatar     = user_name[:1].upper()
        st.markdown(f"""
        <div class='topbar-account'>
            <span class='topbar-avatar'>{avatar}</span>
            <span class='topbar-user-text'>
                <span class='topbar-user-name'>{user_name}</span>
                <span class='topbar-role-badge {role_cls}'>{role_label}</span>
            </span>
        </div>""", unsafe_allow_html=True)

    # ── تبديل الثيم ─────────────────────────────────────────────────────────────
    with topbar_cols[4]:
        with st.container(key="topbar_theme_slot"):
            theme_tip  = "الوضع النهاري" if st.session_state.dark_mode else "الوضع الليلي"
            if st.button("", key="theme_toggle", help=theme_tip, type="secondary"):
                st.session_state.dark_mode = not st.session_state.dark_mode
                st.rerun()

    # ── إدارة المستخدمين (للمدير فقط) ──────────────────────────────────────────
    with topbar_cols[5]:
        action_cols = st.columns([0.58, 0.95], gap="small")
        with action_cols[0]:
            with st.container(key="topbar_admin_slot"):
                if st.session_state.current_role == "admin":
                    if st.button("", key="user_management_toggle",
                                 help="إدارة المستخدمين", type="secondary",
                                 use_container_width=True):
                        st.session_state.current_page = "user_management"
                        st.session_state.show_user_management = False
                        st.rerun()

        # ── تسجيل الخروج ────────────────────────────────────────────────────────
        with action_cols[1]:
            with st.container(key="topbar_logout_slot"):
                if st.button("خروج", key="topbar_logout",
                             help="تسجيل الخروج", type="secondary",
                             use_container_width=True):
                    st.session_state.authenticated = False
                    st.session_state.current_user = None
                    st.session_state.current_role = None
                    st.session_state.show_user_management = False
                    st.session_state.current_page = "home"
                    st.query_params.pop("auth", None)
                    if cookie_manager:
                        cookie_manager.delete("auth")
                    st.rerun()

    # ── خيارات المعالجة المرفوعة للشريط العلوي ────────────────────────────────────
    st.markdown("<div class='topbar-subdivider'></div>", unsafe_allow_html=True)

    if st.session_state.get("opt_date_filter", False):
        opt_cols = st.columns([1.3, 1.1, 1.1, 1.4, 1.1])
        with opt_cols[0]:
            use_date_filter = st.toggle("فلترة التاريخ", key="opt_date_filter")
        with opt_cols[1]:
            start_date = st.date_input("من", value=date.today() - timedelta(days=30), key="opt_date_from")
        with opt_cols[2]:
            end_date = st.date_input("إلى", value=date.today(), key="opt_date_to")
        with opt_cols[3]:
            merge_mode = st.toggle("دمج كل الحالات معاً", key="opt_merge_mode")
        with opt_cols[4]:
            if st.button("مسح البيانات", key="opt_clear_all",
                         help="مسح جميع الجداول والبيانات المرفوعة (للمدير فقط)", type="secondary",
                         use_container_width=True, disabled=st.session_state.current_role != "admin"):
                for k in STATUS_CONFIG:
                    st.session_state[f"data_{k}"] = None
                    st.session_state[f"raw_{k}"] = None
                st.rerun()
    else:
        opt_cols = st.columns([1.3, 1.6, 2.9, 1.2])
        with opt_cols[0]:
            use_date_filter = st.toggle("فلترة التاريخ", value=False, key="opt_date_filter")
            start_date = end_date = None
        with opt_cols[1]:
            merge_mode = st.toggle("دمج كل الحالات معاً", value=False, key="opt_merge_mode")
        with opt_cols[2]:
            st.markdown("<div class='topbar-opt-hint'><i class='pi pi-info-circle'></i> <span>خيارات المعالجة: فلترة التواريخ ودمج الحالات المرفوعة تلقائياً</span></div>", unsafe_allow_html=True)
        with opt_cols[3]:
            if st.button("مسح البيانات", key="opt_clear_all",
                         help="مسح جميع الجداول والبيانات المرفوعة (للمدير فقط)", type="secondary",
                         use_container_width=True, disabled=st.session_state.current_role != "admin"):
                for k in STATUS_CONFIG:
                    st.session_state[f"data_{k}"] = None
                    st.session_state[f"raw_{k}"] = None
                st.rerun()



# ─── رفع الملفات ──────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'><i class='pi pi-upload'></i><span>رفع الملفات</span></div>", unsafe_allow_html=True)
upload_cols = st.columns(4)
status_labels = list(STATUS_CONFIG.keys())

for i, status in enumerate(status_labels):
    cfg = STATUS_CONFIG[status]
    with upload_cols[i]:
        st.markdown(f"<div class='upload-label' style='color:{cfg['color']};--status-soft:{cfg['soft_color']}'><i class='pi {cfg['prime_icon']}' aria-hidden='true'></i><span>{status}</span></div>", unsafe_allow_html=True)
        uploaded = st.file_uploader("اختر ملفًا", type=["xlsx", "xls", "csv"], key=f"up_{status}", label_visibility="collapsed")

        if uploaded:
            try:
                if uploaded.size > MAX_UPLOAD_SIZE_BYTES:
                    st.error("حجم الملف يتجاوز الحد المسموح (20 ميجابايت).")
                    continue
                if uploaded.name.lower().endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                if df.empty:
                    st.error("الملف فارغ!")
                else:
                    col_driver, col_code, col_date = detect_columns(df)
                    if not col_driver:
                        st.error("لم يُعثر على عمود المندوب!")
                    else:
                        if use_date_filter and col_date and start_date and end_date:
                            df = filter_by_date(df, col_date, start_date, end_date)
                        if df.empty:
                            st.warning("لا بيانات في النطاق الزمني!")
                        else:
                            st.session_state[f"raw_{status}"]  = df
                            st.session_state[f"data_{status}"] = process_df(df, col_driver, col_code)
                            st.success(f"تم تحميل {len(df)} سطر")
            except Exception as e:
                st.error(f"خطأ: {e}")

st.divider()

# ─── جمع البيانات المتاحة ─────────────────────────────────────────────────────
all_processed = {s: st.session_state[f"data_{s}"] for s in STATUS_CONFIG}
has_data = any(v is not None for v in all_processed.values())

# ─── لوحة الإحصائيات ──────────────────────────────────────────────────────────
st.markdown("<div class='section-title'><i class='pi pi-chart-bar'></i><span>لوحة الإحصائيات</span></div>", unsafe_allow_html=True)
stat_cols = st.columns(4)

total_drivers = set()
total_codes   = 0
status_counts = {}

for status, data in all_processed.items():
    if data:
        for name, info in data.items():
            total_drivers.add(name)
            total_codes += info["count"]
        status_counts[status] = sum(d["count"] for d in data.values())
    else:
        status_counts[status] = 0

top_driver_name, top_driver_count = get_top_driver(all_processed)

with stat_cols[0]:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label"><i class="pi pi-users"></i> إجمالي المندوبين</div>
        <div class="stat-value stat-blue">{len(total_drivers)}</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[1]:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label"><i class="pi pi-box"></i> إجمالي الطلبات</div>
        <div class="stat-value stat-green">{total_codes}</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[2]:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label"><i class="pi pi-trophy"></i> الأعلى طلباً</div>
        <div class="stat-value stat-orange" style="font-size:1.2rem">{top_driver_name}</div>
        <div class="stat-label">{top_driver_count if top_driver_count else ''} طلب</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[3]:
    active = sum(1 for v in all_processed.values() if v is not None)
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label"><i class="pi pi-list"></i> الحالات المُحمّلة</div>
        <div class="stat-value stat-purple">{active} / 4</div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ─── النتائج والتحليلات ────────────────────────────────────────────────────────
if has_data:
    tab_results, tab_chart, tab_table, tab_export = st.tabs([
        "النتائج النصية",
        "الرسم البياني",
        "جدول المندوبين",
        "تصدير البيانات",
    ])

    # ── Tab 1: النتائج النصية ────────────────────────────────────────────────
    with tab_results:
        if merge_mode:
            # دمج شامل
            combined: dict = {}
            for status, data in all_processed.items():
                if data:
                    for name, info in data.items():
                        if name not in combined:
                            combined[name] = {"codes": [], "count": 0}
                        combined[name]["codes"].extend(info["codes"])
                        combined[name]["count"] += info["count"]

            # تطبيق البحث
            if search_query:
                combined = {k: v for k, v in combined.items() if search_query.lower() in k.lower()}

            text_output = build_text_output(combined, "نتائج المندوبين (دمج كامل)")

            col_txt, col_btn = st.columns([5, 1])
            with col_btn:
                st.download_button("تنزيل", text_output, "results.txt", "text/plain", use_container_width=True)
                render_copy_button(text_output, "combined")
            with col_txt:
                st.markdown(f'<div class="result-box">{text_output.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

        else:
            # نتائج مقسّمة
            for status in status_labels:
                data = all_processed[status]
                if data is None:
                    continue
                cfg = STATUS_CONFIG[status]

                # تطبيق البحث
                filtered = data
                if search_query:
                    filtered = {k: v for k, v in data.items() if search_query.lower() in k.lower()}

                with st.expander(f"{status} — {sum(d['count'] for d in filtered.values())} طلب | {len(filtered)} مندوب", expanded=True):
                    text_output = build_text_output(filtered, status)
                    col_txt, col_btn = st.columns([5, 1])
                    with col_btn:
                        st.download_button("تنزيل", text_output, f"{status}.txt", "text/plain",
                                           key=f"dl_{status}", use_container_width=True)
                        render_copy_button(text_output, f"status-{status}")
                    with col_txt:
                        st.markdown(f'<div class="result-box" style="border-color:{cfg["color"]}55">{text_output.replace(chr(10), "<br>")}</div>',
                                    unsafe_allow_html=True)

    # ── Tab 2: الرسم البياني ─────────────────────────────────────────────────
    with tab_chart:
        chart_type = st.radio("نوع الرسم", ["أعمدة", "دائري", "مقارنة الحالات"], horizontal=True)

        if chart_type == "أعمدة":
            # أعلى 15 مندوب
            combined_counts: dict = {}
            for data in all_processed.values():
                if data:
                    for name, info in data.items():
                        combined_counts[name] = combined_counts.get(name, 0) + info["count"]

            if combined_counts:
                df_chart = pd.DataFrame(list(combined_counts.items()), columns=["المندوب", "الطلبات"])
                df_chart = df_chart.sort_values("الطلبات", ascending=False).head(15)

                fig = px.bar(
                    df_chart, x="المندوب", y="الطلبات",
                    title="أعلى 15 مندوبًا من حيث عدد الطلبات",
                    color="الطلبات",
                    color_continuous_scale=["#99f6e4", "#0f766e", "#115e59"],
                    text="الطلبات",
                )
                fig.update_traces(textposition='outside', textfont_size=12)
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='#f8fafc',
                    font=dict(family="Cairo", color="#172033"),
                    title_font_size=16,
                    xaxis=dict(tickangle=-30, gridcolor='#e4e8ef'),
                    yaxis=dict(gridcolor='#e4e8ef'),
                    coloraxis_showscale=False,
                )
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "دائري":
            labels = [s for s, v in status_counts.items() if v > 0]
            values = [status_counts[s] for s in labels]
            colors = [STATUS_CONFIG[s]["color"] for s in labels]

            if values:
                fig = go.Figure(go.Pie(
                    labels=labels, values=values,
                    hole=0.5,
                    marker_colors=colors,
                    textinfo='label+percent',
                    textfont_size=13,
                ))
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(family="Cairo", color="#172033"),
                    title="توزيع الطلبات حسب الحالة",
                    title_font_size=16,
                    showlegend=True,
                    legend=dict(font=dict(color="#172033")),
                )
                st.plotly_chart(fig, use_container_width=True)

        else:  # مقارنة الحالات
            rows = []
            for status, data in all_processed.items():
                if data:
                    for name, info in data.items():
                        rows.append({"المندوب": name, "الحالة": status, "الطلبات": info["count"]})
            if rows:
                df_comp = pd.DataFrame(rows)
                fig = px.bar(
                    df_comp, x="المندوب", y="الطلبات", color="الحالة",
                    barmode="group",
                    title="مقارنة المندوبين حسب الحالة",
                    color_discrete_map={s: STATUS_CONFIG[s]["color"] for s in STATUS_CONFIG},
                )
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='#f8fafc',
                    font=dict(family="Cairo", color="#172033"),
                    title_font_size=16,
                    xaxis=dict(tickangle=-30, gridcolor='#e4e8ef'),
                    yaxis=dict(gridcolor='#e4e8ef'),
                    legend=dict(font=dict(color="#172033")),
                )
                st.plotly_chart(fig, use_container_width=True)

    # ── Tab 3: جدول المندوبين ────────────────────────────────────────────────
    with tab_table:
        rows = []
        for status, data in all_processed.items():
            if data:
                cfg = STATUS_CONFIG[status]
                for name, info in data.items():
                    rows.append({
                        "المندوب":  name,
                        "الحالة":   status,
                        "عدد الطلبات": info["count"],
                        "الأكواد":  ", ".join(info["codes"][:5]) + ("..." if len(info["codes"]) > 5 else ""),
                    })

        if rows:
            df_table = pd.DataFrame(rows)

            # بحث في الجدول
            if search_query:
                df_table = df_table[df_table["المندوب"].str.contains(search_query, case=False, na=False)]

            df_table = df_table.sort_values("عدد الطلبات", ascending=False).reset_index(drop=True)
            st.dataframe(df_table, use_container_width=True, height=400)

            st.metric("إجمالي الصفوف", len(df_table))

    # ── Tab 4: تصدير البيانات ────────────────────────────────────────────────
    with tab_export:
        st.markdown("<div class='section-title'><i class='pi pi-file-export'></i><span>خيارات التصدير</span></div>", unsafe_allow_html=True)
        exp_cols = st.columns(3)

        with exp_cols[0]:
            st.markdown("<div class='upload-label'><i class='pi pi-file-edit'></i><span>تصدير النص الكامل</span></div>", unsafe_allow_html=True)
            full_text = ""
            if merge_mode:
                combined_all: dict = {}
                for data in all_processed.values():
                    if data:
                        for name, info in data.items():
                            if name not in combined_all:
                                combined_all[name] = {"codes": [], "count": 0}
                            combined_all[name]["codes"].extend(info["codes"])
                            combined_all[name]["count"] += info["count"]
                full_text = build_text_output(combined_all, "نتائج المندوبين")
            else:
                for status, data in all_processed.items():
                    if data:
                        full_text += build_text_output(data, status) + "\n\n"

            st.download_button(
                "تنزيل TXT",
                full_text,
                "drivers_results.txt",
                "text/plain",
                use_container_width=True,
                type="primary",
            )

        with exp_cols[1]:
            st.markdown("<div class='upload-label'><i class='pi pi-file-excel'></i><span>تصدير إكسل (كل الحالات)</span></div>", unsafe_allow_html=True)
            raw_frames = {s: st.session_state[f"raw_{s}"] for s in STATUS_CONFIG}
            excel_bytes = to_excel_bytes(raw_frames)
            st.download_button(
                "تنزيل إكسل",
                excel_bytes,
                "drivers_data.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )

        with exp_cols[2]:
            st.markdown("<div class='upload-label'><i class='pi pi-table'></i><span>تصدير جدول المندوبين</span></div>", unsafe_allow_html=True)
            rows_exp = []
            for status, data in all_processed.items():
                if data:
                    for name, info in data.items():
                        rows_exp.append({"المندوب": name, "الحالة": status, "عدد الطلبات": info["count"]})
            if rows_exp:
                df_exp = pd.DataFrame(rows_exp)
                csv_bytes = df_exp.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "تنزيل CSV",
                    csv_bytes,
                    "drivers_summary.csv",
                    "text/csv",
                    use_container_width=True,
                    type="primary",
                )

else:
    # لا توجد بيانات بعد
    st.markdown("""
    <div style="text-align:center; padding: 60px 20px; color: #667085;">
        <div style="font-size:4rem; color:#0f766e"><i class="pi pi-inbox"></i></div>
        <div style="font-size:1.2rem; margin-top:12px">ارفع ملفات إكسل للبدء</div>
        <div style="font-size:0.9rem; margin-top:6px">يمكنك رفع ملف واحد أو أكثر من الحالات الأربع</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div class='app-footer'>نظام بيانات المندوبين Pro v2.0</div>", unsafe_allow_html=True)
