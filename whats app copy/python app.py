import tkinter as tk
from tkinter import ttk, font
import pyperclip
import re
from datetime import datetime

# ==================== الألوان والتصميم ====================
COLORS = {
    'bg_dark': '#0f0f1e',
    'bg_secondary': '#1a1a2e',
    'bg_card': '#16213e',
    'primary': '#667eea',
    'primary_dark': '#5568d3',
    'secondary': '#f093fb',
    'accent': '#4facfe',
    'success': '#4ade80',
    'text_primary': '#ffffff',
    'text_secondary': '#b4b4b4',
    'border': '#2d2d44',
}


# ==================== نظام الذكاء الاصطناعي للتعرف على الأعمدة ====================

def is_code_column(value):
    """فحص إذا كانت القيمة تبدو كأنها كود (رقم طويل)"""
    if not value:
        return False
    # إزالة المسافات
    clean = value.strip()
    # التحقق من أنها أرقام فقط وطويلة (أكثر من 8 أرقام)
    return clean.isdigit() and len(clean) >= 8


def is_datetime_column(value):
    """فحص إذا كانت القيمة تبدو كأنها تاريخ/وقت"""
    if not value:
        return False
    
    # أنماط التاريخ الشائعة
    datetime_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # 2025-12-23
        r'\d{2}/\d{2}/\d{4}',  # 23/12/2025
        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',  # 2025-12-23 10:23:45
        r'\d{2}:\d{2}:\d{2}',  # 10:23:45
        r'\d{2}:\d{2}',  # 10:23
    ]
    
    for pattern in datetime_patterns:
        if re.search(pattern, value):
            return True
    return False


def is_name_column(value):
    """فحص إذا كانت القيمة تبدو كأنها اسم (نص عربي أو إنجليزي)"""
    if not value:
        return False
    
    clean = value.strip()
    # التحقق من وجود حروف (عربي أو إنجليزي)
    has_arabic = bool(re.search(r'[\u0600-\u06FF]', clean))
    has_english = bool(re.search(r'[a-zA-Z]', clean))
    has_spaces = ' ' in clean or '-' in clean
    
    # الأسماء عادة تحتوي على حروف ومسافات أو شرطات
    return (has_arabic or has_english) and (has_spaces or len(clean.split()) > 1 or '-' in clean)


def detect_column_type(sample_values):
    """
    تحليل عينة من القيم لتحديد نوع العمود
    Returns: 'code', 'name', 'datetime', or 'unknown'
    """
    if not sample_values:
        return 'unknown'
    
    # تصفية القيم الفارغة
    sample_values = [v for v in sample_values if v and v.strip()]
    if not sample_values:
        return 'unknown'
    
    # حساب النتائج لكل نوع
    code_score = sum(1 for v in sample_values if is_code_column(v))
    datetime_score = sum(1 for v in sample_values if is_datetime_column(v))
    name_score = sum(1 for v in sample_values if is_name_column(v))
    
    total = len(sample_values)
    
    # إذا كانت 70% أو أكثر من العينات تطابق نوع معين
    threshold = 0.7
    
    if code_score / total >= threshold:
        return 'code'
    elif datetime_score / total >= threshold:
        return 'datetime'
    elif name_score / total >= threshold:
        return 'name'
    else:
        return 'unknown'


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
        parts = line.split("\t")
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


def extract_date_only(datetime_str):
    """استخراج التاريخ فقط وحذف الوقت"""
    if not datetime_str:
        return datetime_str
    
    # البحث عن نمط التاريخ (YYYY-MM-DD)
    match = re.search(r'\d{4}-\d{2}-\d{2}', datetime_str)
    if match:
        return match.group(0)
    
    # إذا لم نجد التاريخ، نرجع النص كما هو
    return datetime_str

