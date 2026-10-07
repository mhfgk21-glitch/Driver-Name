# pyrefly: ignore [missing-import]
import streamlit as st
# pyrefly: ignore [missing-import]
import streamlit.components.v1 as components
import pandas as pd
# pyrefly: ignore [missing-import]
import plotly.express as px
# pyrefly: ignore [missing-import]
import plotly.graph_objects as go
import os
import re
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from html import escape as html_escape
from io import BytesIO
from datetime import date, datetime, timedelta
from auth_cookie import create_auth_cookie, verify_auth_cookie

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ─── إعدادات الصفحة ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="نظام بيانات المندوبين",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

AUTH_COOKIE_NAME = "__Host-driver_auth"

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

if "accounting_assignments" not in st.session_state:
    st.session_state.accounting_assignments = {}
if "accounting_rates" not in st.session_state:
    st.session_state.accounting_rates = {"مركز": 2000, "قضاء": 3000}
if "accounting_rows" not in st.session_state:
    st.session_state.accounting_rows = None

USERS_DB_PATH = os.getenv("APP_USERS_DB", "users.db")
# OWASP's current PBKDF2-HMAC-SHA256 baseline is 600,000 iterations.
PASSWORD_HASH_ITERATIONS = 600_000
LEGACY_PASSWORD_HASH_MIN_ITERATIONS = 310_000
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256
LOGIN_MAX_FAILURES = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60


def configured_idle_seconds() -> int:
    try:
        configured_value = int(os.getenv("APP_SESSION_IDLE_SECONDS", "1800"))
    except ValueError:
        configured_value = 1800
    return min(max(configured_value, 5 * 60), 8 * 60 * 60)


LOGIN_SESSION_IDLE_SECONDS = configured_idle_seconds()
USERNAME_MAX_LENGTH = 64

# This has the same format and cost as a real hash.  It prevents a faster
# response for an unknown user from revealing whether a username exists.
DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$AAAAAAAAAAAAAAAAAAAAAA$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)


def normalize_username(value: str) -> str:
    """Allow readable Arabic/Latin usernames without allowing markup or controls."""
    username = value.strip()
    if not 3 <= len(username) <= USERNAME_MAX_LENGTH:
        return ""
    if not all(char.isalnum() or char in "._-@" for char in username):
        return ""
    return username


def password_policy_error(password: str) -> str | None:
    """Return a safe, actionable password-policy error, if any."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "يجب أن تتكون كلمة المرور من 12 حرفًا على الأقل."
    if len(password) > PASSWORD_MAX_LENGTH:
        return "كلمة المرور طويلة جدًا. الحد الأقصى هو 256 حرفًا."
    if any(char.isspace() for char in password):
        return "لا تستخدم مسافات في كلمة المرور."

    categories = sum((
        any(char.isalpha() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    ))
    if categories < 3:
        return "استخدم حروفًا وأرقامًا ورمزًا خاصًا واحدًا على الأقل."
    return None


def text_as_safe_html(text: object) -> str:
    """Escape untrusted text before placing it in an unsafe HTML container."""
    return html_escape(str(text)).replace("\n", "<br>")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_HASH_ITERATIONS
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, stored_password: str) -> bool:
    """Verify only PBKDF2 hashes; plaintext passwords are never accepted."""
    if not isinstance(password, str) or not isinstance(stored_password, str):
        return False
    if len(password) > PASSWORD_MAX_LENGTH:
        return False
    if not stored_password.startswith("pbkdf2_sha256$"):
        return False

    try:
        _, iterations_text, salt_text, digest_text = stored_password.split("$", 3)
        iterations = int(iterations_text)
        if not LEGACY_PASSWORD_HASH_MIN_ITERATIONS <= iterations <= 1_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        if len(salt) < 16 or len(expected) != 32:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def password_hash_iterations(stored_password: str) -> int:
    try:
        _, iterations_text, _, _ = stored_password.split("$", 3)
        return int(iterations_text)
    except (AttributeError, ValueError):
        return 0


def configured_bootstrap_users() -> tuple[dict, list[str]]:
    """Read only explicitly supplied credentials; never fall back to defaults."""
    users: dict = {}
    errors: list[str] = []
    definitions = (
        ("APP_ADMIN_USERNAME", "APP_ADMIN_PASSWORD", "admin", "مدير النظام", True),
        ("APP_EMPLOYEE_USERNAME", "APP_EMPLOYEE_PASSWORD", "employee", "موظف", False),
    )

    for username_key, password_key, role, label, required in definitions:
        username = os.getenv(username_key, "")
        password = os.getenv(password_key, "")
        if not username and not password:
            if required:
                errors.append("لم تُضبط بيانات مدير النظام في متغيرات البيئة.")
            continue
        clean_username = normalize_username(username)
        if not clean_username or not password:
            errors.append(f"تحقق من {username_key} و {password_key}.")
            continue
        if policy_error := password_policy_error(password):
            errors.append(f"كلمة مرور {username_key}: {policy_error}")
            continue
        users[clean_username] = {"password": password, "role": role, "label": label}
    return users, errors


BOOTSTRAP_USERS, AUTH_CONFIGURATION_ERRORS = configured_bootstrap_users()


def _open_users_db() -> sqlite3.Connection:
    return sqlite3.connect(USERS_DB_PATH, timeout=5)


def load_managed_users() -> dict:
    with _open_users_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                label TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                username TEXT PRIMARY KEY,
                first_failed_at INTEGER NOT NULL,
                failure_count INTEGER NOT NULL,
                locked_until INTEGER NOT NULL DEFAULT 0
            )
        """)
        for username, account in BOOTSTRAP_USERS.items():
            current = connection.execute(
                "SELECT password FROM users WHERE username = ?", (username,)
            ).fetchone()
            if current is None:
                connection.execute(
                    """INSERT INTO users (username, password, role, label)
                       VALUES (?, ?, ?, ?)""",
                    (username, hash_password(account["password"]), account["role"], account["label"]),
                )
            # Replace an older plaintext bootstrap credential with the explicitly
            # configured credential. This provides a safe recovery path from prior
            # releases without ever preserving a plaintext password on disk.
            elif not current[0].startswith("pbkdf2_sha256$"):
                connection.execute(
                    "UPDATE users SET password = ?, role = ?, label = ? WHERE username = ?",
                    (hash_password(account["password"]), account["role"], account["label"], username),
                )
        rows = connection.execute(
            "SELECT username, password, role, label FROM users"
        ).fetchall()
    return {
        username: {"password": password, "role": role, "label": label}
        for username, password, role, label in rows
    }


