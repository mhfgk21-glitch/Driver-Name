from __future__ import annotations

import glob
import html
import os
import tempfile
import urllib.request
from datetime import date
from io import BytesIO

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from pdf_formatting import format_pdf_date


def _pdf_font_name() -> str:
    font_key = "ArabicUI"
    if font_key in pdfmetrics.getRegisteredFontNames():
        return font_key

    for pattern in (
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic*.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic*.ttf",
        "/usr/share/fonts/truetype/noto/Noto*Arabic*.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ):
        for path in glob.glob(pattern):
            try:
                pdfmetrics.registerFont(TTFont(font_key, path))
                return font_key
            except Exception:
                continue

    font_path = os.path.join(tempfile.gettempdir(), "Amiri-Regular.ttf")
    for url in (
        "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
        "https://cdn.jsdelivr.net/gh/google/fonts@main/ofl/amiri/Amiri-Regular.ttf",
    ):
        try:
            if not os.path.exists(font_path):
                request = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(request, timeout=10) as response:
                    with open(font_path, "wb") as font_file:
                        font_file.write(response.read())
            pdfmetrics.registerFont(TTFont(font_key, font_path))
            return font_key
        except Exception:
            if os.path.exists(font_path):
                try:
                    os.remove(font_path)
                except OSError:
                    pass

    raise RuntimeError("تعذر تجهيز خط عربي لتقرير الأرباح PDF.")


def _shape_arabic(value: object) -> str:
    return get_display(arabic_reshaper.reshape(str(value)))


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    shaped_text = _shape_arabic(str(value)).replace("\n", "<br/>")
    return Paragraph(html.escape(shaped_text).replace("&lt;br/&gt;", "<br/>"), style)


def profit_report_pdf_bytes(
    driver_summary,
    gross_revenue: int,
    vehicle_transport: int,
    fines: int,
    report_date: date,
    company_name: str = "",
) -> bytes:
    driver_wages = int(driver_summary["المبلغ"].sum())
    gross_revenue = int(gross_revenue)
    vehicle_transport = int(vehicle_transport)
    fines = int(fines)
    net_profit = gross_revenue - driver_wages - vehicle_transport - fines
    profit_margin = net_profit / gross_revenue * 100 if gross_revenue else 0.0

    font_name = _pdf_font_name()
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=34,
        leftMargin=34,
        topMargin=36,
        bottomMargin=36,
        title="تقرير الأرباح",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ProfitTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=26,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#115e59"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ProfitSubtitle",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=16,
    )
    section_style = ParagraphStyle(
        "ProfitSection",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0f766e"),
        spaceBefore=8,
        spaceAfter=7,
    )
    cell_style = ParagraphStyle(
        "ProfitCell",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=12,
        alignment=TA_CENTER,
    )
    driver_style = ParagraphStyle(
        "ProfitDriverCell",
        parent=cell_style,
        alignment=TA_RIGHT,
    )
    small_style = ParagraphStyle(
        "ProfitSmall",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748b"),
    )

    date_text = format_pdf_date(report_date)
    report_title = f"تقرير الأرباح{f' - {company_name.strip()}' if company_name.strip() else ''}"
    story = [
        _paragraph(report_title, title_style),
        _paragraph(f"تاريخ التقرير: {date_text}", subtitle_style),
        _paragraph("الملخص المالي", section_style),
    ]

    financial_rows = [
        [_paragraph("البيان", cell_style), _paragraph("القيمة (د.ع)", cell_style)],
        [_paragraph("الإيرادات الكلية", cell_style), _paragraph(f"{gross_revenue:,}", cell_style)],
        [_paragraph("أجور المندوبين", cell_style), _paragraph(f"- {driver_wages:,}", cell_style)],
        [_paragraph("أجور نقل السيارة", cell_style), _paragraph(f"- {vehicle_transport:,}", cell_style)],
        [_paragraph("الغرامات", cell_style), _paragraph(f"- {fines:,}", cell_style)],
        [_paragraph("إجمالي الخصومات", cell_style), _paragraph(f"- {driver_wages + vehicle_transport + fines:,}", cell_style)],
        [_paragraph("صافي الأرباح", cell_style), _paragraph(f"{net_profit:,}", cell_style)],
        [_paragraph("هامش الربح", cell_style), _paragraph(f"{profit_margin:.1f}%", cell_style)],
    ]
    financial_table = Table(financial_rows, colWidths=[260, 245], hAlign="CENTER")
    financial_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor("#f8fafc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.HexColor("#f8fafc"), colors.white]),
        ("BACKGROUND", (0, -2), (-1, -2),
         colors.HexColor("#ecfdf5") if net_profit >= 0 else colors.HexColor("#fff1f2")),
        ("TEXTCOLOR", (0, -2), (-1, -2),
         colors.HexColor("#047857") if net_profit >= 0 else colors.HexColor("#be123c")),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#dbe4e8")),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.extend([financial_table, Spacer(1, 12)])
    story.append(_paragraph("تفاصيل أجور المندوبين", section_style))

    detail_rows = [[
        _paragraph("المندوب", cell_style),
        _paragraph("القسم", cell_style),
        _paragraph("عدد الطلبات", cell_style),
        _paragraph("أجر الطلب (د.ع)", cell_style),
        _paragraph("الأجر المستحق (د.ع)", cell_style),
    ]]
    for _, row in driver_summary.iterrows():
        detail_rows.append([
            _paragraph(row["المندوب"], driver_style),
            _paragraph(row["القسم"], cell_style),
            _paragraph(f"{int(row['عدد الطلبات']):,}", cell_style),
            _paragraph(f"{int(row['التسعيرة']):,}", cell_style),
            _paragraph(f"{int(row['المبلغ']):,}", cell_style),
        ])
    detail_rows.append([
        _paragraph("الإجمالي", cell_style),
        "",
        _paragraph(f"{int(driver_summary['عدد الطلبات'].sum()):,}", cell_style),
        "",
        _paragraph(f"{driver_wages:,}", cell_style),
    ])
    detail_table = LongTable(
        detail_rows,
        colWidths=[145, 68, 78, 92, 122],
        repeatRows=1,
        hAlign="CENTER",
    )
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.HexColor("#f8fafc"), colors.white]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ccfbf1")),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#0f766e")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dbe4e8")),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.extend([
        detail_table,
        Spacer(1, 14),
        _paragraph("تم إعداد التقرير آليًا من كشف المحاسبة والتسعيرات المعتمدة.", small_style),
    ])
    document.build(story)
    return output.getvalue()