def convert_text():
    text = input_text.get("1.0", tk.END).strip()
    separator = sep_entry.get()

    if not text:
        status_label.config(text="⚠️ الرجاء إدخال بيانات!", foreground=COLORS['secondary'])
        return

    lines = text.splitlines()
    
    # 🤖 الكشف التلقائي الذكي عن أنواع الأعمدة
    column_types = auto_detect_columns(lines)
    
    # تحديد مواقع الأعمدة بناءً على النوع
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
    
    # عرض معلومات الكشف في شريط الحالة
    detected_info = f"🤖 تم الكشف: "
    if code_col is not None:
        detected_info += f"كود[{code_col}] "
    if name_col is not None:
        detected_info += f"اسم[{name_col}] "
    if datetime_col is not None:
        detected_info += f"تاريخ[{datetime_col}]"
    
    # تجميع البيانات حسب الاسم
    grouped_data = {}
    
    for line in lines:
        parts = line.split("\t")  # Excel يفصل الأعمدة بـ TAB
        parts = [p.strip() for p in parts]
        
        if not parts or len(parts) < 2:
            continue
        
        # استخراج القيم بناءً على الأعمدة المحددة
        name = parts[name_col] if name_col < len(parts) else ""
        
        if not name:
            continue
        
        # بناء الإدخال
        entry_parts = []
        
        # إضافة الكود إذا وجد
        if code_col is not None and code_col < len(parts):
            entry_parts.append(parts[code_col])
        
        # إضافة التاريخ فقط (بدون الوقت) إذا وجد
        if datetime_col is not None and datetime_col < len(parts):
            date_only = extract_date_only(parts[datetime_col])
            entry_parts.append(date_only)
        
        # إذا لم نجد أعمدة محددة، نضيف كل شيء ما عدا الاسم
        if not entry_parts:
            entry_parts = [p for i, p in enumerate(parts) if i != name_col and p]
        
        # إضافة للمجموعة حسب الاسم
        if name not in grouped_data:
            grouped_data[name] = []
        if entry_parts:
            grouped_data[name].append(entry_parts)
    
    # بناء النتيجة
    output_lines = []
    for i, (name, entries) in enumerate(grouped_data.items()):
        # كتابة جميع الأكواد والأوقات وحساب أطول سطر
        max_data_length = 0
        for entry in entries:
            joined = separator.join(entry)
            output_lines.append(joined)
            max_data_length = max(max_data_length, len(joined))
        
        # كتابة الاسم في الأسفل
        output_lines.append(name)
        
        # خط فاصل صغير ومرتب
        if i < len(grouped_data) - 1:
            output_lines.append("─" * 15)
        else:
            output_lines.append("")  # سطر فارغ في النهاية فقط
    
    result = "\n".join(output_lines)

    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, result)
    
    total_names = len(grouped_data)
    total_entries = sum(len(entries) for entries in grouped_data.values())
    status_label.config(text=f"✓ {detected_info} | {total_names} شخص، {total_entries} سطر", foreground=COLORS['success'])


def copy_to_clipboard():
    content = output_text.get("1.0", tk.END).strip()
    if content:
        pyperclip.copy(content)
        copy_btn.config(text="✓ تم النسخ!", bg=COLORS['success'])
        root.after(2000, lambda: copy_btn.config(text="📋 نسخ النتيجة", bg=COLORS['accent']))
        status_label.config(text="✓ تم نسخ النص إلى الحافظة!", foreground=COLORS['success'])
    else:
        status_label.config(text="⚠️ لا يوجد نص للنسخ!", foreground=COLORS['secondary'])


def clear_input():
    input_text.delete("1.0", tk.END)
    output_text.delete("1.0", tk.END)
    status_label.config(text="🔄 جاهز للعمل", foreground=COLORS['text_secondary'])


def paste_from_clipboard():
    """لصق النص من الحافظة"""
    try:
        clipboard_text = root.clipboard_get()
        input_text.insert(tk.INSERT, clipboard_text)
        status_label.config(text="✓ تم اللصق بنجاح!", foreground=COLORS['success'])
    except:
        # إذا لم يعمل clipboard_get، نستخدم pyperclip
        try:
            clipboard_text = pyperclip.paste()
            input_text.insert(tk.INSERT, clipboard_text)
            status_label.config(text="✓ تم اللصق بنجاح!", foreground=COLORS['success'])
        except:
            status_label.config(text="⚠️ لا يوجد نص في الحافظة!", foreground=COLORS['secondary'])


def show_context_menu(event, text_widget):
    """إظهار قائمة السياق عند الضغط بالزر الأيمن"""
    context_menu = tk.Menu(root, tearoff=0, bg=COLORS['bg_card'], fg=COLORS['text_primary'],
                           activebackground=COLORS['primary'], activeforeground=COLORS['text_primary'])
    
    context_menu.add_command(label="📋 لصق (Ctrl+V)", command=lambda: paste_to_widget(text_widget))
    context_menu.add_command(label="📄 نسخ (Ctrl+C)", command=lambda: copy_from_widget(text_widget))
    context_menu.add_command(label="✂️ قص (Ctrl+X)", command=lambda: cut_from_widget(text_widget))
    context_menu.add_separator()
    context_menu.add_command(label="🔄 تحديد الكل (Ctrl+A)", command=lambda: select_all(text_widget))
    
    context_menu.tk_popup(event.x_root, event.y_root)


def paste_to_widget(widget):
    """لصق في widget محدد"""
    try:
        clipboard_text = root.clipboard_get()
        widget.insert(tk.INSERT, clipboard_text)
    except:
        try:
            clipboard_text = pyperclip.paste()
            widget.insert(tk.INSERT, clipboard_text)
        except:
            pass


