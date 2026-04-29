"""
PDF generation using WeasyPrint.
Renders an HTML template to PDF in-memory and returns raw bytes.
"""
from __future__ import annotations

import io
from datetime import date

from flask import render_template
from app.excel import schema as S


def generate_pdf(data: dict, pdf_type: str) -> bytes:
    """
    Generate a PDF for the given data.

    pdf_type:
        'klasse' → class list with all LN grades per student
    """
    html = _build_html(data, pdf_type)
    try:
        from weasyprint import HTML
        buf = io.BytesIO()
        HTML(string=html).write_pdf(buf)
        return buf.getvalue()
    except Exception as exc:
        raise RuntimeError(f"PDF-Generierung fehlgeschlagen: {exc}") from exc


def _build_html(data: dict, pdf_type: str) -> str:
    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]
    lns = data.get("leistungsnachweise", [])
    today = date.today().strftime("%d.%m.%Y")
    return render_template(
        "pdf/klassenliste.html",
        students=students,
        lns=lns,
        today=today,
        note15_to6=S.NOTE_15_TO_6,
    )
