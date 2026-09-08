# pyrefly: ignore [missing-import]
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from datetime import date, timedelta

# ─── إعدادات الصفحة ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="نظام معالجة بيانات المندوبين",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS مخصص ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');

*, body, .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
}

/* خلفية التطبيق */
.stApp {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    min-height: 100vh;
}

/* شريط العنوان */
.main-header {
    background: linear-gradient(90deg, #1a1a2e, #16213e, #0f3460);
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 16px;
    padding: 20px 30px;
    margin-bottom: 24px;
    text-align: center;
    box-shadow: 0 8px 32px rgba(99, 102, 241, 0.2);
}

.main-header h1 {
    color: #fff;
    font-size: 2rem;
    font-weight: 900;
    margin: 0;
    text-shadow: 0 0 20px rgba(99, 102, 241, 0.6);
}

.main-header p {
    color: rgba(255,255,255,0.6);
    margin: 6px 0 0;
    font-size: 0.95rem;
}

/* بطاقات الإحصاء */
.stat-card {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 14px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    transition: transform 0.2s ease;
}

.stat-card:hover { transform: translateY(-3px); }

.stat-value {
    font-size: 2.2rem;
    font-weight: 900;
    margin: 6px 0;
}

.stat-label {
    color: rgba(255,255,255,0.6);
    font-size: 0.9rem;
}

.stat-blue  { color: #60a5fa; }
.stat-green { color: #34d399; }
.stat-orange{ color: #fbbf24; }
.stat-purple{ color: #a78bfa; }

/* بطاقات الحالات */
.status-card {
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 16px;
    border: 1px solid rgba(255,255,255,0.1);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 6px;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 20px;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 600;
    color: rgba(255,255,255,0.7);
    background: transparent;
    border: none;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e, #0f0c29);
    border-left: 1px solid rgba(99, 102, 241, 0.2);
}

[data-testid="stSidebar"] .stMarkdown h3 {
    color: #a78bfa;
    font-size: 1rem;
}

/* أزرار */
.stButton > button {
    border-radius: 10px;
    font-family: 'Cairo', sans-serif !important;
    font-weight: 700;
    padding: 10px 24px;
    transition: all 0.2s ease;
    border: none;
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
}

/* مربع النتائج */
.result-box {
    background: rgba(15, 12, 41, 0.7);
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 14px;
    padding: 20px;
    font-family: 'Cairo', monospace;
    white-space: pre-wrap;
    color: #e2e8f0;
    line-height: 1.8;
    max-height: 500px;
    overflow-y: auto;
    text-align: right;
    direction: rtl;
}

/* Badge الحالة */
.badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 700;
    margin: 2px;
}

.badge-delivery { background: rgba(59,130,246,0.2); color: #60a5fa; border: 1px solid #60a5fa; }
.badge-deferred { background: rgba(245,158,11,0.2); color: #fbbf24; border: 1px solid #fbbf24; }
.badge-returned { background: rgba(239,68,68,0.2);  color: #f87171; border: 1px solid #f87171; }
.badge-delivered{ background: rgba(16,185,129,0.2); color: #34d399; border: 1px solid #34d399; }

/* شريط البحث */
.stTextInput > div > div > input {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(99, 102, 241, 0.3) !important;
    border-radius: 10px !important;
    color: white !important;
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
}

/* DataFrames */
.stDataFrame {
    border-radius: 12px;
    overflow: hidden;
}

/* Divider */
hr { border-color: rgba(99, 102, 241, 0.2) !important; }

/* Metric */
[data-testid="metric-container"] {
    background: rgba(99, 102, 241, 0.1);
    border: 1px solid rgba(99, 102, 241, 0.25);
    border-radius: 12px;
    padding: 12px;
}

/* Success/Error/Warning */
.stSuccess, .stError, .stWarning, .stInfo {
    border-radius: 10px;
}

/* File uploader */
[data-testid="stFileUploader"] {
    background: rgba(99, 102, 241, 0.05);
    border: 2px dashed rgba(99, 102, 241, 0.4);
    border-radius: 14px;
    padding: 10px;
}
</style>
""", unsafe_allow_html=True)

# ─── الثوابت ──────────────────────────────────────────────────────────────────
STATUS_CONFIG = {
    "قيد التوصيل": {"icon": "🚚", "color": "#60a5fa", "badge": "badge-delivery", "emoji_badge": "🔵"},
    "المؤجل":       {"icon": "⏳", "color": "#fbbf24", "badge": "badge-deferred", "emoji_badge": "🟡"},
    "الراجع":       {"icon": "↩️", "color": "#f87171", "badge": "badge-returned",  "emoji_badge": "🔴"},
    "تم التسليم":   {"icon": "✅", "color": "#34d399", "badge": "badge-delivered", "emoji_badge": "🟢"},
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

# ─── العنوان الرئيسي ──────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>📦 نظام معالجة بيانات المندوبين</h1>
    <p>رفع ملفات Excel • تحليل ذكي • إحصائيات متقدمة • تصدير النتائج</p>
</div>
""", unsafe_allow_html=True)

# ─── الشريط الجانبي ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ إعدادات المعالجة")
    st.divider()

    use_date_filter = st.toggle("🗓️ تفعيل فلترة التاريخ", value=False)
    if use_date_filter:
        col_s, col_e = st.columns(2)
        with col_s:
            start_date = st.date_input("من", value=date.today() - timedelta(days=30), label_visibility="visible")
        with col_e:
            end_date   = st.date_input("إلى", value=date.today(), label_visibility="visible")
    else:
        start_date = end_date = None

    st.divider()
    merge_mode = st.toggle("🔗 دمج كل الحالات معاً", value=False)

    st.divider()
    st.markdown("### 🔍 بحث في النتائج")
    search_query = st.text_input("ابحث عن مندوب...", placeholder="اكتب اسم المندوب", label_visibility="collapsed")

    st.divider()
    if st.button("🧹 مسح كل البيانات", use_container_width=True, type="secondary"):
        for key in STATUS_CONFIG:
            st.session_state[f"data_{key}"] = None
            st.session_state[f"raw_{key}"]  = None
        st.rerun()

    st.divider()
    st.markdown("<div style='color:rgba(255,255,255,0.3);font-size:0.75rem;text-align:center'>نظام بيانات المندوبين Pro v2.0</div>", unsafe_allow_html=True)

# ─── رفع الملفات ──────────────────────────────────────────────────────────────
st.markdown("### 📂 رفع ملفات Excel")
upload_cols = st.columns(4)
status_labels = list(STATUS_CONFIG.keys())

for i, status in enumerate(status_labels):
    cfg = STATUS_CONFIG[status]
    with upload_cols[i]:
        st.markdown(f"<div style='color:{cfg['color']};font-weight:700;margin-bottom:6px'>{cfg['icon']} {status}</div>", unsafe_allow_html=True)
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
                            st.success(f"✅ {len(df)} سطر")
            except Exception as e:
                st.error(f"خطأ: {e}")

st.divider()

# ─── جمع البيانات المتاحة ─────────────────────────────────────────────────────
all_processed = {s: st.session_state[f"data_{s}"] for s in STATUS_CONFIG}
has_data = any(v is not None for v in all_processed.values())

# ─── لوحة الإحصائيات ──────────────────────────────────────────────────────────
st.markdown("### 📊 لوحة الإحصائيات")
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
        <div class="stat-label">👥 إجمالي المندوبين</div>
        <div class="stat-value stat-blue">{len(total_drivers)}</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[1]:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">📦 إجمالي الطلبات</div>
        <div class="stat-value stat-green">{total_codes}</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[2]:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">🏆 الأعلى طلباً</div>
        <div class="stat-value stat-orange" style="font-size:1.2rem">{top_driver_name}</div>
        <div class="stat-label">{top_driver_count if top_driver_count else ''} طلب</div>
    </div>""", unsafe_allow_html=True)

with stat_cols[3]:
    active = sum(1 for v in all_processed.values() if v is not None)
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">📋 الحالات المُحمّلة</div>
        <div class="stat-value stat-purple">{active} / 4</div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ─── النتائج والتحليلات ────────────────────────────────────────────────────────
if has_data:
    tab_results, tab_chart, tab_table, tab_export = st.tabs([
        "📋 النتائج النصية",
        "📊 الرسم البياني",
        "🗂️ جدول المندوبين",
        "💾 تصدير البيانات",
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
                st.download_button("📥 تنزيل", text_output, "results.txt", "text/plain", use_container_width=True)
                if st.button("📋 نسخ", use_container_width=True):
                    st.code(text_output, language=None)
                    st.info("انسخ النص من المربع أعلاه")
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

                with st.expander(f"{cfg['icon']} {status} — {sum(d['count'] for d in filtered.values())} طلب | {len(filtered)} مندوب", expanded=True):
                    text_output = build_text_output(filtered, status)
                    col_txt, col_btn = st.columns([5, 1])
                    with col_btn:
                        st.download_button(f"📥 تنزيل", text_output, f"{status}.txt", "text/plain",
                                           key=f"dl_{status}", use_container_width=True)
                    with col_txt:
                        st.markdown(f'<div class="result-box" style="border-color:{cfg["color"]}55">{text_output.replace(chr(10), "<br>")}</div>',
                                    unsafe_allow_html=True)

    # ── Tab 2: الرسم البياني ─────────────────────────────────────────────────
    with tab_chart:
        chart_type = st.radio("نوع الرسم", ["📊 أعمدة", "🥧 دائري", "📈 مقارنة الحالات"], horizontal=True)

        if chart_type == "📊 أعمدة":
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
                    color_continuous_scale=["#6366f1", "#8b5cf6", "#a78bfa"],
                    text="الطلبات",
                )
                fig.update_traces(textposition='outside', textfont_size=12)
                fig.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(15,12,41,0.5)',
                    font=dict(family="Cairo", color="white"),
                    title_font_size=16,
                    xaxis=dict(tickangle=-30, gridcolor='rgba(255,255,255,0.05)'),
                    yaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                    coloraxis_showscale=False,
                )
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "🥧 دائري":
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
                    font=dict(family="Cairo", color="white"),
                    title="توزيع الطلبات حسب الحالة",
                    title_font_size=16,
                    showlegend=True,
                    legend=dict(font=dict(color="white")),
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
                    plot_bgcolor='rgba(15,12,41,0.5)',
                    font=dict(family="Cairo", color="white"),
                    title_font_size=16,
                    xaxis=dict(tickangle=-30, gridcolor='rgba(255,255,255,0.05)'),
                    yaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
                    legend=dict(font=dict(color="white")),
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
                        "الحالة":   f"{cfg['icon']} {status}",
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
            st.markdown("**📄 تصدير النص الكامل**")
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
                "📥 تنزيل TXT",
                full_text,
                "drivers_results.txt",
                "text/plain",
                use_container_width=True,
                type="primary",
            )

        with exp_cols[1]:
            st.markdown("**📊 تصدير Excel (كل الحالات)**")
            raw_frames = {s: st.session_state[f"raw_{s}"] for s in STATUS_CONFIG}
            excel_bytes = to_excel_bytes(raw_frames)
            st.download_button(
                "📥 تنزيل Excel",
                excel_bytes,
                "drivers_data.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )

        with exp_cols[2]:
            st.markdown("**📋 تصدير جدول المندوبين**")
            rows_exp = []
            for status, data in all_processed.items():
                if data:
                    for name, info in data.items():
                        rows_exp.append({"المندوب": name, "الحالة": status, "عدد الطلبات": info["count"]})
            if rows_exp:
                df_exp = pd.DataFrame(rows_exp)
                csv_bytes = df_exp.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "📥 تنزيل CSV",
                    csv_bytes,
                    "drivers_summary.csv",
                    "text/csv",
                    use_container_width=True,
                    type="primary",
                )

else:
    # لا توجد بيانات بعد
    st.markdown("""
    <div style="text-align:center; padding: 60px 20px; color: rgba(255,255,255,0.4);">
        <div style="font-size:4rem">📂</div>
        <div style="font-size:1.2rem; margin-top:12px">ارفع ملفات Excel للبدء</div>
        <div style="font-size:0.9rem; margin-top:6px">يمكنك رفع ملف واحد أو أكثر من الحالات الأربع</div>
    </div>
    """, unsafe_allow_html=True)
