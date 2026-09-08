# pyrefly: ignore [missing-import]
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import date, timedelta

# ─── إعدادات الصفحة ───────────────────────────────────────────────────────────
st.set_page_config(
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

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
    --p-primary-color: #0f766e;
    --p-primary-hover-color: #115e59;
    --p-primary-contrast-color: #ffffff;
    --p-border-radius-md: 6px;
    --p-border-radius-lg: 8px;
    --p-button-icon-only-width: 2.5rem;
    --p-transition-duration: 0.2s;
    --shadow: 0 12px 30px rgba(23, 32, 51, 0.08);
}

*, body, .stApp {
    font-family: var(--font-sans) !important;
    direction: rtl;
    color: var(--ink);
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
    gap: 7px;
    padding: 8px 10px;
    border: 1px solid currentColor;
    border-radius: var(--p-border-radius-md);
    background: var(--status-soft, #f8fafc);
    font-weight: 700;
    margin-bottom: 6px;
    min-height: 42px;
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
    justify-content: flex-end;
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
    width: 25px;
    height: 25px;
    border-radius: 50%;
    background: currentColor;
    color: white;
    font-size: 0.8rem;
}

@media (max-width: 768px) {
    .stat-card { height: 96px; padding: 14px 10px; }
    .stat-value { font-size: 1.6rem; }
    .stTabs [data-baseweb="tab"] { padding: 8px 10px; font-size: 0.82rem; }
    .upload-label { min-height: 38px; font-size: 0.82rem; }
    [data-testid="stFileUploader"] section { height: 104px; padding: 8px; }
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
.stApp:has(.theme-dark-marker) .stButton > button,
.stApp:has(.theme-dark-marker) [data-testid="stFileUploader"] section button {
    background: #1e293b !important;
    border-color: #475569 !important;
    color: #e5e7eb !important;
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
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<span class="theme-dark-marker"></span>' if st.session_state.dark_mode else '<span class="theme-light-marker"></span>',
    unsafe_allow_html=True,
)

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


def filter_by_date(df, col_date, start_date, end_date):
    df = df.copy()
    df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
    start = pd.Timestamp(start_date)
    end   = pd.Timestamp(end_date).replace(hour=23, minute=59, second=59)
    return df[(df[col_date] >= start) & (df[col_date] <= end)]


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

# ─── الشريط الجانبي ────────────────────────────────────────────────────────────
theme_cols = st.columns([8, 1])
with theme_cols[1]:
    theme_icon = "pi-sun" if st.session_state.dark_mode else "pi-moon"
    theme_label = "نهاري" if st.session_state.dark_mode else "ليلي"
    st.markdown(f"<div class='theme-toolbar'><i class='pi {theme_icon}'></i><span>المظهر</span></div>", unsafe_allow_html=True)
    if st.button(theme_label, use_container_width=True, type="secondary"):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

with st.container():
    st.markdown("""
    <div class="sidebar-brand">
        <div>
            <strong>لوحة التحكم</strong>
            <small>إدارة ملفات المندوبين</small>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'><i class='pi pi-sliders-h'></i><span>إعدادات المعالجة</span></div>", unsafe_allow_html=True)

    with st.container(border=True):
        control_cols = st.columns([1.35, 1.25, 2.4, 1.15])

        with control_cols[0]:
            use_date_filter = st.toggle("تفعيل فلترة التاريخ", value=False)
            if use_date_filter:
                date_cols = st.columns(2)
                with date_cols[0]:
                    start_date = st.date_input("من", value=date.today() - timedelta(days=30), label_visibility="visible")
                with date_cols[1]:
                    end_date = st.date_input("إلى", value=date.today(), label_visibility="visible")
            else:
                start_date = end_date = None

        with control_cols[1]:
            merge_mode = st.toggle("دمج كل الحالات معاً", value=False)

        with control_cols[2]:
            st.markdown("<div class='control-label'><i class='pi pi-search'></i><span>بحث في النتائج</span></div>", unsafe_allow_html=True)
            search_query = st.text_input("ابحث عن مندوب...", placeholder="اكتب اسم المندوب", label_visibility="collapsed")

        with control_cols[3]:
            st.markdown("<div class='control-label'>&nbsp;</div>", unsafe_allow_html=True)
            if st.button("مسح كل البيانات", use_container_width=True, type="secondary"):
                for key in STATUS_CONFIG:
                    st.session_state[f"data_{key}"] = None
                    st.session_state[f"raw_{key}"]  = None
                st.rerun()

# ─── رفع الملفات ──────────────────────────────────────────────────────────────
st.markdown("<div class='section-title'><i class='pi pi-upload'></i><span>رفع ملفات Excel</span></div>", unsafe_allow_html=True)
upload_cols = st.columns(4)
status_labels = list(STATUS_CONFIG.keys())

for i, status in enumerate(status_labels):
    cfg = STATUS_CONFIG[status]
    with upload_cols[i]:
        st.markdown(f"<div class='upload-label' style='color:{cfg['color']};--status-soft:{cfg['soft_color']}'><i class='pi {cfg['prime_icon']}'></i><span>{status}</span></div>", unsafe_allow_html=True)
        uploaded = st.file_uploader(f"upload_{status}", type=["xlsx", "xls"], key=f"up_{status}", label_visibility="collapsed")

        if uploaded:
            try:
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
        st.markdown("#### 💾 خيارات التصدير")
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
            st.markdown("<div class='upload-label'><i class='pi pi-file-excel'></i><span>تصدير Excel (كل الحالات)</span></div>", unsafe_allow_html=True)
            raw_frames = {s: st.session_state[f"raw_{s}"] for s in STATUS_CONFIG}
            excel_bytes = to_excel_bytes(raw_frames)
            st.download_button(
                "تنزيل Excel",
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
        <div style="font-size:1.2rem; margin-top:12px">ارفع ملفات Excel للبدء</div>
        <div style="font-size:0.9rem; margin-top:6px">يمكنك رفع ملف واحد أو أكثر من الحالات الأربع</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div class='app-footer'>نظام بيانات المندوبين Pro v2.0</div>", unsafe_allow_html=True)
