"""
PDF generation using xhtml2pdf.
Renders an HTML template to PDF in-memory and returns raw bytes.
"""
from __future__ import annotations

from datetime import date

from flask import render_template
from app.excel import schema as S


def _pisa_render(html: str) -> bytes:
    """Shared helper: render HTML → PDF bytes via xhtml2pdf."""
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
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"PDF-Generierung fehlgeschlagen: {exc}") from exc


def generate_pdf(data: dict, pdf_type: str) -> bytes:
    """
    Generate a PDF for the given data.

    pdf_type:
        'klasse' → class list with all LN grades per student
    """
    html = _build_html(data, pdf_type)
    return _pisa_render(html)


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
    return _pisa_render(html)


def generate_ln_zettel_pdf(
    klasse: str,
    fach: str,
    lehrkraft: str,
    ln_name: str,
    thema: str,
    datum: str,
    aufgaben: list[dict],
    schueler: list[dict],
    layout: int = 1,
) -> bytes:
    """
    Generate LN feedback slips for selected students.

    Each entry in `schueler` must contain:
        name     – "Nachname, Vorname"
        punkte   – list of floats/None, parallel to aufgaben
        note_15  – int or None
        note_6   – int or None
        ignoriert – bool

    The Notenspiegel and average are computed internally from the
    full schueler list (non-ignored students only).

    layout: 1 = one per A4 page (portrait)
            2 = two per A4 page (landscape)
            4 = four per A4 page (portrait)
    """
    # Compute Notenspiegel (6P) from all non-ignored students
    notenspiegel: dict[int, int] = {g: 0 for g in range(1, 7)}
    note6_vals: list[int] = []
    for s in schueler:
        if s.get("ignoriert"):
            continue
        n6 = s.get("note_6")
        if n6 is not None:
            notenspiegel[int(n6)] = notenspiegel.get(int(n6), 0) + 1
            note6_vals.append(int(n6))
    avg6 = round(sum(note6_vals) / len(note6_vals), 2) if note6_vals else None

    html = render_template(
        "pdf/ln_zettel.html",
        klasse=klasse,
        fach=fach,
        lehrkraft=lehrkraft,
        ln_name=ln_name,
        thema=thema,
        datum=datum,
        aufgaben=aufgaben,
        schueler=schueler,
        notenspiegel=notenspiegel,
        avg6=avg6,
        today=date.today().strftime("%d.%m.%Y"),
        layout=layout,
    )
    return _pisa_render(html)
