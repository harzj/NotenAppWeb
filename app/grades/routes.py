import io
import json
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, session, send_file, abort,
)
from flask_login import login_required, current_user
from app.excel.reader import load_gradebook, ExcelReadError
from app.excel.writer import build_gradebook
from app.excel import schema as S
from app.grades.forms import UploadForm, StammdatenForm, AustrittForm, NewLNForm, ExportForm
from app.pdf.generator import generate_pdf

grades_bp = Blueprint("grades", __name__, template_folder="../templates/grades")

SESSION_KEY = "gradebook"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_gradebook() -> dict | None:
    return session.get(SESSION_KEY)


def _save_gradebook(data: dict) -> None:
    session[SESSION_KEY] = data
    session.modified = True


def _require_gradebook():
    data = _get_gradebook()
    if data is None:
        flash("Keine Datei geladen. Bitte zuerst eine Excel-Datei hochladen.", "warning")
        abort(redirect(url_for("grades.upload")))
    return data


# ── Index ─────────────────────────────────────────────────────────────────────

@grades_bp.route("/")
@login_required
def index():
    data = _get_gradebook()
    return render_template("grades/index.html", has_data=data is not None,
                           data=data)


# ── Upload ────────────────────────────────────────────────────────────────────

@grades_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        file_bytes = form.file.data.read()
        password = form.password.data or None
        try:
            data = load_gradebook(file_bytes, password)
            _save_gradebook(data)
            flash("Datei erfolgreich geladen.", "success")
            return redirect(url_for("grades.index"))
        except ExcelReadError as e:
            flash(str(e), "danger")
    return render_template("grades/upload.html", form=form)


@grades_bp.route("/close")
@login_required
def close_file():
    session.pop(SESSION_KEY, None)
    session.modified = True
    flash("Datei geschlossen. Alle Daten wurden aus dem Speicher entfernt.", "info")
    return redirect(url_for("grades.index"))


# ── Neue leere Datei erstellen ────────────────────────────────────────────────

@grades_bp.route("/new")
@login_required
def new_file():
    empty = {
        "klasse": "",
        "stammdaten": [],
        "leistungsnachweise": [],
        "uebersicht_hj1": None,
        "uebersicht_hj2": None,
        "uebersicht_jahr": None,
    }
    _save_gradebook(empty)
    flash("Neue leere Datei erstellt.", "success")
    return redirect(url_for("grades.index"))


@grades_bp.route("/klasse", methods=["POST"])
@login_required
def set_klasse():
    data = _require_gradebook()
    data["klasse"] = request.form.get("klasse", "").strip()
    _save_gradebook(data)
    flash("Klassenbezeichnung gespeichert.", "success")
    return redirect(url_for("grades.index"))


# ── Stammdaten ────────────────────────────────────────────────────────────────

@grades_bp.route("/stammdaten", methods=["GET", "POST"])
@login_required
def stammdaten():
    data = _require_gradebook()
    add_form = StammdatenForm()
    austritt_form = AustrittForm()

    if add_form.validate_on_submit() and "add_student" in request.form:
        data["stammdaten"].append({
            "nachname": add_form.nachname.data,
            "vorname":  add_form.vorname.data,
            "status":   S.SD_STATUS_AKTIV,
            "austritt": "",
        })
        _save_gradebook(data)
        flash("Schüler hinzugefügt.", "success")
        return redirect(url_for("grades.stammdaten"))

    return render_template(
        "grades/stammdaten.html",
        students=data["stammdaten"],
        add_form=add_form,
        austritt_form=austritt_form,
    )


@grades_bp.route("/stammdaten/austritt", methods=["POST"])
@login_required
def student_austritt():
    data = _require_gradebook()
    idx = request.form.get("student_index", type=int)
    datum = request.form.get("austritt_datum", "")
    if idx is not None and 0 <= idx < len(data["stammdaten"]):
        data["stammdaten"][idx]["status"] = S.SD_STATUS_AUSGESCHIEDEN
        data["stammdaten"][idx]["austritt"] = datum
        _save_gradebook(data)
        flash("Schüler als ausgeschieden markiert.", "success")
    return redirect(url_for("grades.stammdaten"))


@grades_bp.route("/stammdaten/reaktivieren/<int:idx>", methods=["POST"])
@login_required
def student_reaktivieren(idx):
    data = _require_gradebook()
    if 0 <= idx < len(data["stammdaten"]):
        data["stammdaten"][idx]["status"] = S.SD_STATUS_AKTIV
        data["stammdaten"][idx]["austritt"] = ""
        _save_gradebook(data)
        flash("Schüler reaktiviert.", "success")
    return redirect(url_for("grades.stammdaten"))