def save_managed_user(username: str, account: dict) -> None:
    with _open_users_db() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO users (username, password, role, label)
               VALUES (?, ?, ?, ?)""",
            (username, account["password"], account["role"], account["label"]),
        )


def delete_managed_user(username: str) -> None:
    with _open_users_db() as connection:
        connection.execute("DELETE FROM users WHERE username = ?", (username,))


def login_lock_remaining(username: str) -> int:
    now = int(time.time())
    with _open_users_db() as connection:
        row = connection.execute(
            "SELECT first_failed_at, locked_until FROM login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return 0
        first_failed_at, locked_until = row
        if locked_until > now:
            return locked_until - now
        if first_failed_at + LOGIN_FAILURE_WINDOW_SECONDS <= now:
            connection.execute("DELETE FROM login_attempts WHERE username = ?", (username,))
    return 0


def record_login_failure(username: str) -> int:
    """Record a failure and return the remaining lockout seconds, if now locked."""
    now = int(time.time())
    with _open_users_db() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT first_failed_at, failure_count FROM login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
        if not row or row[0] + LOGIN_FAILURE_WINDOW_SECONDS <= now:
            first_failed_at, failure_count = now, 0
        else:
            first_failed_at, failure_count = row
        failure_count += 1
        locked_until = now + LOGIN_LOCKOUT_SECONDS if failure_count >= LOGIN_MAX_FAILURES else 0
        connection.execute(
            """INSERT INTO login_attempts (username, first_failed_at, failure_count, locked_until)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                 first_failed_at = excluded.first_failed_at,
                 failure_count = excluded.failure_count,
                 locked_until = excluded.locked_until""",
            (username, first_failed_at, failure_count, locked_until),
        )
    return max(locked_until - now, 0)


def clear_login_failures(username: str) -> None:
    with _open_users_db() as connection:
        connection.execute("DELETE FROM login_attempts WHERE username = ?", (username,))


def clear_uploaded_data() -> None:
    if st.session_state.current_role != "admin":
        st.warning("صلاحية مسح البيانات متاحة لمدير النظام فقط.")
        return
    _statuses = ["قيد التوصيل", "المؤجل", "الراجع", "تم التسليم"]
    for key in _statuses:
        st.session_state[f"data_{key}"] = None
        st.session_state[f"raw_{key}"] = None
    st.rerun()


if "managed_users" not in st.session_state:
    st.session_state.managed_users = load_managed_users()

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024


def has_usable_login_account() -> bool:
    return any(
        isinstance(account.get("password"), str)
        and account["password"].startswith("pbkdf2_sha256$")
        for account in st.session_state.managed_users.values()
    )


def clear_authentication() -> None:
    components.html(
        f"""<script>
            window.parent.document.cookie =
                "{AUTH_COOKIE_NAME}=; Path=/; Max-Age=0; Secure; SameSite=Strict";
        </script>""",
        height=0,
    )
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.session_state.current_role = None
    st.session_state.last_auth_activity = None
    st.session_state["_auth_cookie_expiry"] = None
    st.session_state.show_user_management = False
    st.session_state.current_page = "home"


def set_browser_auth_cookie(username: str, account: dict) -> None:
    now = int(time.time())
    token, expires_at = create_auth_cookie(
        username,
        account["password"],
        now,
        LOGIN_SESSION_IDLE_SECONDS,
    )
    cookie_value = (
        f"{AUTH_COOKIE_NAME}={token}; Path=/; Secure; SameSite=Strict"
    )
    components.html(
        f"<script>window.parent.document.cookie = {json.dumps(cookie_value)};</script>",
        height=0,
    )
    st.session_state["_auth_cookie_expiry"] = expires_at


def restore_authentication_from_cookie() -> None:
    if st.session_state.authenticated:
        return
    token = st.context.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return
    verified = verify_auth_cookie(
        token,
        st.session_state.managed_users,
        int(time.time()),
        LOGIN_SESSION_IDLE_SECONDS,
    )
    if verified is None:
        clear_authentication()
        st.session_state.login_expired = True
        return
    username, expires_at = verified
    account = st.session_state.managed_users[username]
    st.session_state.authenticated = True
    st.session_state.current_user = username
    st.session_state.current_role = account["role"]
    st.session_state.last_auth_activity = time.time()
    st.session_state["_auth_cookie_expiry"] = expires_at


def refresh_authenticated_session() -> None:
    """Refresh active sessions and expire them after the configured idle interval."""
    if not st.session_state.authenticated:
        return
    now = time.time()
    last_activity = st.session_state.get("last_auth_activity")
    if not last_activity or now - last_activity > LOGIN_SESSION_IDLE_SECONDS:
        clear_authentication()
        st.session_state.login_expired = True
        return
    st.session_state.last_auth_activity = now
    cookie_expiry = st.session_state.get("_auth_cookie_expiry")
    if not cookie_expiry or cookie_expiry - now <= min(300, LOGIN_SESSION_IDLE_SECONDS // 3):
        username = st.session_state.current_user
        account = st.session_state.managed_users.get(username)
        if account is None:
            clear_authentication()
            return
        set_browser_auth_cookie(username, account)


# Previous releases put an authentication token in the URL. Remove it rather
# than accepting it: URLs leak through history, logs, bookmarks, and referrers.
if "auth" in st.query_params:
    st.query_params.pop("auth")

restore_authentication_from_cookie()
refresh_authenticated_session()

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
    gap: 5px;
    background: var(--surface-soft);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 6px;
    box-shadow: inset 0 1px 2px rgba(23, 32, 51, 0.035);
}

.stTabs [data-baseweb="tab"] {
    position: relative;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    min-height: 42px;
    border-radius: 9px;
    padding: 9px 16px 11px;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 600;
    color: var(--muted);
    background: transparent;
    border: none;
    white-space: nowrap;
    box-shadow: none;
    transition: color 0.22s ease, background-color 0.22s ease, box-shadow 0.22s ease;
}

.accounting-tabs-marker {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab-list"] {
    overflow-x: auto;
    scrollbar-width: none;
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none;
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab-list"] {
    overflow-x: auto;
    scrollbar-width: none;
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
    display: none;
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"],
.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"] {
    flex: 0 0 auto;
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]::before {
    content: "";
    display: inline-block;
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    background: currentColor;
    mask-position: center;
    mask-repeat: no-repeat;
    mask-size: contain;
    -webkit-mask-position: center;
    -webkit-mask-repeat: no-repeat;
    -webkit-mask-size: contain;
    opacity: 0.78;
    transition: opacity 0.22s ease, transform 0.22s ease;
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(1)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 3.75h7l4.25 4.5v12A1.75 1.75 0 0 1 16.5 22h-9A1.75 1.75 0 0 1 5.75 20.25v-14A2.5 2.5 0 0 1 8.25 3.75Z'/%3E%3Cpath d='M14 4v5h4.5M8.5 13h7M8.5 16.5h7'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 3.75h7l4.25 4.5v12A1.75 1.75 0 0 1 16.5 22h-9A1.75 1.75 0 0 1 5.75 20.25v-14A2.5 2.5 0 0 1 8.25 3.75Z'/%3E%3Cpath d='M14 4v5h4.5M8.5 13h7M8.5 16.5h7'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(2)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='9' cy='8' r='3.25'/%3E%3Cpath d='M2.75 19.25a6.25 6.25 0 0 1 12.5 0M16 5a3.25 3.25 0 0 1 0 6.25M17 14a5.25 5.25 0 0 1 4.25 5.15'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='9' cy='8' r='3.25'/%3E%3Cpath d='M2.75 19.25a6.25 6.25 0 0 1 12.5 0M16 5a3.25 3.25 0 0 1 0 6.25M17 14a5.25 5.25 0 0 1 4.25 5.15'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(3)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cellipse cx='12' cy='6' rx='7.5' ry='3'/%3E%3Cpath d='M4.5 6v5c0 1.65 3.35 3 7.5 3 1.1 0 2.15-.1 3.1-.3M4.5 11v5c0 1.65 3.35 3 7.5 3 1.45 0 2.8-.18 3.9-.5M19.5 11.5v-2M17 16.5l2.5-2.5 2.5 2.5M19.5 14v6'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cellipse cx='12' cy='6' rx='7.5' ry='3'/%3E%3Cpath d='M4.5 6v5c0 1.65 3.35 3 7.5 3 1.1 0 2.15-.1 3.1-.3M4.5 11v5c0 1.65 3.35 3 7.5 3 1.45 0 2.8-.18 3.9-.5M19.5 11.5v-2M17 16.5l2.5-2.5 2.5 2.5M19.5 14v6'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(4)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 8V3.75h12V8M6 17H4.5A2.5 2.5 0 0 1 2 14.5v-4A2.5 2.5 0 0 1 4.5 8h15a2.5 2.5 0 0 1 2.5 2.5v4a2.5 2.5 0 0 1-2.5 2.5H18'/%3E%3Cpath d='M6 14h12v6.25H6zM17.5 11.5h.01'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 8V3.75h12V8M6 17H4.5A2.5 2.5 0 0 1 2 14.5v-4A2.5 2.5 0 0 1 4.5 8h15a2.5 2.5 0 0 1 2.5 2.5v4a2.5 2.5 0 0 1-2.5 2.5H18'/%3E%3Cpath d='M6 14h12v6.25H6zM17.5 11.5h.01'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(5)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3.5 19.5h17M5.5 16V11M10 16V6.5M14.5 16v-3.5M19 16V8'/%3E%3Cpath d='m4.5 8.5 5-4 4.5 5 6-5'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3.5 19.5h17M5.5 16V11M10 16V6.5M14.5 16v-3.5M19 16V8'/%3E%3Cpath d='m4.5 8.5 5-4 4.5 5 6-5'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]::before {
    content: "";
    display: inline-block;
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    background: currentColor;
    mask-position: center;
    mask-repeat: no-repeat;
    mask-size: contain;
    -webkit-mask-position: center;
    -webkit-mask-repeat: no-repeat;
    -webkit-mask-size: contain;
    opacity: 0.78;
    transition: opacity 0.22s ease, transform 0.22s ease;
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(1)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 3.75h7l4.25 4.5v12A1.75 1.75 0 0 1 16.5 22h-9A1.75 1.75 0 0 1 5.75 20.5v-14A2.5 2.5 0 0 1 8.25 4Z'/%3E%3Cpath d='M14 4v5h4.5M8.5 13h7M8.5 16.5h7'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M7 3.75h7l4.25 4.5v12A1.75 1.75 0 0 1 16.5 22h-9A1.75 1.75 0 0 1 5.75 20.5v-14A2.5 2.5 0 0 1 8.25 4Z'/%3E%3Cpath d='M14 4v5h4.5M8.5 13h7M8.5 16.5h7'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(2)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 20V11M10 20V5M16 20v-7M22 20H2'/%3E%3Cpath d='m4 8 6-4 6 6 5-5'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 20V11M10 20V5M16 20v-7M22 20H2'/%3E%3Cpath d='m4 8 6-4 6 6 5-5'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(3)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3.5' y='4' width='17' height='16' rx='2'/%3E%3Cpath d='M3.5 9h17M9 4v16M15 9v11'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3.5' y='4' width='17' height='16' rx='2'/%3E%3Cpath d='M3.5 9h17M9 4v16M15 9v11'/%3E%3C/svg%3E");
}

.stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]:nth-child(4)::before {
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3v12M7.5 10.5 12 15l4.5-4.5M4 16v4h16v-4'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3v12M7.5 10.5 12 15l4.5-4.5M4 16v4h16v-4'/%3E%3C/svg%3E");
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--brand);
    background: rgba(15, 118, 110, 0.055);
}

.stTabs [aria-selected="true"] {
    isolation: isolate;
    background: linear-gradient(135deg, #0f766e, #115e59) !important;
    color: white !important;
    font-weight: 800;
    box-shadow: 0 3px 8px rgba(15, 118, 110, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [aria-selected="true"]::before {
    opacity: 1;
    transform: scale(1.08);
}

.stTabs [aria-selected="true"]::after {
    content: "";
    position: absolute;
    inset-inline: 36%;
    bottom: 4px;
    height: 2px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.72);
    pointer-events: none;
}

.stTabs [data-baseweb="tab"]:focus-visible {
    outline: 2px solid #0f766e !important;
    outline-offset: 2px;
    box-shadow: none;
}

.stTabs [role="tabpanel"] {
    animation: tab-panel-enter 0.26s ease-out both;
}

.profit-intro {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px 22px;
    margin: 4px 0 18px;
    border: 1px solid #cce5e2;
    border-radius: 16px;
    background: linear-gradient(115deg, #f0fdfa 0%, #ffffff 72%);
    box-shadow: 0 8px 24px rgba(15, 118, 110, 0.07);
}

.profit-intro-icon {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    flex: 0 0 54px;
    border-radius: 15px;
    background: linear-gradient(145deg, #0f766e, #115e59);
    color: #ffffff;
    font-size: 1.35rem;
    box-shadow: 0 6px 14px rgba(15, 118, 110, 0.2);
}

.profit-intro h3 {
    margin: 0 0 4px;
    color: var(--ink);
    font-size: 1.08rem;
    font-weight: 900;
}

.profit-intro p {
    margin: 0;
    color: var(--muted);
    font-size: 0.84rem;
}

.profit-result {
    padding: 20px 22px;
    margin: 12px 0 18px;
    border: 1px solid #a7f3d0;
    border-radius: 16px;
    background: linear-gradient(120deg, #ecfdf5, #f0fdfa);
    text-align: center;
    box-shadow: 0 8px 24px rgba(15, 118, 110, 0.08);
}

.profit-result.is-negative {
    border-color: #fecaca;
    background: linear-gradient(120deg, #fff1f2, #fff7ed);
    box-shadow: 0 8px 24px rgba(190, 18, 60, 0.07);
}

.profit-result-label {
    color: #475569;
    font-size: 0.9rem;
    font-weight: 700;
}

.profit-result-value {
    margin-top: 4px;
    color: #047857;
    font-size: clamp(1.7rem, 4vw, 2.5rem);
    font-weight: 900;
    line-height: 1.35;
    direction: ltr;
    unicode-bidi: isolate;
}

.profit-result.is-negative .profit-result-value {
    color: #be123c;
}

.stApp:has(.theme-dark-marker) .profit-intro {
    border-color: #315d5a;
    background: linear-gradient(115deg, #173b3b, #172033 72%);
}

.stApp:has(.theme-dark-marker) .profit-intro h3 {
    color: #e5e7eb;
}

.stApp:has(.theme-dark-marker) .profit-result {
    border-color: #216b57;
    background: linear-gradient(120deg, #123b34, #173b3b);
}

.stApp:has(.theme-dark-marker) .profit-result.is-negative {
    border-color: #7f3345;
    background: linear-gradient(120deg, #3b1e2b, #33251f);
}

.stApp:has(.theme-dark-marker) .profit-result-label {
    color: #cbd5e1;
}

@keyframes tab-panel-enter {
    from {
        opacity: 0.72;
        transform: translateY(5px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.page-transition-marker {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
}

.stMainBlockContainer:has(.page-transition-marker) {
    animation: page-content-enter 0.42s cubic-bezier(0.2, 0.75, 0.25, 1) both;
}

@keyframes page-content-enter {
    from {
        opacity: 0.45;
        transform: translateY(12px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (prefers-reduced-motion: reduce) {
    .stMainBlockContainer:has(.page-transition-marker) {
        animation: none !important;
    }

    .stTabs [data-baseweb="tab"] {
        transition: none !important;
    }

    .stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]::before {
        transition: none !important;
    }

    .stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]::before {
        transition: none !important;
    }

    .stTabs [role="tabpanel"] {
        animation: none !important;
    }
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

.st-key-login_shell {
    position: relative;
    isolation: isolate;
    width: min(100%, 1080px);
    min-height: 560px;
    margin: clamp(1rem, 5vh, 3.5rem) auto;
}

.login-ambient {
    position: absolute;
    z-index: -1;
    inset: 6% 8%;
    overflow: hidden;
    border-radius: 28px;
    filter: blur(20px);
    pointer-events: none;
}

.login-orb {
    position: absolute;
    width: 210px;
    height: 210px;
    border-radius: 50%;
    opacity: 0.18;
    background: #2dd4bf;
    animation: login-float 11s ease-in-out infinite;
}

.login-orb--one { top: -70px; right: 5%; }
.login-orb--two { bottom: -80px; left: 16%; background: #60a5fa; animation-delay: -5s; }

.st-key-login_panel {
    position: relative;
    min-height: 560px;
    padding: 56px 46px;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: color-mix(in srgb, var(--surface) 96%, transparent);
    box-shadow: 0 24px 60px rgba(23, 32, 51, 0.12), 0 4px 14px rgba(23, 32, 51, 0.06);
    animation: login-panel-in 0.65s cubic-bezier(.2,.8,.2,1) both;
}

.st-key-login_panel > div {
    position: relative;
    z-index: 1;
}

.login-art {
    position: relative;
    display: flex;
    flex: 1;
    align-items: center;
    justify-content: center;
    min-height: 560px;
    overflow: hidden;
    background: linear-gradient(145deg, #0f766e 0%, #115e59 58%, #164e63 100%);
    color: white;
    border-radius: 22px;
    box-shadow: 0 24px 60px rgba(8, 47, 73, 0.2);
    animation: login-art-in 0.72s cubic-bezier(.2,.8,.2,1) both;
}

.login-art::before {
    content: "";
    position: absolute;
    inset: 0;
    opacity: 0.22;
    background-image: linear-gradient(135deg, rgba(255,255,255,0.16) 1px, transparent 1px), linear-gradient(45deg, rgba(255,255,255,0.1) 1px, transparent 1px);
    background-size: 34px 34px;
    transform: scale(1.15);
    animation: login-grid-shift 22s linear infinite;
}

.login-art::after {
    content: "";
    position: absolute;
    width: 280px;
    height: 280px;
    right: -80px;
    bottom: -110px;
    border: 1px solid rgba(255,255,255,0.28);
    border-radius: 50%;
    box-shadow: 0 0 0 36px rgba(255,255,255,0.035), 0 0 0 74px rgba(255,255,255,0.025);
    animation: login-breathe 6s ease-in-out infinite;
}

.login-art-content {
    position: relative;
    z-index: 1;
    width: min(78%, 420px);
}

.login-art-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 11px;
    border: 1px solid rgba(255,255,255,0.24);
    border-radius: 999px;
    background: rgba(255,255,255,0.12);
    font-size: 0.76rem;
    font-weight: 700;
    animation: login-rise 0.5s 0.12s both;
}

.login-art-icon {
    display: grid;
    place-items: center;
    width: 72px;
    height: 72px;
    margin: 28px 0 18px;
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 20px;
    background: rgba(255,255,255,0.14);
    box-shadow: 0 14px 30px rgba(0,0,0,0.14);
    animation: login-icon-float 5s ease-in-out 0.2s infinite;
}

.login-art-icon .pi {
    font-size: 2rem;
}

.login-art-title {
    margin: 0 0 10px;
    color: white;
    font-size: 2rem;
    line-height: 1.25;
    animation: login-rise 0.5s 0.28s both;
}

.login-art-copy {
    margin: 0 0 26px;
    color: rgba(255,255,255,0.78);
    font-size: 0.9rem;
    line-height: 1.8;
    animation: login-rise 0.5s 0.34s both;
}

.login-art-stats {
    display: flex;
    gap: 10px;
    animation: login-rise 0.5s 0.42s both;
}

.login-art-stat {
    flex: 1;
    padding: 12px;
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: 12px;
    background: rgba(255,255,255,0.1);
    transition: transform 0.22s ease, background-color 0.22s ease;
}

.login-art-stat:hover {
    background: rgba(255,255,255,0.18);
    transform: translateY(-4px);
}

.login-art-stat strong,
.login-art-stat span {
    display: block;
}

.login-art-stat strong {
    margin-bottom: 3px;
    font-size: 1.1rem;
}

.login-art-stat span {
    color: rgba(255,255,255,0.7);
    font-size: 0.7rem;
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
    box-shadow: 0 12px 24px rgba(15, 118, 110, 0.22);
    animation: login-logo-in 0.55s cubic-bezier(.2,.9,.3,1.35) both;
}

.login-title {
    margin: 0 0 8px;
    color: var(--ink);
    font-size: 1.45rem;
    text-align: center;
    animation: login-rise 0.45s 0.1s both;
}

.login-subtitle {
    margin: 0 0 24px;
    color: var(--muted);
    font-size: 0.82rem;
    text-align: center;
    animation: login-rise 0.45s 0.16s both;
}

.st-key-login_panel .stTextInput input {
    min-height: 46px;
    border-radius: 10px !important;
    padding-inline: 14px !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.st-key-login_panel .stTextInput input:focus {
    border-color: var(--brand) !important;
    box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.14) !important;
    transform: translateY(-1px);
}

.st-key-login_panel .stFormSubmitButton button {
    position: relative;
    overflow: hidden;
    width: 100%;
    min-height: 46px;
    border: 0;
    border-radius: 10px !important;
    background: var(--brand);
    color: white;
    font-weight: 800;
    box-shadow: 0 8px 18px rgba(15, 118, 110, 0.2);
    transition: background-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.st-key-login_panel .stFormSubmitButton button::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 42%;
    left: -55%;
    transform: skewX(-24deg);
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent);
    transition: left 0.55s ease;
}

.st-key-login_panel .stFormSubmitButton button:hover {
    background: var(--brand-dark);
    transform: translateY(-2px);
    box-shadow: 0 12px 24px rgba(15, 118, 110, 0.28);
}

.st-key-login_panel .stFormSubmitButton button:hover::after { left: 120%; }

.login-security-note {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-top: 16px;
    padding: 10px 12px;
    border: 1px solid color-mix(in srgb, var(--brand) 18%, var(--line));
    border-radius: 10px;
    background: color-mix(in srgb, var(--brand) 5%, var(--surface));
    color: var(--muted);
    font-size: 0.72rem;
    line-height: 1.65;
}

.login-security-note .pi { color: var(--brand); }

@keyframes login-panel-in {
    from { opacity: 0; transform: translateX(18px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes login-art-in {
    from { opacity: 0; transform: translateX(-22px) scale(.985); }
    to { opacity: 1; transform: translateX(0) scale(1); }
}

@keyframes login-rise {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes login-logo-in {
    from { opacity: 0; transform: scale(.72) rotate(-9deg); }
    to { opacity: 1; transform: scale(1) rotate(0); }
}

@keyframes login-icon-float {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-8px); }
}

@keyframes login-grid-shift {
    from { transform: scale(1.15) translate(0, 0); }
    to { transform: scale(1.15) translate(34px, 34px); }
}

@keyframes login-breathe {
    0%, 100% { transform: scale(1); opacity: .72; }
    50% { transform: scale(1.08); opacity: 1; }
}

@keyframes login-float {
    0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
    50% { transform: translate3d(24px, -20px, 0) scale(1.1); }
}

@media (prefers-reduced-motion: reduce) {
    .login-orb,
    .st-key-login_panel,
    .login-art,
    .login-art::before,
    .login-art::after,
    .login-art-badge,
    .login-art-icon,
    .login-art-title,
    .login-art-copy,
    .login-art-stats,
    .login-logo {
        animation: none !important;
    }
    .st-key-login_panel *, .login-art * { transition-duration: 0.01ms !important; }
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

.st-key-topbar_accounting > button {
    min-height: 40px;
    padding: 4px 12px !important;
    border: 1px solid #b7d8d4 !important;
    border-radius: 2rem !important;
    background: linear-gradient(135deg, #f0fdfa, #e6fffb) !important;
    color: #0f766e !important;
    font-size: 0.78rem !important;
    font-weight: 800 !important;
    margin-bottom: 5px;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    box-shadow: 0 2px 7px rgba(15, 118, 110, 0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease !important;
}

.st-key-topbar_accounting > button:hover {
    transform: translateY(-1px);
    border-color: #0f766e !important;
    background: linear-gradient(135deg, #ccfbf1, #d9f9f2) !important;
    box-shadow: 0 5px 14px rgba(15, 118, 110, 0.16);
}

.accounting-button-icon {
    display: inline-grid;
    place-items: center;
    width: 27px;
    height: 27px;
    flex: 0 0 27px;
    border: 1px solid rgba(15, 118, 110, 0.16);
    border-radius: 50%;
    background: #ffffff;
    color: #0f766e;
    font-size: 0.9rem;
    line-height: 1;
    transition: transform 0.2s ease, background 0.2s ease, color 0.2s ease;
}

.st-key-topbar_accounting > button:hover .accounting-button-icon {
    transform: rotate(-8deg) scale(1.05);
    background: #0f766e;
    color: #ffffff;
}

.accounting-button-label {
    white-space: nowrap;
}

.stApp:has(.theme-dark-marker) .st-key-topbar_accounting > button {
    border-color: #3b6470 !important;
    background: linear-gradient(135deg, #173b3b, #164e4a) !important;
    color: #99f6e4 !important;
    box-shadow: 0 2px 9px rgba(0, 0, 0, 0.2);
}

.stApp:has(.theme-dark-marker) .accounting-button-icon {
    border-color: #3b6470;
    background: #1e293b;
    color: #99f6e4;
}

.stApp:has(.theme-dark-marker) .st-key-topbar_accounting > button:hover .accounting-button-icon {
    background: #0f766e;
    color: #ffffff;
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
    .stTabs [data-baseweb="tab"] { gap: 6px !important; padding: 8px 9px 10px; font-size: 0.78rem; }
    .stMainBlockContainer:has(.accounting-tabs-marker) .stTabs [data-baseweb="tab"]::before {
        width: 16px;
        height: 16px;
        flex-basis: 16px;
    }
    .stMainBlockContainer:has(.results-tabs-marker) .stTabs [data-baseweb="tab"]::before {
        width: 16px;
        height: 16px;
        flex-basis: 16px;
    }
    .upload-label { min-height: 38px; font-size: 0.82rem; }
    [data-testid="stFileUploader"] section { height: 104px; padding: 8px; }
    .app-topbar { gap: 6px; padding: 8px; overflow-x: auto; }
    .topbar-account { display: none; }
    .st-key-login_shell { margin: 0.75rem auto; min-height: auto; }
    .st-key-login_panel { min-height: auto; padding: 32px 22px; }
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
.st-key-login_panel,
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

.stApp:has(.theme-dark-marker) .st-key-login_panel {
    background: #172033;
    border-color: #334155;
}

.stApp:has(.theme-dark-marker) .login-art {
    background: linear-gradient(145deg, #115e59 0%, #134e4a 58%, #164e63 100%);
}

.stApp:has(.theme-dark-marker) .stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #0f766e, #115e59) !important;
    color: white !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.stApp:has(.theme-dark-marker) .stTabs [data-baseweb="tab"]:hover:not([aria-selected="true"]) {
    background: rgba(153, 246, 228, 0.08);
    color: #99f6e4;
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
    with st.container(key="login_shell"):
        st.markdown(
            """<div class="login-ambient" aria-hidden="true">
                <span class="login-orb login-orb--one"></span>
                <span class="login-orb login-orb--two"></span>
            </div>""",
            unsafe_allow_html=True,
        )
        login_cols = st.columns([1, 1.45])
        with login_cols[0]:
            with st.container(key="login_panel"):
                st.markdown(
                    "<div class='login-logo' aria-hidden='true'>م</div>"
                    "<h1 class='login-title'>مرحبًا بك</h1>"
                    "<p class='login-subtitle'>سجّل الدخول إلى لوحة بيانات المندوبين</p>",
                    unsafe_allow_html=True,
                )
                username = ""
                password = ""
                submitted = False
                if AUTH_CONFIGURATION_ERRORS and not has_usable_login_account():
                    st.error("لا يمكن تفعيل تسجيل الدخول قبل إعداد حساب مدير آمن.")
                    st.caption("اضبط APP_ADMIN_USERNAME و APP_ADMIN_PASSWORD في بيئة الاستضافة، ثم أعد تشغيل التطبيق.")
                else:
                    with st.form("login_form"):
                        username = st.text_input(
                            "اسم المستخدم",
                            placeholder="أدخل اسم المستخدم",
                            max_chars=USERNAME_MAX_LENGTH,
                        )
                        password = st.text_input(
                            "كلمة المرور",
                            type="password",
                            placeholder="أدخل كلمة المرور",
                            max_chars=PASSWORD_MAX_LENGTH,
                        )
                        submitted = st.form_submit_button("تسجيل الدخول", use_container_width=True)
                    st.markdown(
                        f"""<div class="login-security-note">
                            <i class="pi pi-shield" aria-hidden="true"></i>
                            <span>تنتهي الجلسة تلقائيًا بعد {LOGIN_SESSION_IDLE_SECONDS // 60} دقيقة من عدم النشاط.</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

        with login_cols[1]:
            st.markdown("""
            <div class='login-art'>
                <div class='login-art-content'>
                    <div class='login-art-badge'><i class='pi pi-shield'></i><span>منصة تشغيل موثوقة</span></div>
                    <div class='login-art-icon'><i class='pi pi-chart-bar' aria-hidden='true'></i></div>
                    <h2 class='login-art-title'>كل بيانات المندوبين في مكان واحد</h2>
                    <p class='login-art-copy'>تابع الملفات والحالات والإحصائيات من لوحة واضحة تساعدك على اتخاذ القرار بسرعة.</p>
                    <div class='login-art-stats'>
                        <div class='login-art-stat'><strong>4</strong><span>حالات متابعة</span></div>
                        <div class='login-art-stat'><strong>24/7</strong><span>وصول للبيانات</span></div>
                        <div class='login-art-stat'><strong>آمن</strong><span>إدارة صلاحيات</span></div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if st.session_state.pop("login_expired", False):
        st.warning("انتهت الجلسة لعدم النشاط. سجّل الدخول للمتابعة.")

    if submitted:
        clean_username = normalize_username(username)
        rate_limit_key = clean_username or "invalid-username"
        remaining_lock_time = login_lock_remaining(rate_limit_key)
        if remaining_lock_time:
            st.error(f"تم إيقاف محاولات الدخول مؤقتًا. حاول بعد {max(1, -(-remaining_lock_time // 60))} دقيقة.")
        else:
            account = st.session_state.managed_users.get(clean_username)
            # Always derive a PBKDF2 hash, even for an unknown username, to make
            # username enumeration through response timing substantially harder.
            password_is_valid = verify_password(
                password, account["password"] if account else DUMMY_PASSWORD_HASH
            )
            if account and password_is_valid:
                clear_login_failures(clean_username)
                if password_hash_iterations(account["password"]) < PASSWORD_HASH_ITERATIONS:
                    account["password"] = hash_password(password)
                    save_managed_user(clean_username, account)
                st.session_state.login_expired = False
                st.session_state.last_auth_activity = time.time()
                st.session_state.authenticated = True
                st.session_state.current_user = clean_username
                st.session_state.current_role = account["role"]
                set_browser_auth_cookie(clean_username, account)
                st.rerun()

            remaining_lock_time = record_login_failure(rate_limit_key)
            if remaining_lock_time:
                st.error("تم إيقاف محاولات الدخول مؤقتًا لحماية الحساب. حاول لاحقًا.")
            else:
                st.error("بيانات الدخول غير صحيحة")
    st.stop()

page_changed = st.session_state.get("_last_rendered_page") != st.session_state.current_page
st.session_state["_last_rendered_page"] = st.session_state.current_page
if page_changed:
    st.markdown(
        "<span class='page-transition-marker' aria-hidden='true'></span>",
        unsafe_allow_html=True,
    )

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
                new_username = st.text_input(
                    "اسم الموظف", placeholder="employee2", max_chars=USERNAME_MAX_LENGTH
                )
            with add_cols[1]:
                new_password = st.text_input(
                    "كلمة المرور", type="password", max_chars=PASSWORD_MAX_LENGTH
                )
            with add_cols[2]:
                add_employee = st.form_submit_button("إضافة موظف", use_container_width=True)

        if add_employee:
            clean_username = normalize_username(new_username)
            if not clean_username or not new_password:
                st.warning("أدخل اسم مستخدم صحيحًا وكلمة مرور.")
            elif clean_username in st.session_state.managed_users:
                st.error("اسم المستخدم موجود مسبقًا")
            elif policy_error := password_policy_error(new_password):
                st.error(policy_error)
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
                clear_login_failures(delete_user)
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

# ==================== نظام الذكاء الاصطناعي للتعرف على الأعمدة ====================

def is_code_column(value):
    """فحص إذا كانت القيمة تبدو كأنها كود (رقم طويل)"""
    if value is None:
        return False
    clean = str(value).strip()
    if clean.endswith(".0"):
        clean = clean[:-2]
    return clean.isdigit() and len(clean) >= 8


def is_datetime_column(value):
    """فحص إذا كانت القيمة تبدو كأنها تاريخ/وقت"""
    if value is None:
        return False
    datetime_patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}/\d{2}/\d{4}',
        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',
        r'\d{2}:\d{2}:\d{2}',
        r'\d{2}:\d{2}',
    ]
    val_str = str(value).strip()
    for pattern in datetime_patterns:
        if re.search(pattern, val_str):
            return True
    return False


def is_name_column(value):
    """فحص إذا كانت القيمة تبدو كأنها اسم (نص عربي أو إنجليزي)"""
    if value is None:
        return False
    clean = str(value).strip()
    has_arabic = bool(re.search(r'[\u0600-\u06FF]', clean))
    has_english = bool(re.search(r'[a-zA-Z]', clean))
    has_spaces = ' ' in clean or '-' in clean
    return (has_arabic or has_english) and (has_spaces or len(clean.split()) > 1 or '-' in clean)


def detect_column_type(sample_values):
    """
    تحليل عينة من القيم لتحديد نوع العمود
    Returns: 'code', 'name', 'datetime', or 'unknown'
    """
    if not sample_values:
        return 'unknown'
    sample_values = [str(v).strip() for v in sample_values if v is not None and str(v).strip() and str(v).lower() not in ('nan', 'none', 'nat')]
    if not sample_values:
        return 'unknown'
    code_score = sum(1 for v in sample_values if is_code_column(v))
    datetime_score = sum(1 for v in sample_values if is_datetime_column(v))
    name_score = sum(1 for v in sample_values if is_name_column(v))
    total = len(sample_values)
    threshold = 0.7
    if code_score / total >= threshold:
        return 'code'
    elif datetime_score / total >= threshold:
        return 'datetime'
    elif name_score / total >= threshold:
        return 'name'
    else:
        return 'unknown'


def extract_date_only(datetime_str):
    """استخراج التاريخ فقط وحذف الوقت"""
    if not datetime_str:
        return str(datetime_str) if datetime_str is not None else ""
    match = re.search(r'\d{4}-\d{2}-\d{2}', str(datetime_str))
    if match:
        return match.group(0)
    return str(datetime_str).strip()


def auto_detect_columns(lines, max_samples=10):
    """
    الكشف التلقائي عن أنواع الأعمدة من البيانات
    Returns: dict with column indices and their types
    """
    if not lines:
        return {}

    # أخذ عينة من الأسطر للتحليل
    sample_lines = lines[:min(max_samples, len(lines))]

    # تحليل كل عمود
    column_data = {}

    for line in sample_lines:
        parts = line.split("\t") if "\t" in line else [p.strip() for p in re.split(r'[,|;]', line)]
        for i, part in enumerate(parts):
            if i not in column_data:
                column_data[i] = []
            column_data[i].append(part.strip())

    # تحديد نوع كل عمود
    column_types = {}
    for col_idx, values in column_data.items():
        col_type = detect_column_type(values)
        column_types[col_idx] = col_type

    return column_types


def convert_raw_text(text: str, separator: str = " | ") -> tuple[str, dict]:
    """
    معالجة النص المنسوخ وتحويله بصيغة مع البطاقة باحترافية وتوافق تام
    """
    if not text or not text.strip():
        return "", {"status": "empty", "message": "⚠️ الرجاء إدخال بيانات!"}

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return "", {"status": "empty", "message": "⚠️ الرجاء إدخال بيانات صالحة!"}

    # 🤖 الكشف التلقائي الذكي عن أنواع الأعمدة
    column_types = auto_detect_columns(lines)

    code_col = None
    name_col = None
    datetime_col = None

    for col_idx, col_type in column_types.items():
        if col_type == 'code' and code_col is None:
            code_col = col_idx
        elif col_type == 'name' and name_col is None:
            name_col = col_idx
        elif col_type == 'datetime' and datetime_col is None:
            datetime_col = col_idx

    # إذا لم يتم الكشف عن الاسم، نستخدم الطريقة التقليدية (العمود الثاني)
    if name_col is None:
        name_col = 1 if len(column_types) > 1 else 0

    detected_parts = []
    if code_col is not None:
        detected_parts.append(f"كود[{code_col}]")
    if name_col is not None:
        detected_parts.append(f"اسم[{name_col}]")
    if datetime_col is not None:
        detected_parts.append(f"تاريخ[{datetime_col}]")
    detected_info = "🤖 تم الكشف: " + (" ".join(detected_parts) if detected_parts else "تلقائي")

    grouped_data = {}
    structured_drivers = {}

    for line in lines:
        parts = line.split("\t") if "\t" in line else [p.strip() for p in re.split(r'[,|;]', line)]
        parts = [p.strip() for p in parts]

        if not parts:
            continue

        name = parts[name_col] if name_col < len(parts) else ""
        if not name:
            continue

        entry_parts = []
        c_val = ""
        d_val = ""

        if code_col is not None and code_col < len(parts):
            c_val = parts[code_col]
            if c_val.endswith(".0"):
                c_val = c_val[:-2]
            if c_val:
                entry_parts.append(c_val)

        if datetime_col is not None and datetime_col < len(parts):
            d_val = extract_date_only(parts[datetime_col])
            if d_val:
                entry_parts.append(d_val)

        if not entry_parts:
            entry_parts = [p for i, p in enumerate(parts) if i != name_col and p]

        if name not in grouped_data:
            grouped_data[name] = []
            structured_drivers[name] = {"codes": [], "entries": [], "count": 0}

        if entry_parts:
            grouped_data[name].append(entry_parts)
            joined_entry = separator.join(entry_parts)
            structured_drivers[name]["entries"].append(joined_entry)
            if c_val:
                structured_drivers[name]["codes"].append(c_val)
            structured_drivers[name]["count"] += 1

    # بناء النتيجة - كود البطاقة والتاريخ لكل طلب، ثم اسم المندوب في الأسفل، ثم خط فاصل بين المندوبين
    output_lines = []
    names_list = list(grouped_data.keys())
    for i, name in enumerate(names_list):
        entries = grouped_data[name]
        for entry in entries:
            joined = separator.join(entry)
            output_lines.append(joined)
        output_lines.append(name)
        if i < len(names_list) - 1:
            output_lines.append("─" * 15)

    result = "\n".join(output_lines)
    meta = {
        "status": "success",
        "detected_info": detected_info,
        "total_names": len(grouped_data),
        "total_entries": sum(len(e) for e in grouped_data.values()),
        "structured_drivers": structured_drivers
    }
    return result, meta


# ─── دوال مساعدة ──────────────────────────────────────────────────────────────
@st.cache_data
def detect_columns(df: pd.DataFrame):
    col_driver = col_code = col_date = None
    
    # 1. محاولة التعرف عبر أسماء الأعمدة المعتادة
    for col in df.columns:
        col_str = str(col).lower()
        if any(p in col_str for p in POSSIBLE_DRIVER_COLS) and not col_driver:
            col_driver = col
        if any(p in col_str for p in POSSIBLE_CODE_COLS) and not col_code:
            col_code = col
        if any(p in col_str for p in POSSIBLE_DATE_COLS) and not col_date:
            col_date = col

    # 2. الكشف الذكي بتحليل عينات البيانات للأعمدة المتبقية
    if not col_driver or not col_code or not col_date:
        sample_df = df.head(15)
        for col in df.columns:
            samples = sample_df[col].dropna().tolist()
            ctype = detect_column_type(samples)
            if ctype == 'name' and not col_driver:
                col_driver = col
            elif ctype == 'code' and not col_code:
                col_code = col
            elif ctype == 'datetime' and not col_date:
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
def process_df(df, col_driver, col_code, col_date=None):
    """إرجاع dict: اسم المندوب → {codes, entries, count}"""
    result = {}
    for driver_name, group in df.groupby(col_driver):
        codes = []
        entries = []
        code_series = group[col_code].tolist() if col_code and col_code in group.columns else [None] * len(group)
        date_series = group[col_date].tolist() if col_date and col_date in group.columns else [None] * len(group)

        for c, d in zip(code_series, date_series):
            c_str = ""
            if c is not None and str(c).strip() and str(c).lower() not in ('nan', 'none'):
                c_str = str(c).strip()
                if c_str.endswith(".0"):
                    c_str = c_str[:-2]
                codes.append(c_str)

            d_str = ""
            if d is not None and str(d).strip() and str(d).lower() not in ('nan', 'none', 'nat'):
                d_str = extract_date_only(d)

            if c_str and d_str:
                entries.append(f"{c_str} | {d_str}")
            elif c_str:
                entries.append(c_str)
            elif d_str:
                entries.append(d_str)

        result[str(driver_name)] = {
            "codes": codes,
            "entries": entries if entries else codes,
            "count": len(group)
        }
    return result


def build_text_output(drivers_data: dict, title: str) -> str:
    lines = [f"★ {title} ★", "=" * 22]
    for name in sorted(drivers_data.keys()):
        d = drivers_data[name]
        lines.append(name)
        lines.append(str(d["count"]))
        lines.append("-" * 15)
    return "\n".join(lines)


def build_whatsapp_output(drivers_data: dict, title: str = "") -> str:
    """مخرجات خيار مع كود البطاقة:
    كود | تاريخ (لكل طلب)
    اسم المندوب في الأسفل
    خط فاصل بين المندوبين
    """
    output_lines = []
    names = sorted(drivers_data.keys())
    for i, name in enumerate(names):
        d = drivers_data[name]
        items = d.get("entries") if d.get("entries") else d.get("codes", [])
        output_lines.append(str(name))
        for item in items:
            output_lines.append(str(item))
        if i < len(names) - 1:
            output_lines.append("─" * 15)
    return "\n".join(output_lines)


def render_copy_button(text: str, key: str) -> None:
    """عرض زر ينسخ النص إلى حافظة المستخدم."""
    import json

    # JSON does not escape a closing script tag by default. Escape it before
    # embedding untrusted spreadsheet content inside this component's script.
    text_json = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
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



# ─── محاسبة المندوبين ───────────────────────────────────────────────────────────
ACCOUNTING_DRIVER_COLS = [
    "اسم المندوب", "المندوب", "drivername", "driver", "الاسم", "اسم المندوبين"
]
ACCOUNTING_RECEIPT_COLS = [
    "رقم الوصل", "رقم الوصول", "الوصل", "الوصول", "رقم الطلب",
    "code", "كود", "id", "الكود", "رقم", "serial", "رقم الفاتورة",
    "invoice", "order_id", "order id", "رقم الطلبية", "الرقم",
]

def _norm_col(value):
    return re.sub(r"\s+", "", str(value).strip().lower())

def _find_col(df, candidates):
    normalized = {_norm_col(c): c for c in df.columns}
    for candidate in candidates:
        key = _norm_col(candidate)
        if key in normalized:
            return normalized[key]
    # fallback: substring matching
    for c in df.columns:
        cc = _norm_col(c)
        if any(_norm_col(x) in cc or cc in _norm_col(x) for x in candidates):
            return c
    return None

def accounting_extract_rows(df):
    """Extract driver and receipt rows. One non-empty receipt row = one order."""
    driver_col = _find_col(df, ACCOUNTING_DRIVER_COLS)
    receipt_col = _find_col(df, ACCOUNTING_RECEIPT_COLS)

    # Fallback: try to find driver column by scanning actual column names
    # (do NOT call detect_columns — it may return wrong col names for accounting sheets)
    if not driver_col:
        for col in df.columns:
            col_low = str(col).strip().lower()
            if any(x in col_low for x in ["driver", "مندوب", "اسم"]):
                driver_col = col
                break

    if not driver_col:
        return None, None, "لم يتم العثور على عمود اسم المندوب في الملف."

    # If no receipt column found, treat each non-empty driver row as one order.
    if not receipt_col:
        work = df[[driver_col]].copy()
        work.columns = ["المندوب"]
        work["المندوب"] = work["المندوب"].astype(str).str.strip()
        work = work[
            work["المندوب"].ne("") & work["المندوب"].str.lower().ne("nan")
        ].copy()
        work["رقم الوصل"] = range(1, len(work) + 1)
        if work.empty:
            return None, None, "لم توجد وصولات صالحة في الملف."
        return work, driver_col, None

    # Verify receipt_col actually exists in dataframe before using it
    if receipt_col not in df.columns:
        work = df[[driver_col]].copy()
        work.columns = ["المندوب"]
        work["المندوب"] = work["المندوب"].astype(str).str.strip()
        work = work[
            work["المندوب"].ne("") & work["المندوب"].str.lower().ne("nan")
        ].copy()
        work["رقم الوصل"] = range(1, len(work) + 1)
        if work.empty:
            return None, None, "لم توجد وصولات صالحة في الملف."
        return work, driver_col, None

    work = df[[driver_col, receipt_col]].copy()
    work.columns = ["المندوب", "رقم الوصل"]
    work["المندوب"] = work["المندوب"].astype(str).str.strip()
    work["رقم الوصل"] = work["رقم الوصل"].astype(str).str.strip()
    work = work[
        (work["المندوب"].ne("")) &
        (work["المندوب"].str.lower().ne("nan")) &
        (work["رقم الوصل"].ne("")) &
        (work["رقم الوصل"].str.lower().ne("nan"))
    ].copy()
    if work.empty:
        return None, None, "لم توجد وصولات صالحة في الملف."
    return work, driver_col, None

def accounting_build_summary(rows):
    grouped = rows.groupby("المندوب", sort=True).size().reset_index(name="عدد الطلبات")
    assignments = st.session_state.accounting_assignments
    rates = st.session_state.accounting_rates
    grouped["القسم"] = grouped["المندوب"].map(lambda n: assignments.get(n, "مركز"))
    grouped["التسعيرة"] = grouped["القسم"].map(lambda s: int(rates.get(s, 0)))
    grouped["المبلغ"] = grouped["عدد الطلبات"] * grouped["التسعيرة"]
    return grouped[["المندوب", "القسم", "عدد الطلبات", "التسعيرة", "المبلغ"]]

def accounting_pdf_bytes(summary_df):
    if not REPORTLAB_AVAILABLE:
        return None

    import urllib.request
    import tempfile

    # ── Arabic font resolution ──────────────────────────────────────────────────
    # Priority: well-known system paths → download Amiri (open Arabic TTF) at runtime
    font_name = None

    system_candidates = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in system_candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ArabicUI", path))
                font_name = "ArabicUI"
                break
            except Exception:
                continue

    # Download Amiri (a high-quality open Arabic font) if nothing was found
    if not font_name:
        try:
            amiri_url = (
                "https://github.com/alif-type/amiri/raw/main/sources/Amiri-Regular.ttf"
            )
            tmp_dir = tempfile.gettempdir()
            amiri_path = os.path.join(tmp_dir, "Amiri-Regular.ttf")
            if not os.path.exists(amiri_path):
                urllib.request.urlretrieve(amiri_url, amiri_path)
            pdfmetrics.registerFont(TTFont("ArabicUI", amiri_path))
            font_name = "ArabicUI"
        except Exception:
            font_name = None  # will fall back below

    # Last resort: use a built-in reportlab font (no Arabic, but won't crash)
    if not font_name:
        font_name = "Helvetica"

    # ── Arabic shaping helper ──────────────────────────────────────────────────
    # reportlab doesn't do RTL/Arabic shaping on its own.
    # arabic_reshaper + python-bidi produce correctly shaped, right-to-left text.
    def _ar(text: str) -> str:
        """Shape and reverse Arabic text for correct PDF rendering."""
        try:
            # pyrefly: ignore [missing-import]
            import arabic_reshaper
            # pyrefly: ignore [missing-import]
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(str(text)))
        except ImportError:
            return str(text)

def accounting_pdf_bytes(summary_df, mode="per_driver", driver_filter=None, report_date=None, company_name=None):
    """
    mode:
      'per_driver'   — page per driver (original)
      'single'       — one specific driver only
      'all_one_page' — all drivers in a single summary table on one page
    """
    if not REPORTLAB_AVAILABLE:
        return None

    import urllib.request
    import tempfile
    import glob

    # ── Arabic shaping ─────────────────────────────────────────────────────────
    def _ar(text: str) -> str:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(str(text)))
        except Exception:
            return str(text)

    # ── Font resolution ────────────────────────────────────────────────────────
    font_name = None
    _FONT_KEY = "ArabicUI"
    try:
        from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames
        if _FONT_KEY in getRegisteredFontNames():
            font_name = _FONT_KEY
    except Exception:
        pass

    if not font_name:
        for pattern in [
            "/usr/share/fonts/truetype/noto/NotoNaskhArabic*.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic*.ttf",
            "/usr/share/fonts/truetype/noto/Noto*Arabic*.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/tahoma.ttf",
        ]:
            for path in glob.glob(pattern):
                try:
                    pdfmetrics.registerFont(TTFont(_FONT_KEY, path))
                    font_name = _FONT_KEY
                    break
                except Exception:
                    continue
            if font_name:
                break

    if not font_name:
        tmp_path = os.path.join(tempfile.gettempdir(), "Amiri-Regular.ttf")
        for url in [
            "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
            "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/amiri/Amiri-Regular.ttf",
        ]:
            try:
                if not os.path.exists(tmp_path):
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        with open(tmp_path, "wb") as f:
                            f.write(resp.read())
                pdfmetrics.registerFont(TTFont(_FONT_KEY, tmp_path))
                font_name = _FONT_KEY
                break
            except Exception:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass

    if not font_name:
        font_name = "Helvetica"

    # ── Shared styles ──────────────────────────────────────────────────────────
    output = BytesIO()
    doc = SimpleDocTemplate(
        output, pagesize=A4,
        rightMargin=40, leftMargin=40, topMargin=44, bottomMargin=40
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ArTitle", parent=styles["Title"], fontName=font_name,
        fontSize=16, leading=22, alignment=1, spaceAfter=6
    )
    sub_style = ParagraphStyle(
        "ArSub", parent=styles["Normal"], fontName=font_name,
        fontSize=10, leading=14, alignment=1, textColor=colors.HexColor("#667085"),
        spaceAfter=14
    )
    body_style = ParagraphStyle(
        "ArBody", parent=styles["BodyText"], fontName=font_name,
        fontSize=11, leading=17, alignment=1
    )
    small_style = ParagraphStyle(
        "ArSmall", parent=body_style, fontSize=8, leading=12,
        textColor=colors.HexColor("#667085")
    )

    date_str = report_date.strftime("%Y/%m/%d") if report_date else date.today().strftime("%Y/%m/%d")
    comp_suffix = f" ({company_name.strip()})" if company_name and str(company_name).strip() else ""
    story = []

    def _tbl_style(header_color="#0f766e"):
        return TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), font_name),
            ("FONTSIZE",      (0, 0), (-1, -1), 10),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND",    (0, 0), (-1,  0), colors.HexColor(header_color)),
            ("TEXTCOLOR",     (0, 0), (-1,  0), colors.white),
            ("FONTSIZE",      (0, 0), (-1,  0), 11),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#dfe7ef")),
            ("BACKGROUND",    (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
                [colors.HexColor("#f8fafc"), colors.HexColor("#ffffff")]),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])

    # ── Mode: all on one page ──────────────────────────────────────────────────
    if mode == "all_one_page":
        from reportlab.platypus import KeepTogether

        # A4 usable height ≈ 842 - 44 - 40 = 758 pt
        # Title + subtitle ≈ 60pt, footer ≈ 20pt → available for table ≈ 678pt
        n_data_rows = len(summary_df)          # driver rows (no header/total)
        n_rows_total = n_data_rows + 2          # + header + total

        # Dynamically pick font & padding so everything fits in ~678 pt
        if n_rows_total <= 18:
            row_fs, row_pad = 10, 7
        elif n_rows_total <= 28:
            row_fs, row_pad = 9, 5
        elif n_rows_total <= 40:
            row_fs, row_pad = 8, 4
        else:
            row_fs, row_pad = 7, 3

        header = [_ar(c) for c in ["المندوب", "القسم", "عدد الطلبات", "التسعيرة", "المبلغ (د.ع)"]]
        rows_data = [header]
        for _, row in summary_df.iterrows():
            rows_data.append([
                _ar(str(row["المندوب"])),
                _ar(str(row["القسم"])),
                f"{int(row['عدد الطلبات']):,}",
                f"{int(row['التسعيرة']):,}",
                f"{int(row['المبلغ']):,}",
            ])
        # totals row
        rows_data.append([
            _ar("الإجمالي"), "",
            f"{int(summary_df['عدد الطلبات'].sum()):,}",
            "",
            f"{int(summary_df['المبلغ'].sum()):,}",
        ])

        total_idx = len(rows_data) - 1
        tbl = Table(rows_data, colWidths=[130, 65, 80, 80, 90], hAlign="CENTER")
        ts = TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), font_name),
            ("FONTSIZE",      (0, 0), (-1, -1), row_fs),
            ("FONTSIZE",      (0, 0), (-1,  0), row_fs + 1),   # header slightly bigger
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND",    (0, 0), (-1,  0), colors.HexColor("#0f766e")),
            ("TEXTCOLOR",     (0, 0), (-1,  0), colors.white),
            ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe7ef")),
            ("BACKGROUND",    (0, 1), (-1, total_idx - 1), colors.HexColor("#f8fafc")),
            ("ROWBACKGROUNDS",(0, 1), (-1, total_idx - 1),
                [colors.HexColor("#f8fafc"), colors.HexColor("#ffffff")]),
            ("TOPPADDING",    (0, 0), (-1, -1), row_pad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), row_pad),
            # totals row styling
            ("BACKGROUND",    (0, total_idx), (-1, total_idx), colors.HexColor("#ccfbf1")),
            ("TEXTCOLOR",     (0, total_idx), (-1, total_idx), colors.HexColor("#0f766e")),
            ("FONTNAME",      (0, total_idx), (-1, total_idx), font_name),
        ])
        tbl.setStyle(ts)

        block = [
            Paragraph(_ar(f"كشف محاسبة المندوبين{comp_suffix}"), title_style),
            Paragraph(_ar(f"تاريخ الكشف: {date_str}"), sub_style),
            tbl,
            Spacer(1, 10),
            Paragraph(_ar("نظام بيانات المندوبين"), small_style),
        ]
        story.append(KeepTogether(block))

    # ── Mode: single driver ────────────────────────────────────────────────────
    elif mode == "single" and driver_filter:
        df_f = summary_df[summary_df["المندوب"] == driver_filter]
        for idx, row in df_f.reset_index(drop=True).iterrows():
            story.append(Paragraph(_ar(f"كشف محاسبة المندوب{comp_suffix}"), title_style))
            story.append(Paragraph(_ar(f"تاريخ الكشف: {date_str}"), sub_style))
            story.append(Paragraph(_ar(f"المندوب: {row['المندوب']}"), body_style))
            story.append(Paragraph(_ar(f"القسم: {row['القسم']}"), body_style))
            story.append(Spacer(1, 10))
            data = [
                [_ar("البيان"), _ar("القيمة")],
                [_ar("عدد الطلبات"), f"{int(row['عدد الطلبات']):,}"],
                [_ar("تسعيرة الطلب"), f"{int(row['التسعيرة']):,} د.ع"],
                [_ar("المبلغ المستحق"), f"{int(row['المبلغ']):,} د.ع"],
            ]
            tbl = Table(data, colWidths=[230, 230], hAlign="CENTER")
            tbl.setStyle(_tbl_style())
            story.append(tbl)
            story.append(Spacer(1, 20))
            story.append(Paragraph(_ar("نظام بيانات المندوبين"), small_style))

    # ── Mode: per_driver (original — page per driver) ──────────────────────────
    else:
        for idx, row in summary_df.reset_index(drop=True).iterrows():
            story.append(Paragraph(_ar(f"كشف محاسبة المندوب{comp_suffix}"), title_style))
            story.append(Paragraph(_ar(f"تاريخ الكشف: {date_str}"), sub_style))
            story.append(Paragraph(_ar(f"المندوب: {row['المندوب']}"), body_style))
            story.append(Paragraph(_ar(f"القسم: {row['القسم']}"), body_style))
            story.append(Spacer(1, 10))
            data = [
                [_ar("البيان"), _ar("القيمة")],
                [_ar("عدد الطلبات"), f"{int(row['عدد الطلبات']):,}"],
                [_ar("تسعيرة الطلب"), f"{int(row['التسعيرة']):,} د.ع"],
                [_ar("المبلغ المستحق"), f"{int(row['المبلغ']):,} د.ع"],
            ]
            tbl = Table(data, colWidths=[230, 230], hAlign="CENTER")
            tbl.setStyle(_tbl_style())
            story.append(tbl)
            story.append(Spacer(1, 20))
            story.append(Paragraph(_ar("نظام بيانات المندوبين"), small_style))
            if idx < len(summary_df) - 1:
                story.append(PageBreak())

    doc.build(story)
    return output.getvalue()

def render_accounting_page():
    st.markdown(
        "<div class='section-title'><i class='pi pi-calculator'></i><span>محاسبة المندوبين</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='accounting-tabs-marker' aria-hidden='true'></span>",
        unsafe_allow_html=True,
    )

    if st.button("العودة إلى الصفحة الرئيسية", key="accounting_back_home"):
        st.session_state.current_page = "home"
        st.rerun()

    tab_upload, tab_assign, tab_rates, tab_report, tab_profit = st.tabs(
        ["كشف Excel", "تقسيم المندوبين", "التسعيرات", "المحاسبة والطباعة", "الأرباح"]
    )

    with tab_upload:
        uploaded = st.file_uploader(
            "ارفع كشف Excel المحاسبة",
            type=["xlsx", "xls", "csv"],
            key="accounting_excel",
            help="يجب أن يحتوي الملف على اسم المندوب ورقم الوصل/الوصول.",
        )
        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                rows, _, error = accounting_extract_rows(df)
                if error:
                    st.error(error)
                else:
                    st.session_state.accounting_rows = rows
                    # Initialize unseen drivers with the default section.
                    for name in rows["المندوب"].drop_duplicates():
                        st.session_state.accounting_assignments.setdefault(name, "مركز")
                    st.success(
                        f"تم تحميل الكشف: {len(rows):,} وصولات و"
                        f" {rows['المندوب'].nunique():,} مندوب."
                    )
                    st.dataframe(rows.head(30), use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error(f"تعذر قراءة الملف: {exc}")

        if st.session_state.accounting_rows is not None:
            rows = st.session_state.accounting_rows
            c1, c2, c3 = st.columns(3)
            c1.metric("المندوبون", f"{rows['المندوب'].nunique():,}")
            c2.metric("الوصولات", f"{len(rows):,}")
            c3.metric("مركز / قضاء", f"{sum(1 for v in st.session_state.accounting_assignments.values() if v == 'مركز')} / {sum(1 for v in st.session_state.accounting_assignments.values() if v == 'قضاء')}")

    with tab_assign:
        if st.session_state.accounting_rows is None:
            st.info("ارفع كشف Excel أولًا.")
        else:
            names = sorted(st.session_state.accounting_rows["المندوب"].drop_duplicates().tolist())
            st.markdown("### تحديد قسم كل مندوب")
            changed = False
            for i, name in enumerate(names):
                cols = st.columns([3, 1.3])
                with cols[0]:
                    st.write(name)
                with cols[1]:
                    current = st.session_state.accounting_assignments.get(name, "مركز")
                    new_section = st.selectbox(
                        "القسم", ["مركز", "قضاء"],
                        index=0 if current == "مركز" else 1,
                        key=f"accounting_section_{i}_{hash(name)}",
                        label_visibility="collapsed",
                    )
                    if new_section != current:
                        st.session_state.accounting_assignments[name] = new_section
                        changed = True
            if st.button("💾 حفظ تقسيم المندوبين", type="primary", use_container_width=True):
                st.success("تم حفظ تقسيم المندوبين لهذا النظام. ويمكن تغييره لاحقًا.")
                st.rerun()

    with tab_rates:
        st.markdown("### تسعيرة الأقسام")
        rate_cols = st.columns(2)
        with rate_cols[0]:
            center_rate = st.number_input(
                "تسعيرة المركز (د.ع)", min_value=0, step=500,
                value=int(st.session_state.accounting_rates.get("مركز", 2000)),
                key="accounting_center_rate",
            )
        with rate_cols[1]:
            district_rate = st.number_input(
                "تسعيرة القضاء (د.ع)", min_value=0, step=500,
                value=int(st.session_state.accounting_rates.get("قضاء", 3000)),
                key="accounting_district_rate",
            )
        if st.button("💾 حفظ التسعيرات", key="save_accounting_rates", type="primary"):
            st.session_state.accounting_rates = {
                "مركز": int(center_rate),
                "قضاء": int(district_rate),
            }
            st.success("تم حفظ التسعيرات.")
            st.rerun()

    with tab_report:
        if st.session_state.accounting_rows is None:
            st.info("ارفع كشف Excel أولًا.")
        else:
            summary = accounting_build_summary(st.session_state.accounting_rows)

            # ── جدول الملخص ────────────────────────────────────────────────────
            st.dataframe(
                summary.style.format({
                    "عدد الطلبات": "{:,.0f}",
                    "التسعيرة":    "{:,.0f}",
                    "المبلغ":      "{:,.0f}",
                }),
                use_container_width=True,
                hide_index=True,
            )
            total_orders = int(summary["عدد الطلبات"].sum())
            total_amount = int(summary["المبلغ"].sum())
            c1, c2 = st.columns(2)
            c1.metric("إجمالي الطلبات", f"{total_orders:,}")
            c2.metric("الإجمالي المستحق", f"{total_amount:,} د.ع")

            st.divider()

            if not REPORTLAB_AVAILABLE:
                st.warning("ميزة PDF تحتاج حزمة reportlab. أضف reportlab إلى requirements.txt ثم أعد النشر.")
            else:
                # ── تاريخ الكشف واسم الشركة ─────────────────────────────────────
                meta_col1, meta_col2 = st.columns(2)
                with meta_col1:
                    rpt_date = st.date_input(
                        "📅 تاريخ الكشف",
                        value=date.today(),
                        key="accounting_report_date",
                    )
                with meta_col2:
                    company_name = st.text_input(
                        "🏢 اسم الشركة (اختياري)",
                        value="",
                        placeholder="مثال: شركة الرافدين",
                        key="accounting_company_name",
                        help="يظهر بجانب اسم الكشف بين قوسين: كشف محاسبة المندوبين (اسم الشركة)",
                    )

                comp_file_part = f"_{company_name.strip().replace(' ', '_')}" if company_name and company_name.strip() else ""

                st.markdown("#### خيارات الطباعة")
                pdf_col1, pdf_col2 = st.columns(2)

                # ── خيار 1: كشف لمندوب محدد ────────────────────────────────────
                with pdf_col1:
                    st.markdown("**📄 كشف مندوب محدد**")
                    driver_names = sorted(summary["المندوب"].tolist())
                    selected_driver = st.selectbox(
                        "اختر المندوب",
                        options=driver_names,
                        key="accounting_pdf_driver",
                        label_visibility="collapsed",
                    )
                    pdf_single = accounting_pdf_bytes(
                        summary,
                        mode="single",
                        driver_filter=selected_driver,
                        report_date=rpt_date,
                        company_name=company_name,
                    )
                    if pdf_single:
                        safe_name = selected_driver.replace(" ", "_")[:30]
                        st.download_button(
                            f"🖨️ طباعة كشف {selected_driver}",
                            data=pdf_single,
                            file_name=f"كشف_{safe_name}{comp_file_part}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            type="primary",
                            key="dl_single_driver",
                        )

                # ── خيار 2: كشف شامل في ورقة واحدة ────────────────────────────
                with pdf_col2:
                    st.markdown("**📋 كشف شامل (ورقة واحدة)**")
                    st.caption("جميع المندوبين في جدول واحد مع الإجمالي")
                    pdf_all = accounting_pdf_bytes(
                        summary,
                        mode="all_one_page",
                        report_date=rpt_date,
                        company_name=company_name,
                    )
                    if pdf_all:
                        st.download_button(
                            "🖨️ طباعة الكشف الشامل",
                            data=pdf_all,
                            file_name=f"كشف_شامل{comp_file_part}_{rpt_date.strftime('%Y-%m-%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            type="secondary",
                            key="dl_all_one_page",
                        )

    with tab_profit:
        st.markdown(
            """<div class="profit-intro">
                <div class="profit-intro-icon" aria-hidden="true">د.ع</div>
                <div>
                    <h3>ملخص الأرباح</h3>
                    <p>أدخل الإيراد والمصاريف الإضافية، وستُخصم أجور المندوبين تلقائيًا من كشف المحاسبة المحمّل.</p>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        if st.session_state.accounting_rows is None:
            st.info("ارفع كشف المحاسبة من تبويب «كشف Excel» أولًا لاحتساب أجور المندوبين.")
        else:
            profit_summary = accounting_build_summary(st.session_state.accounting_rows)
            driver_wages = int(profit_summary["المبلغ"].sum())

            revenue_col, transport_col, fines_col = st.columns(3)
            with revenue_col:
                gross_revenue = st.number_input(
                    "المبلغ الكلي للإيرادات (د.ع)",
                    min_value=0,
                    value=0,
                    step=10000,
                    key="profit_gross_revenue",
                    help="إجمالي الإيرادات للفترة التي يغطيها كشف المحاسبة.",
                )
            with transport_col:
                vehicle_transport = st.number_input(
                    "أجور نقل السيارة (د.ع)",
                    min_value=0,
                    value=0,
                    step=1000,
                    key="profit_vehicle_transport",
                )
            with fines_col:
                fines = st.number_input(
                    "الغرامات (د.ع)",
                    min_value=0,
                    value=0,
                    step=1000,
                    key="profit_fines",
                )

            total_deductions = driver_wages + int(vehicle_transport) + int(fines)
            net_profit = int(gross_revenue) - total_deductions
            profit_margin = (
                net_profit / int(gross_revenue) * 100
                if gross_revenue
                else 0.0
            )

            result_class = "profit-result is-negative" if net_profit < 0 else "profit-result"
            st.markdown(
                f"""<div class="{result_class}">
                    <div class="profit-result-label">صافي الأرباح</div>
                    <div class="profit-result-value">{net_profit:,.0f} د.ع</div>
                </div>""",
                unsafe_allow_html=True,
            )

            metric_cols = st.columns(4)
            metric_cols[0].metric("الإيرادات الكلية", f"{int(gross_revenue):,} د.ع")
            metric_cols[1].metric("أجور المندوبين", f"{driver_wages:,} د.ع")
            metric_cols[2].metric(
                "النقل والغرامات",
                f"{int(vehicle_transport) + int(fines):,} د.ع",
            )
            metric_cols[3].metric("هامش الربح", f"{profit_margin:.1f}%")

            st.caption(
                f"احتُسبت أجور {len(profit_summary):,} مندوبًا حسب الأقسام والتسعيرات الحالية."
            )
            breakdown = pd.DataFrame(
                [
                    {"البيان": "المبلغ الكلي للإيرادات", "القيمة (د.ع)": int(gross_revenue)},
                    {"البيان": "أجور المندوبين", "القيمة (د.ع)": -driver_wages},
                    {"البيان": "أجور نقل السيارة", "القيمة (د.ع)": -int(vehicle_transport)},
                    {"البيان": "الغرامات", "القيمة (د.ع)": -int(fines)},
                    {"البيان": "صافي الأرباح", "القيمة (د.ع)": net_profit},
                ]
            )
            st.dataframe(
                breakdown.style.format({"القيمة (د.ع)": "{:,.0f}"}),
                use_container_width=True,
                hide_index=True,
            )
            if REPORTLAB_AVAILABLE:
                report_meta_cols = st.columns(2)
                with report_meta_cols[0]:
                    profit_report_date = st.date_input(
                        "تاريخ تقرير الأرباح",
                        value=st.session_state.get("accounting_report_date", date.today()),
                        key="profit_report_date",
                    )
                with report_meta_cols[1]:
                    profit_company_name = st.text_input(
                        "اسم الشركة في التقرير (اختياري)",
                        value=st.session_state.get("accounting_company_name", ""),
                        key="profit_company_name",
                    )

                from profit_report import profit_report_pdf_bytes

                profit_pdf = profit_report_pdf_bytes(
                    profit_summary,
                    gross_revenue,
                    vehicle_transport,
                    fines,
                    profit_report_date,
                    profit_company_name,
                )
                st.download_button(
                    "📄 تنزيل تقرير الأرباح التفصيلي PDF (A4)",
                    data=profit_pdf,
                    file_name=f"تقرير_الأرباح_{profit_report_date.strftime('%Y-%m-%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                    key="download_profit_report",
                )
            else:
                st.warning(
                    "تنزيل تقرير PDF غير متاح حاليًا؛ تأكد من تثبيت حزم reportlab و arabic-reshaper و python-bidi."
                )
            if net_profit < 0:
                st.warning("المصاريف أعلى من الإيرادات؛ النتيجة الحالية تمثل صافي خسارة.")
            elif gross_revenue == 0:
                st.info("أدخل المبلغ الكلي للإيرادات لاحتساب هامش الربح.")


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

            // محاسبة المندوبين: أيقونة آلة حاسبة داخل شارة متناسقة مع الشريط.
            var accountingBtn = parentDoc.querySelector('.st-key-topbar_accounting button');
            if (accountingBtn && !accountingBtn.querySelector('.accounting-button-icon')) {
                accountingBtn.innerHTML =
                    '<span class="accounting-button-icon" aria-hidden="true">' +
                    '<i class="pi pi-calculator"></i></span>' +
                    '<span class="accounting-button-label">المحاسبة</span>';
                accountingBtn.setAttribute('aria-label', 'محاسبة المندوبين');
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
            <span class='topbar-avatar'>{html_escape(avatar)}</span>
            <span class='topbar-user-text'>
                <span class='topbar-user-name'>{html_escape(user_name)}</span>
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

        # ── محاسبة المندوبين + تسجيل الخروج ─────────────────────────────────────
        with action_cols[1]:
            if st.button("المحاسبة", key="topbar_accounting", help="فتح محاسبة المندوبين", use_container_width=True):
                st.session_state.current_page = "accounting"
                st.rerun()
            with st.container(key="topbar_logout_slot"):
                if st.button("خروج", key="topbar_logout",
                             help="تسجيل الخروج", type="secondary",
                             use_container_width=True):
                    clear_authentication()
                    st.rerun()

    # ── خيارات المعالجة المرفوعة للشريط العلوي ────────────────────────────────────
    st.markdown("<div class='topbar-subdivider'></div>", unsafe_allow_html=True)

    if st.session_state.get("opt_date_filter", False):
        opt_cols = st.columns([1.3, 1.1, 1.1, 1.4, 1.4, 1.1])
        with opt_cols[0]:
            use_date_filter = st.toggle("فلترة التاريخ", key="opt_date_filter")
        with opt_cols[1]:
            start_date = st.date_input("من", value=date.today() - timedelta(days=30), key="opt_date_from")
        with opt_cols[2]:
            end_date = st.date_input("إلى", value=date.today(), key="opt_date_to")
        with opt_cols[3]:
            merge_mode = st.toggle("دمج كل الحالات معاً", key="opt_merge_mode")
        with opt_cols[4]:
            whatsapp_mode = st.toggle("مع كود البطاقة", key="opt_whatsapp_mode", help="مخرجات كود البطاقة والتاريخ لكل طلب مع اسم المندوب في الأسفل")
        with opt_cols[5]:
            if st.session_state.current_role == "admin":
                if st.button("مسح البيانات", key="opt_clear_all",
                             help="مسح جميع الجداول والبيانات المرفوعة", type="secondary",
                             use_container_width=True):
                    clear_uploaded_data()
    else:
        opt_cols = st.columns([1.3, 1.6, 1.6, 3.5])
        with opt_cols[0]:
            use_date_filter = st.toggle("فلترة التاريخ", value=False, key="opt_date_filter")
            start_date = end_date = None
        with opt_cols[1]:
            merge_mode = st.toggle("دمج كل الحالات معاً", value=False, key="opt_merge_mode")
        with opt_cols[2]:
            whatsapp_mode = st.toggle("مع كود البطاقة", value=False, key="opt_whatsapp_mode", help="مخرجات كود البطاقة والتاريخ لكل طلب مع اسم المندوب في الأسفل")
        with opt_cols[3]:
            if st.session_state.current_role == "admin":
                if st.button("مسح البيانات", key="opt_clear_all",
                             help="مسح جميع الجداول والبيانات المرفوعة", type="secondary",
                             use_container_width=False):
                    clear_uploaded_data()



# ─── صفحة محاسبة المندوبين ─────────────────────────────────────────────────────
if st.session_state.current_page == "accounting":
    render_accounting_page()
    st.markdown("<div class='app-footer'>نظام بيانات المندوبين Pro v2.0</div>", unsafe_allow_html=True)
    st.stop()

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
                            st.session_state[f"data_{status}"] = process_df(df, col_driver, col_code, col_date)
                            st.success(f"تم تحميل {len(df)} سطر")
            except Exception as e:
                st.error(f"خطأ: {e}")




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
        <div class="stat-value stat-orange" style="font-size:1.2rem">{html_escape(str(top_driver_name))}</div>
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
    st.markdown(
        "<span class='results-tabs-marker' aria-hidden='true'></span>",
        unsafe_allow_html=True,
    )
    tab_results, tab_chart, tab_table, tab_export = st.tabs([
        "النتائج النصية",
        "الرسم البياني",
        "جدول المندوبين",
        "تصدير البيانات",
    ])

    # ── Tab 1: النتائج النصية ────────────────────────────────────────────────
    with tab_results:
        _builder = build_whatsapp_output if whatsapp_mode else build_text_output

        if merge_mode:
            # دمج شامل
            combined: dict = {}
            for status, data in all_processed.items():
                if data:
                    for name, info in data.items():
                        if name not in combined:
                            combined[name] = {"codes": [], "entries": [], "count": 0}
                        combined[name]["codes"].extend(info["codes"])
                        combined[name]["entries"].extend(info.get("entries", info["codes"]))
                        combined[name]["count"] += info["count"]

            # تطبيق البحث
            if search_query:
                combined = {k: v for k, v in combined.items() if search_query.lower() in k.lower()}

            text_output = _builder(combined, "نتائج المندوبين (دمج كامل)")

            col_txt, col_btn = st.columns([5, 1])
            with col_btn:
                st.download_button("تنزيل", text_output, "results.txt", "text/plain", use_container_width=True)
                render_copy_button(text_output, "combined")
            with col_txt:
                st.markdown(
                    f'<div class="result-box">{text_as_safe_html(text_output)}</div>',
                    unsafe_allow_html=True,
                )

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
                    text_output = _builder(filtered, status)
                    col_txt, col_btn = st.columns([5, 1])
                    with col_btn:
                        st.download_button("تنزيل", text_output, f"{status}.txt", "text/plain",
                                           key=f"dl_{status}", use_container_width=True)
                        render_copy_button(text_output, f"status-{status}")
                    with col_txt:
                        st.markdown(
                            f'<div class="result-box" style="border-color:{cfg["color"]}55">'
                            f'{text_as_safe_html(text_output)}</div>',
                            unsafe_allow_html=True,
                        )

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
            _exp_builder = build_whatsapp_output if whatsapp_mode else build_text_output
            full_text = ""
            if merge_mode:
                combined_all: dict = {}
                for data in all_processed.values():
                    if data:
                        for name, info in data.items():
                            if name not in combined_all:
                                combined_all[name] = {"codes": [], "entries": [], "count": 0}
                            combined_all[name]["codes"].extend(info["codes"])
                            combined_all[name]["entries"].extend(info.get("entries", info["codes"]))
                            combined_all[name]["count"] += info["count"]
                full_text = _exp_builder(combined_all, "نتائج المندوبين")
            else:
                for status, data in all_processed.items():
                    if data:
                        full_text += _exp_builder(data, status) + "\n\n"

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
