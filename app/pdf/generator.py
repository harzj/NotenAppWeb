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


def generate_abitur_pdf(
    klasse: str,
    fach: str,
    lehrkraft: str,
    ln_name: str,
    thema: str,
    datum: str,
    aufgaben: list[dict],
    schueler: list[dict],
) -> bytes:
    """
    Generate a plain Abitur result table: Name | task cols | Gesamt | Note (15P) | Note (6P).
    """
    note6_vals: list[int] = [int(s["note_6"]) for s in schueler
                              if not s.get("ignoriert") and s.get("note_6") is not None]
    avg6 = round(sum(note6_vals) / len(note6_vals), 2) if note6_vals else None

    html = render_template(
        "pdf/abitur_zettel.html",
        klasse=klasse,
        fach=fach,
        lehrkraft=lehrkraft,
        ln_name=ln_name,
        thema=thema,
        datum=datum,
        aufgaben=aufgaben,
        schueler=schueler,
        avg6=avg6,
        today=date.today().strftime("%d.%m.%Y"),
    )
    return _pisa_render(html)


# ── ABT per-student Zettel ────────────────────────────────────────────────────

def _build_abt_sections(aufgaben_tree: list[dict]) -> list[dict]:
    """
    Build print sections from the aufgaben_tree.

    If ALL root nodes are leaves (flat tree) → one combined section.
    If any root has children → one section per root node.

    Returns list of sections:
        [{label, rows: [{label, max, idx, afb}], max}, ...]
    """
    if not aufgaben_tree:
        return []

    leaf_counter = [0]

    def collect_leaves(nodes: list[dict], parent_label: str = "") -> list[dict]:
        rows = []
        for node in nodes:
            node_label = node.get("label", "")
            full_label = f"{parent_label}.{node_label}" if parent_label else node_label
            children = node.get("children") or []
            if children:
                rows.extend(collect_leaves(children, full_label))
            else:
                rows.append({
                    "label": full_label,
                    "max":   float(node.get("max_punkte") or 0),
                    "idx":   leaf_counter[0],
                    "afb":   node.get("afb", ""),
                })
                leaf_counter[0] += 1
        return rows

    all_flat = all(not (node.get("children") or []) for node in aufgaben_tree)

    sections = []
    for root in aufgaben_tree:
        children = root.get("children") or []
        root_label = root.get("label", "")
        if children:
            rows = collect_leaves(children, root_label)
        else:
            rows = [{
                "label": root.get("label", ""),
                "max":   float(root.get("max_punkte") or 0),
                "idx":   leaf_counter[0],
                "afb":   root.get("afb", ""),
            }]
            leaf_counter[0] += 1
        sections.append({
            "label": root.get("label", ""),
            "rows":  rows,
            "max":   sum(r["max"] for r in rows),
        })
    return sections


def generate_abt_zettel_pdf(
    klasse: str,
    fach: str,
    lehrkraft: str,
    ln_name: str,
    thema: str,
    datum: str,
    aufgaben_tree: list[dict],
    schueler: list[dict],
    layout: int = 1,
    orientation: str = "portrait",
) -> bytes:
    """
    Generate ABT per-student feedback slips.

    Each entry in `schueler` must contain:
        kuerzel   – exam candidate code (shown instead of name)
        punkte    – flat list of floats/None, parallel to leaves in aufgaben_tree
        note_15   – int or None
        note_6    – int or None  (unused in output, note_15 is the ABT grade)

    layout:      1 / 2 / 4  slips per page
    orientation: 'portrait' or 'landscape'
    """
    sections = _build_abt_sections(aufgaben_tree)
    total_max = sum(s["max"] for s in sections)

    # Pre-compute per-student section sums
    for student in schueler:
        punkte = student.get("punkte") or []
        sec_data = []
        for sec in sections:
            sec_pts = []
            sec_sum = 0.0
            has_any = False
            for row in sec["rows"]:
                idx = row["idx"]
                val = punkte[idx] if idx < len(punkte) else None
                sec_pts.append(val)
                if val is not None:
                    sec_sum += val
                    has_any = True
            sec_data.append({
                "pts":    sec_pts,
                "sum":    sec_sum if has_any else None,
                "has_any": has_any,
            })
        student["_sec_data"] = sec_data

        # Total & percent
        total = sum(sd["sum"] for sd in sec_data if sd["sum"] is not None)
        has_total = any(sd["has_any"] for sd in sec_data)
        student["_total"]   = total if has_total else None
        student["_pct"]     = round(total / total_max * 100, 1) if (has_total and total_max > 0) else None

    html = render_template(
        "pdf/abt_zettel.html",
        klasse=klasse,
        fach=fach,
        orientation=orientation,
        lehrkraft=lehrkraft,
        ln_name=ln_name,
        thema=thema,
        datum=datum,
        sections=sections,
        total_max=total_max,
        schueler=schueler,
        today=date.today().strftime("%d.%m.%Y"),
        layout=layout,
    )
    return _pisa_render(html)
