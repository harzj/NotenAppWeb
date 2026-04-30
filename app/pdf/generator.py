"""
PDF generation using xhtml2pdf.
Renders an HTML template to PDF in-memory and returns raw bytes.
"""
from __future__ import annotations

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
        import io
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
        if status.err:
            raise RuntimeError(f"xhtml2pdf Fehler (Code {status.err})")
        return buf.getvalue()
    except ImportError:
        raise RuntimeError("xhtml2pdf ist nicht installiert. Bitte 'pip install xhtml2pdf' ausführen.")
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


# ── SL-Notenzettel ────────────────────────────────────────────────────────────

_SL_TITEL: dict[str, str] = {
    "SL1": "Sonstige Leistungen 1 (Halbjahr 1)",
    "SL2": "Sonstige Leistungen 2 (Halbjahr 1)",
    "SL3": "Sonstige Leistungen 1 (Halbjahr 2)",
    "SL4": "Sonstige Leistungen 2 (Halbjahr 2)",
}


def generate_sl_zettel_pdf(
    klasse: str,
    fach: str,
    lehrkraft: str,
    sl_key: str,
    schueler: list[dict],
    note15_to6: dict,
    layout: int = 1,
) -> bytes:
    """
    Generate SL feedback slips for all active students.

    Each student entry in `schueler` must contain:
        name        – "Nachname, Vorname"
        mdl_note    – int or None
        kln_noten   – list of {"name", "note_15", "ignoriert"}
        sl_note_15  – int or None  (computed suggestion)
        sl_note_6   – int or None
        sl_actual   – int or None  (teacher override)

    layout: 1 = one per A4 page (portrait)
            2 = two per A4 page (landscape)
            4 = four per A4 page (portrait)
    """
    html = render_template(
        "pdf/sl_zettel.html",
        klasse=klasse,
        fach=fach,
        lehrkraft=lehrkraft,
        sl_key=sl_key,
        sl_titel=_SL_TITEL.get(sl_key, sl_key),
        schueler=schueler,
        note15_to6=note15_to6,
        today=date.today().strftime("%d.%m.%Y"),
        layout=layout,
    )
    try:
        import io
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        status = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
        if status.err:
            raise RuntimeError(f"xhtml2pdf Fehler (Code {status.err})")
        return buf.getvalue()
    except ImportError:
        raise RuntimeError("xhtml2pdf ist nicht installiert. Bitte 'pip install xhtml2pdf' ausführen.")
    except Exception as exc:
        raise RuntimeError(f"PDF-Generierung fehlgeschlagen: {exc}") from exc