@grades_bp.route("/stammdaten/loeschen/<int:idx>", methods=["POST"])
@login_required
def student_loeschen(idx):
    data = _require_gradebook()
    if 0 <= idx < len(data["stammdaten"]):
        data["stammdaten"].pop(idx)
        _save_gradebook(data)
        flash("Schüler gelöscht.", "success")
    return redirect(url_for("grades.stammdaten"))


# ── Leistungsnachweise ────────────────────────────────────────────────────────

@grades_bp.route("/ln")
@login_required
def ln_list():
    data = _require_gradebook()
    return render_template("grades/ln_list.html", lns=data["leistungsnachweise"],
                           new_form=NewLNForm())


@grades_bp.route("/ln/neu", methods=["POST"])
@login_required
def ln_neu():
    data = _require_gradebook()
    form = NewLNForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        sheet_name = S.LN_SHEET_PREFIX + name
        # Check for duplicate
        existing = [ln["sheet_name"] for ln in data["leistungsnachweise"]]
        if sheet_name in existing:
            flash("Ein Leistungsnachweis mit diesem Namen existiert bereits.", "warning")
            return redirect(url_for("grades.ln_list"))

        # Pre-fill student list from Stammdaten
        schueler = []
        for s in data["stammdaten"]:
            if s.get("status") == S.SD_STATUS_AKTIV:
                schueler.append({
                    "name": f"{s['nachname']}, {s['vorname']}",
                    "punkte": [],
                    "note_15": None,
                    "note_6": None,
                })

        data["leistungsnachweise"].append({
            "sheet_name": sheet_name,
            "name": name,
            "aufgaben": [],
            "schueler": schueler,
        })
        _save_gradebook(data)
        flash(f'Leistungsnachweis "{name}" erstellt.', "success")
        return redirect(url_for("grades.ln_detail", ln_idx=len(data["leistungsnachweise"]) - 1))
    return redirect(url_for("grades.ln_list"))


@grades_bp.route("/ln/<int:ln_idx>")
@login_required
def ln_detail(ln_idx):
    data = _require_gradebook()
    if ln_idx >= len(data["leistungsnachweise"]):
        abort(404)
    ln = data["leistungsnachweise"][ln_idx]
    return render_template("grades/ln_detail.html", ln=ln, ln_idx=ln_idx,
                           afb_values=S.AFB_VALUES,
                           grade_scale=S.GRADE_SCALE,
                           note15_to6=S.NOTE_15_TO_6)


@grades_bp.route("/ln/<int:ln_idx>/aufgaben", methods=["POST"])
@login_required
def ln_aufgaben_speichern(ln_idx):
    """Save task configuration (labels, AFB, max points) via JSON POST."""
    data = _require_gradebook()
    if ln_idx >= len(data["leistungsnachweise"]):
        abort(404)

    payload = request.get_json(force=True, silent=True)
    if not payload or "aufgaben" not in payload:
        return {"ok": False, "error": "Invalid payload"}, 400

    # Save old max per task index for proportional scaling
    old_aufgaben = data["leistungsnachweise"][ln_idx].get("aufgaben", [])
    old_max = [float(a.get("max_punkte", 0)) for a in old_aufgaben]

    aufgaben = []
    for a in payload["aufgaben"]:
        aufgaben.append({
            "label": str(a.get("label", "")).strip() or "?",
            "afb": str(a.get("afb", "")).strip(),
            "max_punkte": float(a["max_punkte"]) if a.get("max_punkte") not in (None, "") else 0,
        })

    data["leistungsnachweise"][ln_idx]["aufgaben"] = aufgaben

    # Adjust punkte arrays; scale values when max changed (e.g. 4→8 doubles points)
    n = len(aufgaben)
    for s in data["leistungsnachweise"][ln_idx]["schueler"]:
        current = s.get("punkte", [])
        new_punkte = []
        for t_idx in range(n):
            val = current[t_idx] if t_idx < len(current) else None
            if val is not None and t_idx < len(old_max):
                om = old_max[t_idx]
                nm = aufgaben[t_idx]["max_punkte"]
                if om > 0 and nm > 0 and om != nm:
                    # Round to nearest 0.25 after scaling
                    val = round(val * nm / om * 4) / 4
            new_punkte.append(val)
        s["punkte"] = new_punkte

    _save_gradebook(data)
    return {"ok": True}