def copy_from_widget(widget):
    """نسخ من widget محدد"""
    try:
        selected_text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        pyperclip.copy(selected_text)
        root.clipboard_clear()
        root.clipboard_append(selected_text)
    except:
        pass


def cut_from_widget(widget):
    """قص من widget محدد"""
    try:
        selected_text = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        pyperclip.copy(selected_text)
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except:
        pass


def select_all(widget):
    """تحديد كل النص في widget"""
    widget.tag_add(tk.SEL, "1.0", tk.END)
    widget.mark_set(tk.INSERT, "1.0")
    widget.see(tk.INSERT)
    return 'break'


def on_enter(e):
    e.widget['background'] = COLORS['primary_dark']


def on_leave(e):
    original_color = e.widget.original_bg
    e.widget['background'] = original_color


# ==================== إنشاء النافذة الرئيسية ====================
root = tk.Tk()
root.title("⚡ نسمة هوى بغداد - Excel to WhatsApp")
root.geometry("900x700")
root.configure(bg=COLORS['bg_dark'])

# منع تغيير حجم النافذة بنسب غير مناسبة
root.minsize(700, 600)

# ==================== الخطوط ====================
title_font = font.Font(family="Segoe UI", size=18, weight="bold")
header_font = font.Font(family="Segoe UI", size=11, weight="bold")
body_font = font.Font(family="Segoe UI", size=10)
text_font = font.Font(family="Consolas", size=10)

# ==================== Header ====================
header_frame = tk.Frame(root, bg=COLORS['bg_secondary'], height=80)
header_frame.pack(fill="x", pady=(0, 20))
header_frame.pack_propagate(False)

icon_label = tk.Label(
    header_frame,
    text="⚡",
    font=("Segoe UI", 32),
    bg=COLORS['bg_secondary'],
    fg=COLORS['primary']
)
icon_label.pack(side="right", padx=20)

title_label = tk.Label(
    header_frame,
    text="نسمة هوى بغداد - Excel to WhatsApp",
    font=title_font,
    bg=COLORS['bg_secondary'],
    fg=COLORS['text_primary']
)
title_label.pack(side="right", pady=20)

subtitle_label = tk.Label(
    header_frame,
    text="نص منسق جاهز للارسال واتساب",
    font=body_font,
    bg=COLORS['bg_secondary'],
    fg=COLORS['text_secondary']
)
subtitle_label.pack(side="right", padx=(0, 20))

# ==================== Container الرئيسي ====================
main_container = tk.Frame(root, bg=COLORS['bg_dark'])
main_container.pack(fill="both", expand=True, padx=30, pady=(0, 20))

# ==================== قسم الإدخال ====================
input_frame = tk.Frame(main_container, bg=COLORS['bg_dark'])
input_frame.pack(fill="both", expand=True, pady=(0, 15))

input_header = tk.Label(
    input_frame,
    text="📥 البيانات المدخلة",
    font=header_font,
    bg=COLORS['bg_dark'],
    fg=COLORS['text_primary'],
    anchor="e"
)
input_header.pack(anchor="e", pady=(0, 8))

input_text = tk.Text(
    input_frame,
    height=10,
    font=text_font,
    bg=COLORS['bg_card'],
    fg=COLORS['text_primary'],
    insertbackground=COLORS['primary'],
    relief="flat",
    borderwidth=2,
    highlightthickness=2,
    highlightbackground=COLORS['border'],
    highlightcolor=COLORS['primary'],
    padx=15,
    pady=15
)
input_text.pack(fill="both", expand=True)

# ربط اختصارات لوحة المفاتيح
input_text.bind('<Control-v>', lambda e: paste_to_widget(input_text))
input_text.bind('<Control-c>', lambda e: copy_from_widget(input_text))
input_text.bind('<Control-x>', lambda e: cut_from_widget(input_text))
input_text.bind('<Control-a>', lambda e: select_all(input_text))
# قائمة السياق بالزر الأيمن
input_text.bind('<Button-3>', lambda e: show_context_menu(e, input_text))

# ==================== قسم الإعدادات والأزرار ====================
control_frame = tk.Frame(main_container, bg=COLORS['bg_card'], height=70)
control_frame.pack(fill="x", pady=15)
control_frame.pack_propagate(False)

# Frame للفاصل
separator_frame = tk.Frame(control_frame, bg=COLORS['bg_card'])
separator_frame.pack(side="right", padx=20, pady=15)

sep_label = tk.Label(
    separator_frame,
    text="الفاصل:",
    font=header_font,
    bg=COLORS['bg_card'],
    fg=COLORS['text_secondary']
)
sep_label.pack(side="right", padx=(0, 8))

