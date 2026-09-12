import customtkinter as ctk
import pandas as pd
from tkinter import filedialog, messagebox
import pyperclip
import os
import time
import threading
import sys
from datetime import datetime
from tkcalendar import DateEntry

# الإعدادات العامة للواجهة
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DriverApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("معالج طلبات المندوبين Pro - الإحصائيات والذكاء")
        self.geometry("900x900")
        self.minsize(360, 620)

        # تعيين الأيقونة
        try:
            icon_path = self.resource_path("app_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Could not load icon: {e}")

        # الخطوط
        self.font_main = ("Segoe UI", 16)
        self.font_header = ("Segoe UI", 22, "bold")
        self.font_stats = ("Segoe UI", 14, "bold")

        # الواجهة الرئيسية
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        self._compact_layout = None

        # 1. العنوان
        self.label_title = ctk.CTkLabel(self, text="📊 نظام معالجة بيانات المندوبين المتطور", font=self.font_header)
        self.label_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # 2. لوحة الإحصائيات (Dashboard)
        self.stats_frame = ctk.CTkFrame(self)
        self.stats_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.stats_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.stat_drivers = self.create_stat_box(self.stats_frame, "👥 إجمالي المندوبين", "0", 0)
        self.stat_codes = self.create_stat_box(self.stats_frame, "📦 إجمالي الأكواد", "0", 1)
        self.stat_top_driver = self.create_stat_box(self.stats_frame, "🏆 الأعلى طلباً", "---", 2)

        # 3. إعدادات التاريخ والعرض
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.settings_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.date_filter_var = ctk.BooleanVar(value=False)
        self.date_toggle = ctk.CTkSwitch(self.settings_frame, text="فلترة التاريخ", variable=self.date_filter_var, font=self.font_stats)
        self.date_toggle.grid(row=0, column=0, padx=10, pady=10)

        self.start_date_label = ctk.CTkLabel(self.settings_frame, text="من:", font=self.font_stats)
        self.start_date_label.grid(row=0, column=1, padx=5)
        # استخدام DateEntry لتحديد التاريخ بصرياً
        self.start_date_picker = DateEntry(self.settings_frame, width=12, background='darkblue',
                                         foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.start_date_picker.grid(row=0, column=2, padx=5, pady=10, sticky="ew")

        self.end_date_label = ctk.CTkLabel(self.settings_frame, text="إلى:", font=self.font_stats)
        self.end_date_label.grid(row=0, column=3, padx=5)
        self.end_date_picker = DateEntry(self.settings_frame, width=12, background='darkblue',
                                       foreground='white', borderwidth=2, date_pattern='yyyy-mm-dd')
        self.end_date_picker.grid(row=0, column=4, padx=5, pady=10, sticky="ew")

        self.merge_var = ctk.BooleanVar(value=False)
        self.merge_toggle = ctk.CTkSwitch(self.settings_frame, text="دمج بدون حالات", variable=self.merge_var, font=self.font_stats, command=self.update_combined_results)
        self.merge_toggle.grid(row=0, column=5, padx=10, pady=10)

        # 4. أزرار التحكم العليا
        self.top_controls = ctk.CTkFrame(self, fg_color="transparent")
        self.top_controls.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.top_controls.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_delivery = ctk.CTkButton(self.top_controls, text="📂 قيد التوصيل", font=self.font_main, height=45, fg_color="#2980b9", command=lambda: self.start_processing_thread("قيد التوصيل"))
        self.btn_delivery.grid(row=0, column=0, padx=5, pady=10, sticky="ew")

        self.btn_deferred = ctk.CTkButton(self.top_controls, text="📂 المؤجل", font=self.font_main, height=45, fg_color="#f39c12", command=lambda: self.start_processing_thread("المؤجل"))
        self.btn_deferred.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.btn_returned = ctk.CTkButton(self.top_controls, text="📂 الراجع", font=self.font_main, height=45, fg_color="#e74c3c", command=lambda: self.start_processing_thread("الراجع"))
        self.btn_returned.grid(row=0, column=2, padx=5, pady=10, sticky="ew")

        self.btn_delivered = ctk.CTkButton(self.top_controls, text="📂 تم التسليم", font=self.font_main, height=45, fg_color="#27ae60", command=lambda: self.start_processing_thread("تم التسليم"))
        self.btn_delivered.grid(row=0, column=3, padx=5, pady=10, sticky="ew")
        self.processing_buttons = (self.btn_delivery, self.btn_deferred, self.btn_returned, self.btn_delivered)

        self.progress_bar = ctk.CTkProgressBar(self, height=10)
        self.progress_bar.grid(row=4, column=0, padx=20, pady=5, sticky="ew")
        self.progress_bar.set(0)

        # 5. منطقة النتائج
        self.result_text = ctk.CTkTextbox(self, font=self.font_main, height=300)
        self.result_text.grid(row=5, column=0, padx=20, pady=10, sticky="nsew")

        # 6. أزرار التحكم السفلى
        self.bottom_buttons = ctk.CTkFrame(self)
        self.bottom_buttons.grid(row=6, column=0, padx=20, pady=20, sticky="ew")
        self.bottom_buttons.grid_columnconfigure((0, 1), weight=1)

        self.btn_copy = ctk.CTkButton(self.bottom_buttons, text="📋 نسخ كل النتائج", font=self.font_main, height=40, command=self.copy_to_clipboard, state="disabled")
        self.btn_copy.grid(row=0, column=0, padx=10, pady=10)

        self.btn_clear = ctk.CTkButton(self.bottom_buttons, text="🧹 مسح وتصفير", font=self.font_main, height=40, fg_color="#c0392b", hover_color="#e74c3c", command=self.clear_results)
        self.btn_clear.grid(row=0, column=1, padx=10, pady=10)

        # مخزن البيانات لكل حالة
        self.raw_dfs = {"قيد التوصيل": None, "المؤجل": None, "الراجع": None, "تم التسليم": None}
        self.status_cols = {"قيد التوصيل": (None, None), "المؤجل": (None, None), "الراجع": (None, None), "تم التسليم": (None, None)}

        self.bind("<Configure>", self._update_responsive_layout)
        self.after_idle(self._update_responsive_layout)

    def _update_responsive_layout(self, event=None):
        """Reflow controls so the window remains usable at narrow widths."""
        compact = self.winfo_width() < 760
        if compact == self._compact_layout:
            return
        self._compact_layout = compact

        for column in range(6):
            self.settings_frame.grid_columnconfigure(column, weight=0)
        for column in range(4):
            self.top_controls.grid_columnconfigure(column, weight=0)
        for column in range(3):
            self.stats_frame.grid_columnconfigure(column, weight=0)

        for widget in (
            self.date_toggle,
            self.start_date_label,
            self.start_date_picker,
            self.end_date_label,
            self.end_date_picker,
            self.merge_toggle,
        ):
            widget.grid_forget()

        buttons = (self.btn_delivery, self.btn_deferred, self.btn_returned, self.btn_delivered)
        for button in buttons:
            button.grid_forget()

        stat_widgets = (self.stat_drivers, self.stat_codes, self.stat_top_driver)
        for widget in stat_widgets:
            widget.master.grid_forget()

        if compact:
            for column in range(2):
                self.settings_frame.grid_columnconfigure(column, weight=1)
                self.top_controls.grid_columnconfigure(column, weight=1)
            self.stats_frame.grid_columnconfigure(0, weight=1)

            self.date_toggle.grid(row=0, column=0, columnspan=2, padx=10, pady=8, sticky="w")
            self.start_date_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")
            self.start_date_picker.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            self.end_date_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")
            self.end_date_picker.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
            self.merge_toggle.grid(row=3, column=0, columnspan=2, padx=10, pady=8, sticky="w")

            for index, button in enumerate(buttons):
                button.grid(row=index // 2, column=index % 2, padx=5, pady=6, sticky="ew")
            for index, widget in enumerate(stat_widgets):
                widget.master.grid(row=index, column=0, padx=10, pady=5, sticky="ew")
            self.bottom_buttons.grid_columnconfigure(0, weight=1)
            self.bottom_buttons.grid_columnconfigure(1, weight=0)
            self.btn_copy.grid_configure(row=0, column=0, sticky="ew")
            self.btn_clear.grid_configure(row=1, column=0, sticky="ew")
        else:
            for column in range(6):
                self.settings_frame.grid_columnconfigure(column, weight=1)
            for column in range(4):
                self.top_controls.grid_columnconfigure(column, weight=1)
            for column in range(3):
                self.stats_frame.grid_columnconfigure(column, weight=1)

            self.date_toggle.grid(row=0, column=0, padx=10, pady=10)
            self.start_date_label.grid(row=0, column=1, padx=5)
            self.start_date_picker.grid(row=0, column=2, padx=5, pady=10, sticky="ew")
            self.end_date_label.grid(row=0, column=3, padx=5)
            self.end_date_picker.grid(row=0, column=4, padx=5, pady=10, sticky="ew")
            self.merge_toggle.grid(row=0, column=5, padx=10, pady=10)
            for index, button in enumerate(buttons):
                button.grid(row=0, column=index, padx=5, pady=10, sticky="ew")
            for index, widget in enumerate(stat_widgets):
                widget.master.grid(row=0, column=index, padx=10, pady=10, sticky="nsew")
            self.bottom_buttons.grid_columnconfigure(0, weight=1)
            self.bottom_buttons.grid_columnconfigure(1, weight=1)
            self.btn_copy.grid_configure(row=0, column=0, sticky="")
            self.btn_clear.grid_configure(row=0, column=1, sticky="")

    def create_stat_box(self, parent, title, value, col):
        frame = ctk.CTkFrame(parent, fg_color="#2c3e50")
        frame.grid(row=0, column=col, padx=10, pady=10, sticky="nsew")
        
        lbl_title = ctk.CTkLabel(frame, text=title, font=self.font_stats, text_color="#bdc3c7")
        lbl_title.pack(pady=(5, 0))
        
        lbl_value = ctk.CTkLabel(frame, text=value, font=("Segoe UI", 20, "bold"), text_color="#3498db")
        lbl_value.pack(pady=(0, 5))
        
        return lbl_value

    def start_processing_thread(self, status_type):
        file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if file_path:
            filter_enabled = self.date_filter_var.get()
            start_date = self.start_date_picker.get_date()
            end_date = self.end_date_picker.get_date()
            for button in self.processing_buttons:
                button.configure(state="disabled")
            threading.Thread(
                target=self.process_excel,
                args=(file_path, status_type, filter_enabled, start_date, end_date),
                daemon=True,
            ).start()

    def process_excel(self, file_path, status_type, filter_enabled, start_date, end_date):
        try:
            self.after(0, lambda: (self.progress_bar.set(0), self.progress_bar.start()))
            
            df = pd.read_excel(file_path)
            
            if df.empty:
                self.after(0, lambda: messagebox.showwarning("تنبيه", f"الملف المختار لـ {status_type} فارغ!"))
                return

            # اكتشاف الأعمدة
            col_driver = None
            col_code = None
            col_date = None
            
            possible_driver_cols = ['driverName', 'اسم المندوب', 'المندوب', 'Driver', 'الاسم']
            possible_code_cols = ['code', 'كود', 'رقم الطلب', 'Code', 'id', 'رقم كود']
            possible_date_cols = ['created_at', 'التاريخ', 'تاريخ الطلب', 'date', 'تاريخ']

            for col in df.columns:
                col_str = str(col).lower()
                if any(p in col_str for p in [x.lower() for x in possible_driver_cols]):
                    col_driver = col
                if any(p in col_str for p in [x.lower() for x in possible_code_cols]):
                    col_code = col
                if any(p in col_str for p in [x.lower() for x in possible_date_cols]):
                    col_date = col

            if not col_driver:
                self.after(0, lambda: messagebox.showerror("خطأ", f"لم يتم العثور على عمود 'اسم المندوب' في ملف {status_type}."))
                return

            # فلترة التاريخ إذا كانت مفعلة
            if filter_enabled and col_date:
                try:
                    df[col_date] = pd.to_datetime(df[col_date])
                    start_val = pd.to_datetime(start_date)
                    end_val = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)
                    
                    df = df[(df[col_date] >= start_val) & (df[col_date] <= end_val)]
                except Exception as e:
                    self.after(0, lambda: messagebox.showwarning("تنبيه", f"خطأ في فلترة التاريخ في {status_type}:\n{str(e)}"))

            if df.empty:
                self.after(0, lambda: messagebox.showwarning("تنبيه", f"لا توجد بيانات تطابق التاريخ المحدد في ملف {status_type}!"))
                self.raw_dfs[status_type] = None
                return

            self.raw_dfs[status_type] = df
            self.status_cols[status_type] = (col_driver, col_code)

            # تحديث الواجهة
            self.after(0, self.update_combined_results)

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("خطأ فني", f"حدث خطأ أثناء قراءة ملف {status_type}:\n{str(e)}"))
        finally:
            self.after(0, self._finish_processing)

    def _finish_processing(self):
        self.progress_bar.stop()
        self.progress_bar.set(1)
        for button in self.processing_buttons:
            button.configure(state="normal")

    def update_combined_results(self):
        final_output = ""
        total_drivers_names = set()
        total_codes_count = 0
        
        if self.merge_var.get():
            # دمج كلي بدون حالات
            combined_data = {}
            for status, df in self.raw_dfs.items():
                if df is not None:
                    col_driver, col_code = self.status_cols[status]
                    for name, group in df.groupby(col_driver):
                        if name not in combined_data:
                            combined_data[name] = {"codes": [], "count": 0}
                        
                        if col_code:
                            codes = [str(c) for c in group[col_code].tolist() if str(c).lower() != 'nan']
                            combined_data[name]["codes"].extend(codes)
                        
                        combined_data[name]["count"] += len(group)
                        total_drivers_names.add(name)
                        total_codes_count += len(group)
            
            output_lines = ["★ نتائج المندوبين ★", "=" * 20]
            for driver_name in sorted(combined_data.keys()):
                data = combined_data[driver_name]
                output_lines.append(f"{driver_name}")
                if data["codes"]:
                    output_lines.extend(data["codes"])
                output_lines.append(f"{data['count']}")
                output_lines.append("-" * 15)
            final_output = "\n".join(output_lines)
        else:
            # نتائج مقسمة حسب الحالات
            for status in ["قيد التوصيل", "المؤجل", "الراجع", "تم التسليم"]:
                df = self.raw_dfs[status]
                if df is not None:
                    col_driver, col_code = self.status_cols[status]
                    output_lines = [f"★ {status} ★", "=" * 20]
                    for driver_name, group in df.groupby(col_driver):
                        output_lines.append(f"{driver_name}")
                        if col_code:
                            codes = [str(c) for c in group[col_code].tolist() if str(c).lower() != 'nan']
                            output_lines.extend(codes)
                        output_lines.append(f"{len(group)}")
                        output_lines.append("-" * 15)
                        total_drivers_names.add(driver_name)
                        total_codes_count += len(group)
                    final_output += "\n".join(output_lines) + "\n\n"

        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", final_output)
        
        self.stat_drivers.configure(text=str(len(total_drivers_names)))
        self.stat_codes.configure(text=str(total_codes_count))
        self.stat_top_driver.configure(text="---")
        self.btn_copy.configure(state="normal")

    def copy_to_clipboard(self):
        text = self.result_text.get("1.0", "end-1c")
        if text.strip():
            pyperclip.copy(text)
            messagebox.showinfo("نجاح", "تم نسخ النتائج إلى الحافظة 📋")

    def clear_results(self):
        self.result_text.delete("1.0", "end")
        self.btn_copy.configure(state="disabled")
        self.stat_drivers.configure(text="0")
        self.stat_codes.configure(text="0")
        self.stat_top_driver.configure(text="---")
        self.progress_bar.set(0)
        self.raw_dfs = {"قيد التوصيل": None, "المؤجل": None, "الراجع": None, "تم التسليم": None}
        self.status_cols = {"قيد التوصيل": (None, None), "المؤجل": (None, None), "الراجع": (None, None), "تم التسليم": (None, None)}

    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)

if __name__ == "__main__":
    app = DriverApp()
    app.mainloop()
