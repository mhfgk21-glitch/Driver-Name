from datetime import date


def format_pdf_date(value: date) -> str:
    """Keep date digits and separators in left-to-right order in RTL PDF text."""
    return f"\u200e{value:%Y/%m/%d}\u200e"