@grades_bp.route("/ln/<int:ln_idx>/noten", methods=["POST"])
@login_required
def ln_noten_speichern(ln_idx):
    """Save student scores via JSON POST."""
    data = _require_gradebook()
    if ln_idx >= len(data["leistungsnachweise"]):
        abort(404)

    payload = request.get_json(force=True, silent=True)
    if not payload or "schueler" not in payload:
        return {"ok": False, "error": "Invalid payload"}, 400

    ln = data["leistungsnachweise"][ln_idx]
    for incoming in payload["schueler"]:
        name = incoming.get("name")
        for s in ln["schueler"]:
            if s["name"] == name:
                raw = incoming.get("punkte", [])
                s["punkte"] = [float(p) if p not in (None, "") else None for p in raw]
                # Recalculate grades server-side
                total = sum(p for p in s["punkte"] if p is not None)
                max_total = sum(a.get("max_punkte", 0) for a in ln["aufgaben"])
                s["note_15"] = S.percent_to_note15(total, max_total)
                s["note_6"] = S.note15_to_note6(s["note_15"])
                break

    _save_gradebook(data)
    return {"ok": True}


@grades_bp.route("/ln/<int:ln_idx>/loeschen", methods=["POST"])
@login_required
def ln_loeschen(ln_idx):
    data = _require_gradebook()
    if ln_idx < len(data["leistungsnachweise"]):
        name = data["leistungsnachweise"][ln_idx]["name"]
        data["leistungsnachweise"].pop(ln_idx)
        _save_gradebook(data)
        flash(f'Leistungsnachweis "{name}" gelöscht.', "success")
    return redirect(url_for("grades.ln_list"))


# ── Übersichten ───────────────────────────────────────────────────────────────

@grades_bp.route("/uebersicht/<hj>")
@login_required
def uebersicht(hj):
    if hj not in ("hj1", "hj2", "jahr"):
        abort(404)
    data = _require_gradebook()
    lns = data.get("leistungsnachweise", [])
    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]
    return render_template("grades/uebersicht.html", hj=hj, lns=lns,
                           students=students, schema=S,
                           note15_to6=S.NOTE_15_TO_6)


# ── Export ────────────────────────────────────────────────────────────────────

@grades_bp.route("/export/excel", methods=["GET", "POST"])
@login_required
def export_excel():
    data = _require_gradebook()
    form = ExportForm()
    if form.validate_on_submit():
        password = form.password.data or None
        try:
            file_bytes = build_gradebook(data, password=password)
        except Exception as e:
            flash(f"Fehler beim Export: {e}", "danger")
            return render_template("grades/export.html", form=form)
        return send_file(
            io.BytesIO(file_bytes),
            download_name="Notendatei.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return render_template("grades/export.html", form=form)


@grades_bp.route("/export/pdf/<pdf_type>")
@login_required
def export_pdf(pdf_type):
    data = _require_gradebook()
    if pdf_type not in ("klasse", "schueler"):
        abort(404)
    try:
        pdf_bytes = generate_pdf(data, pdf_type)
    except Exception as e:
        flash(f"Fehler beim PDF-Export: {e}", "danger")
        return redirect(url_for("grades.index"))
    filename = "Klassenliste.pdf" if pdf_type == "klasse" else "Notenblatt.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        download_name=filename,
        as_attachment=True,
        mimetype="application/pdf",
    )


# ── Statistik API (JSON für Chart.js) ────────────────────────────────────────

@grades_bp.route("/api/statistik/<int:ln_idx>")
@login_required
def statistik_json(ln_idx):
    data = _require_gradebook()
    if ln_idx >= len(data["leistungsnachweise"]):
        abort(404)
    ln = data["leistungsnachweise"][ln_idx]

    # Note distribution 0-15
    dist = {i: 0 for i in range(16)}
    afb_punkte = {"I": 0, "II": 0, "III": 0}
    for s in ln.get("schueler", []):
        note = s.get("note_15")
        if note is not None:
            dist[int(note)] += 1
        for t_idx, task in enumerate(ln.get("aufgaben", [])):
            afb = task.get("afb", "")
            if afb in afb_punkte:
                p = s["punkte"][t_idx] if t_idx < len(s.get("punkte", [])) else None
                if p is not None:
                    afb_punkte[afb] += p

    # Max points per AFB
    afb_max = {"I": 0, "II": 0, "III": 0}
    for task in ln.get("aufgaben", []):
        afb = task.get("afb", "")
        if afb in afb_max:
            afb_max[afb] += task.get("max_punkte", 0)

    return {
        "note_distribution": dist,
        "afb_punkte": afb_punkte,
        "afb_max": afb_max,
    }