sep_entry = tk.Entry(
    separator_frame,
    font=body_font,
    bg=COLORS['bg_secondary'],
    fg=COLORS['text_primary'],
    insertbackground=COLORS['primary'],
    relief="flat",
    width=8,
    justify="center",
    borderwidth=0,
    highlightthickness=2,
    highlightbackground=COLORS['border'],
    highlightcolor=COLORS['primary']
)
sep_entry.pack(side="right")
sep_entry.insert(0, " | ")

# Frame للأزرار
buttons_frame = tk.Frame(control_frame, bg=COLORS['bg_card'])
buttons_frame.pack(side="left", padx=20, pady=15)

# زر اللصق
paste_btn = tk.Button(
    buttons_frame,
    text="📋 لصق",
    font=header_font,
    bg=COLORS['secondary'],
    fg=COLORS['text_primary'],
    relief="flat",
    borderwidth=0,
    padx=25,
    pady=10,
    cursor="hand2",
    command=paste_from_clipboard
)
paste_btn.pack(side="left", padx=5)
paste_btn.original_bg = COLORS['secondary']
paste_btn.bind("<Enter>", on_enter)
paste_btn.bind("<Leave>", on_leave)

# زر التحويل
convert_btn = tk.Button(
    buttons_frame,
    text="⚡ تحويل",
    font=header_font,
    bg=COLORS['primary'],
    fg=COLORS['text_primary'],
    relief="flat",
    borderwidth=0,
    padx=25,
    pady=10,
    cursor="hand2",
    command=convert_text
)
convert_btn.pack(side="left", padx=5)
convert_btn.original_bg = COLORS['primary']
convert_btn.bind("<Enter>", on_enter)
convert_btn.bind("<Leave>", on_leave)

# زر النسخ
copy_btn = tk.Button(
    buttons_frame,
    text="📋 نسخ النتيجة",
    font=header_font,
    bg=COLORS['accent'],
    fg=COLORS['text_primary'],
    relief="flat",
    borderwidth=0,
    padx=25,
    pady=10,
    cursor="hand2",
    command=copy_to_clipboard
)
copy_btn.pack(side="left", padx=5)
copy_btn.original_bg = COLORS['accent']
copy_btn.bind("<Enter>", on_enter)
copy_btn.bind("<Leave>", on_leave)

# زر المسح
clear_btn = tk.Button(
    buttons_frame,
    text="🗑️ مسح",
    font=header_font,
    bg=COLORS['bg_secondary'],
    fg=COLORS['text_secondary'],
    relief="flat",
    borderwidth=0,
    padx=25,
    pady=10,
    cursor="hand2",
    command=clear_input
)
clear_btn.pack(side="left", padx=5)
clear_btn.original_bg = COLORS['bg_secondary']
clear_btn.bind("<Enter>", on_enter)
clear_btn.bind("<Leave>", on_leave)

# ==================== قسم المخرجات ====================
output_frame = tk.Frame(main_container, bg=COLORS['bg_dark'])
output_frame.pack(fill="both", expand=True, pady=(0, 15))

output_header = tk.Label(
    output_frame,
    text="📤 النتيجة الجاهزة",
    font=header_font,
    bg=COLORS['bg_dark'],
    fg=COLORS['text_primary'],
    anchor="e"
)
output_header.pack(anchor="e", pady=(0, 8))

output_text = tk.Text(
    output_frame,
    height=10,
    font=text_font,
    bg=COLORS['bg_card'],
    fg=COLORS['success'],
    insertbackground=COLORS['primary'],
    relief="flat",
    borderwidth=2,
    highlightthickness=2,
    highlightbackground=COLORS['border'],
    highlightcolor=COLORS['accent'],
    padx=15,
    pady=15
)
output_text.pack(fill="both", expand=True)

# ربط اختصارات لوحة المفاتيح للمخرجات
output_text.bind('<Control-c>', lambda e: copy_from_widget(output_text))
output_text.bind('<Control-a>', lambda e: select_all(output_text))
# قائمة السياق بالزر الأيمن
output_text.bind('<Button-3>', lambda e: show_context_menu(e, output_text))

# ==================== شريط الحالة ====================
status_frame = tk.Frame(root, bg=COLORS['bg_secondary'], height=40)
status_frame.pack(fill="x", side="bottom")
status_frame.pack_propagate(False)

status_label = tk.Label(
    status_frame,
    text="🔄 جاهز للعمل",
    font=body_font,
    bg=COLORS['bg_secondary'],
    fg=COLORS['text_secondary'],
    anchor="e"
)
status_label.pack(side="right", padx=20, pady=8)

version_label = tk.Label(
    status_frame,
    text="v2.0 | Modern UI",
    font=("Segoe UI", 8),
    bg=COLORS['bg_secondary'],
    fg=COLORS['border'],
    anchor="w"
)
version_label.pack(side="left", padx=20, pady=8)

# ==================== تشغيل التطبيق ====================
root.mainloop()
