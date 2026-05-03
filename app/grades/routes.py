import io
import json
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, session, send_file, abort,
)
from flask_login import login_required, current_user
from app.excel.reader import load_gradebook, ExcelReadError, schuljahr_from_date
from app.excel.writer import build_gradebook
from app.excel import schema as S
from app.excel.legacy_reader import probe_legacy_file, import_legacy_file
from app.grades.forms import (
    UploadForm, StammdatenForm, AustrittForm, NewLNForm, MoodleImportForm,
    NotendateiImportForm, ExportForm, KlassenEinstellungenForm, GLN_SLOT_CHOICES,
)
from app.grades import moodle as moodle_parser
from app.grades import berechnung
from app.grades.aufgaben import sanitize_node, generate_labels, get_leaves, tree_to_flat, flat_to_tree, calc_max
from app.pdf.generator import generate_pdf, generate_sl_zettel_pdf

grades_bp = Blueprint("grades", __name__, template_folder="../templates/grades")

SESSION_KEY = "gradebook"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_gradebook() -> dict | None:
    return session.get(SESSION_KEY)


def _save_gradebook(data: dict) -> None:
    session[SESSION_KEY] = data
    session.modified = True


def _rot_schwelle(klasse: str | None) -> int:
    """Return the note_15 threshold below which a note is shown in red.

    Notes < threshold are considered failing:
      - Klasse 11+: threshold = 5 (notes 00–04 are red)
      - Otherwise:  threshold = 4 (notes 00–03 are red)
    """
    if klasse:
        digits = "".join(c for c in klasse if c.isdigit())
        if digits:
            try:
                if int(digits[:2]) >= 11:
                    return 5
            except ValueError:
                pass
    return 4


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


# ── Legacy-Import (Admin only) ────────────────────────────────────────────────

_LEGACY_FILE_KEY   = "_legacy_bytes"
_LEGACY_PW_KEY     = "_legacy_pw"
_LEGACY_PROBE_KEY  = "_legacy_probe"
_SL_CHOICES        = ["SL1", "SL2", "SL3", "SL4"]
_HJ_CHOICES        = ["HJ1", "HJ2"]


def _admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@grades_bp.route("/legacy-import", methods=["GET", "POST"])
@login_required
def legacy_import():
    _admin_required()
    form = UploadForm()
    if form.validate_on_submit():
        file_bytes = form.file.data.read()
        password = form.password.data or None
        try:
            probe = probe_legacy_file(file_bytes, password)
        except Exception as e:
            flash(f"Datei konnte nicht gelesen werden: {e}", "danger")
            return render_template("grades/legacy_upload.html", form=form)
        if not probe["students"]:
            flash("Keine Schüler in der Datei gefunden.", "danger")
            return render_template("grades/legacy_upload.html", form=form)
        session[_LEGACY_FILE_KEY]  = file_bytes
        session[_LEGACY_PW_KEY]    = password
        session[_LEGACY_PROBE_KEY] = probe
        session.modified = True
        return redirect(url_for("grades.legacy_wizard"))
    return render_template("grades/legacy_upload.html", form=form)


@grades_bp.route("/legacy-import/wizard", methods=["GET", "POST"])
@login_required
def legacy_wizard():
    _admin_required()
    probe = session.get(_LEGACY_PROBE_KEY)
    if not probe:
        flash("Keine Datei zum Importieren gefunden. Bitte neu hochladen.", "warning")
        return redirect(url_for("grades.legacy_import"))

    if request.method == "POST":
        file_bytes = session.get(_LEGACY_FILE_KEY)
        password   = session.get(_LEGACY_PW_KEY)

        # ── collect KLN selections ────────────────────────────────────────
        kln_imports = []
        for sheet_info in probe.get("kln_sheets", []):
            sname = sheet_info["sheet"]
            for hue in sheet_info["hue_list"]:
                key = f"kln_{sname}_{hue['col']}"
                if request.form.get(key):
                    hj = request.form.get(f"kln_hj_{sname}_{hue['col']}", "HJ1")
                    sl = request.form.get(f"kln_sl_{sname}_{hue['col']}", "SL1")
                    kln_imports.append({
                        "sheet":   sname,
                        "col":     hue["col"],
                        "name":    hue["name"],
                        "max_pts": hue["max_pts"],
                        "hj":      hj if hj in _HJ_CHOICES else "HJ1",
                        "sl":      sl if sl in _SL_CHOICES else "SL1",
                    })

        # ── collect GLN selections ────────────────────────────────────────
        gln_imports = []
        for gname in probe.get("gln_sheets", []):
            if request.form.get(f"gln_{gname}"):
                hj = request.form.get(f"gln_hj_{gname}", "HJ1")
                gln_imports.append({
                    "sheet": gname,
                    "hj":    hj if hj in _HJ_CHOICES else "HJ1",
                    "sl":    None,
                })

        selections = {
            "klasse":         request.form.get("klasse", "").strip(),
            "fach":           request.form.get("fach", "").strip(),
            "schuljahr":      request.form.get("schuljahr", "").strip(),
            "kln_imports":    kln_imports,
            "gln_imports":    gln_imports,
            "bis_sl":         request.form.get("bis_sl", "SL4"),
        }

        try:
            data = import_legacy_file(file_bytes, password, selections)
        except Exception as e:
            flash(f"Import fehlgeschlagen: {e}", "danger")
            return render_template("grades/legacy_wizard.html", probe=probe,
                                   sl_choices=_SL_CHOICES, hj_choices=_HJ_CHOICES)

        _save_gradebook(data)
        # Clean up temp session keys
        for k in (_LEGACY_FILE_KEY, _LEGACY_PW_KEY, _LEGACY_PROBE_KEY):
            session.pop(k, None)
        session.modified = True

        n_lns = len(data["leistungsnachweise"])
        n_s   = len(data["stammdaten"])
        flash(f"Import erfolgreich: {n_s} Schüler, {n_lns} Leistungsnachweise.", "success")
        return redirect(url_for("grades.index"))

    return render_template("grades/legacy_wizard.html", probe=probe,
                           sl_choices=_SL_CHOICES, hj_choices=_HJ_CHOICES)


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
        "modus": "klasse",
        "klasse": "",
        "fach": "",
        "schuljahr": schuljahr_from_date(),
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

def _parse_name(raw: str) -> tuple[str, str] | None:
    """Parse a single name string into (nachname, vorname).
    Accepts 'Nachname, Vorname' or 'Vorname Nachname' forms.
    Returns None if the string is empty or looks like a header."""
    raw = raw.strip()
    if not raw:
        return None
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        return (parts[0], parts[1]) if parts[0] else None
    parts = raw.split()
    if len(parts) >= 2:
        return (parts[-1], " ".join(parts[:-1]))
    return (raw, "")


def _import_students_from_wb(wb) -> tuple[list[dict], str | None]:
    """Parse first sheet of an openpyxl workbook.
    Returns (students_list, error_message_or_None)."""
    import re
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], "Die Tabelle ist leer."

    # ── Try to find header row with known column names ──────────────────────
    NACHNAME_KEYS = {"nachname", "name", "familienname", "last name", "lastname"}
    VORNAME_KEYS  = {"vorname", "first name", "firstname", "given name"}
    FULLNAME_KEYS = {"name", "schüler", "schueler", "vollständiger name", "full name"}

    col_nachname = col_vorname = col_fullname = None
    header_row_idx = None

    for row_idx, row in enumerate(rows[:10]):  # search in first 10 rows
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        for col_idx, cell in enumerate(cells):
            if cell in NACHNAME_KEYS:
                col_nachname = col_idx
            elif cell in VORNAME_KEYS:
                col_vorname = col_idx
            elif cell in FULLNAME_KEYS and col_nachname is None and col_vorname is None:
                col_fullname = col_idx
        if col_nachname is not None or col_vorname is not None or col_fullname is not None:
            header_row_idx = row_idx
            break

    students = []

    if header_row_idx is not None:
        data_rows = rows[header_row_idx + 1:]
        for row in data_rows:
            if not any(row):
                continue
            if col_nachname is not None and col_vorname is not None:
                nn = str(row[col_nachname]).strip() if col_nachname < len(row) and row[col_nachname] else ""
                vn = str(row[col_vorname]).strip()  if col_vorname  < len(row) and row[col_vorname]  else ""
                if nn:
                    students.append({"nachname": nn, "vorname": vn,
                                     "status": S.SD_STATUS_AKTIV, "austritt": ""})
            elif col_nachname is not None:
                nn = str(row[col_nachname]).strip() if col_nachname < len(row) and row[col_nachname] else ""
                if nn:
                    students.append({"nachname": nn, "vorname": "",
                                     "status": S.SD_STATUS_AKTIV, "austritt": ""})
            elif col_vorname is not None:
                vn = str(row[col_vorname]).strip() if col_vorname < len(row) and row[col_vorname] else ""
                if vn:
                    students.append({"nachname": "", "vorname": vn,
                                     "status": S.SD_STATUS_AKTIV, "austritt": ""})
            else:  # fullname column
                raw = str(row[col_fullname]).strip() if col_fullname < len(row) and row[col_fullname] else ""
                parsed = _parse_name(raw)
                if parsed:
                    students.append({"nachname": parsed[0], "vorname": parsed[1],
                                     "status": S.SD_STATUS_AKTIV, "austritt": ""})
        if not students:
            return [], "Spalten gefunden, aber keine Schülerdaten darunter."
        return students, None

    # ── No header found: try first column as "Nachname, Vorname" ────────────
    for row in rows:
        if not any(row):
            continue
        raw = str(row[0]).strip() if row[0] is not None else ""
        parsed = _parse_name(raw)
        if parsed:
            students.append({"nachname": parsed[0], "vorname": parsed[1],
                             "status": S.SD_STATUS_AKTIV, "austritt": ""})

    if students:
        return students, None

    return [], (
        "Keine erkennbaren Namensspalten gefunden. "
        "Erwartet werden Spaltenköpfe wie 'Nachname'/'Vorname' oder 'Name'."
    )


@grades_bp.route("/stammdaten/import-excel", methods=["POST"])
@login_required
def stammdaten_import_excel():
    data = _require_gradebook()
    file = request.files.get("import_file")
    password = request.form.get("import_password") or None
    if not file or not file.filename.endswith(".xlsx"):
        flash("Bitte eine .xlsx-Datei auswählen.", "warning")
        return redirect(url_for("grades.stammdaten"))

    file_bytes = file.read()
    try:
        from app.excel.reader import _open_workbook, ExcelReadError
        wb = _open_workbook(file_bytes, password)
    except Exception as e:
        flash(f"Fehler beim Öffnen der Datei: {e}", "danger")
        return redirect(url_for("grades.stammdaten"))

    students, error = _import_students_from_wb(wb)
    if error:
        flash(f"Import fehlgeschlagen: {error}", "danger")
        return redirect(url_for("grades.stammdaten"))

    existing_names = {(s["nachname"], s["vorname"]) for s in data["stammdaten"]}
    added = 0
    for s in students:
        key = (s["nachname"], s["vorname"])
        if key not in existing_names:
            data["stammdaten"].append(s)
            existing_names.add(key)
            added += 1

    _save_gradebook(data)
    flash(f"{added} Schüler importiert ({len(students) - added} bereits vorhanden).", "success")
    return redirect(url_for("grades.stammdaten"))


@grades_bp.route("/stammdaten/import-paste", methods=["POST"])
@login_required
def stammdaten_import_paste():
    data = _require_gradebook()
    payload = request.get_json(force=True, silent=True)
    if not payload or "text" not in payload:
        return {"ok": False, "error": "Kein Text übermittelt."}, 400

    lines = payload["text"].strip().splitlines()
    existing_names = {(s["nachname"], s["vorname"]) for s in data["stammdaten"]}
    added = skipped = 0
    for line in lines:
        # Each line may be tab-separated (Excel copy) or plain
        parts = line.split("\t")
        raw = parts[0].strip()
        if not raw:
            continue
        # If two tab-separated columns, treat as Nachname \t Vorname
        if len(parts) >= 2 and parts[1].strip():
            nn, vn = raw, parts[1].strip()
        else:
            parsed = _parse_name(raw)
            if not parsed:
                continue
            nn, vn = parsed

        key = (nn, vn)
        if key not in existing_names:
            data["stammdaten"].append({"nachname": nn, "vorname": vn,
                                       "status": S.SD_STATUS_AKTIV, "austritt": ""})
            existing_names.add(key)
            added += 1
        else:
            skipped += 1

    _save_gradebook(data)
    return {"ok": True, "added": added, "skipped": skipped}


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
    abgang_hj = request.form.get("abgang_nach_hj", "HJ2")
    if idx is not None and 0 <= idx < len(data["stammdaten"]):
        data["stammdaten"][idx]["status"] = S.SD_STATUS_AUSGESCHIEDEN
        data["stammdaten"][idx]["abgang_nach_hj"] = abgang_hj
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
                           new_form=NewLNForm(),
                           modus=data.get("modus", "klasse"),
                           gln_slot_choices=GLN_SLOT_CHOICES)


@grades_bp.route("/ln/neu", methods=["POST"])
@login_required
def ln_neu():
    data = _require_gradebook()
    form = NewLNForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        ln_typ = form.ln_typ.data          # 'GLN' or 'KLN'
        modus = data.get("modus", "klasse")

        if modus == "kurs" and ln_typ == "GLN":
            gln_slot = form.gln_slot.data
            hj = berechnung.gln_slot_to_hj(gln_slot)
            sl_zuordnung = None
        else:
            gln_slot = None
            hj = form.hj.data if ln_typ == "GLN" else None
            sl_zuordnung = form.sl_zuordnung.data if ln_typ == "KLN" else None

        sheet_name = S.LN_SHEET_PREFIX + name
        existing = [ln["sheet_name"] for ln in data["leistungsnachweise"]]
        if sheet_name in existing:
            flash("Ein Leistungsnachweis mit diesem Namen existiert bereits.", "warning")
            return redirect(url_for("grades.ln_list"))

        schueler = []
        for s in data["stammdaten"]:
            if s.get("status") == S.SD_STATUS_AKTIV:
                # In Kurs mode, only add student if active in that HJ
                if modus == "kurs" and hj:
                    if not berechnung.student_active_in_hj(s, hj):
                        continue
                schueler.append({
                    "name": f"{s['nachname']}, {s['vorname']}",
                    "punkte": [],
                    "note_15": None,
                    "note_6": None,
                })

        data["leistungsnachweise"].append({
            "sheet_name": sheet_name,
            "name": name,
            "ln_typ": ln_typ,
            "hj": hj,
            "gln_slot": gln_slot,
            "sl_zuordnung": sl_zuordnung,
            "aufgaben": [],
            "aufgaben_tree": [],
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
    # Ensure aufgaben_tree exists (migrate legacy data on-the-fly)
    if "aufgaben_tree" not in ln:
        ln["aufgaben_tree"] = flat_to_tree(ln.get("aufgaben", []))
        _save_gradebook(data)
    return render_template("grades/ln_detail.html", ln=ln, ln_idx=ln_idx,
                           afb_values=S.AFB_VALUES,
                           grade_scale=S.GRADE_SCALE,
                           note15_to6=S.NOTE_15_TO_6,
                           rot_schwelle=_rot_schwelle(data.get("klasse")))


@grades_bp.route("/ln/<int:ln_idx>/aufgaben", methods=["POST"])
@login_required
def ln_aufgaben_speichern(ln_idx):
    """Save hierarchical task tree via JSON POST."""
    data = _require_gradebook()
    if ln_idx >= len(data["leistungsnachweise"]):
        abort(404)

    payload = request.get_json(force=True, silent=True)
    if not payload or "aufgaben_tree" not in payload:
        return {"ok": False, "error": "Invalid payload"}, 400

    # Sanitize and auto-label the incoming tree
    tree = [sanitize_node(n) for n in payload["aufgaben_tree"]]
    generate_labels(tree)

    # Build flat leaf list for backwards-compat (Excel writer, statistics)
    old_aufgaben = data["leistungsnachweise"][ln_idx].get("aufgaben", [])
    old_max = [float(a.get("max_punkte", 0)) for a in old_aufgaben]

    aufgaben = tree_to_flat(tree)
    data["leistungsnachweise"][ln_idx]["aufgaben_tree"] = tree
    data["leistungsnachweise"][ln_idx]["aufgaben"] = aufgaben

    # Adjust punkte arrays; scale values when max changed
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
                s["ignoriert"] = bool(incoming.get("ignoriert", False))
                # Recalculate grades server-side
                total = sum(p for p in s["punkte"] if p is not None)
                max_total = sum(a.get("max_punkte", 0) for a in ln["aufgaben"])
                has_any = any(p is not None for p in s["punkte"])
                s["note_15"] = S.percent_to_note15(total, max_total) if has_any else None
                s["note_6"] = S.note15_to_note6(s["note_15"]) if s["note_15"] is not None else None
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


# ── Moodle-Import ─────────────────────────────────────────────────────────────

@grades_bp.route("/ln/moodle-import", methods=["GET", "POST"])
@login_required
def moodle_import_ln():
    data = _require_gradebook()
    form = MoodleImportForm()

    if form.validate_on_submit():
        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("Bitte mindestens eine Moodle-Datei hochladen.", "warning")
            return render_template("grades/moodle_import.html", form=form)

        # Parse all uploaded files
        parsed_files = []
        parse_errors = []
        for f in files:
            if f.filename == "":
                continue
            try:
                result = moodle_parser.parse_moodle_file(f.read(), f.filename)
                parsed_files.append(result)
            except moodle_parser.MoodleParseError as exc:
                parse_errors.append(f"{f.filename}: {exc}")

        if parse_errors:
            for err in parse_errors:
                flash(err, "danger")
            return render_template("grades/moodle_import.html", form=form)

        if not parsed_files:
            flash("Keine gültigen Moodle-Dateien gefunden.", "warning")
            return render_template("grades/moodle_import.html", form=form)

        # Merge A/B groups
        merged = moodle_parser.merge_files(parsed_files)

        # Build LN name / sheet
        name = form.name.data.strip()
        ln_typ = form.ln_typ.data
        hj = form.hj.data if ln_typ == "GLN" else None
        sl_zuordnung = form.sl_zuordnung.data if ln_typ == "KLN" else None

        sheet_name = S.LN_SHEET_PREFIX + name
        existing = [ln["sheet_name"] for ln in data["leistungsnachweise"]]
        if sheet_name in existing:
            flash("Ein Leistungsnachweis mit diesem Namen existiert bereits.", "warning")
            return render_template("grades/moodle_import.html", form=form)

        # Build Aufgaben from parsed tasks
        task_list = merged.get("tasks", [])
        from app.grades.aufgaben import sanitize_node, generate_labels, tree_to_flat
        aufgaben_tree = []
        for t in task_list:
            aufgaben_tree.append(sanitize_node({
                "label": "",
                "title": t["name"],
                "max_punkte": t["max_punkte"],
                "afb": "",
                "children": [],
            }))
        generate_labels(aufgaben_tree)
        aufgaben = tree_to_flat(aufgaben_tree)

        # Match Moodle students to Stammdaten
        aktiv = [s for s in data["stammdaten"] if s.get("status") == S.SD_STATUS_AKTIV]
        matched, unmatched_moodle = moodle_parser.match_students(
            merged.get("students", []), aktiv
        )

        # Build reverse map: stammdaten_idx → moodle_student
        sd_to_moodle: dict = {sd_idx: merged["students"][m_idx]
                              for m_idx, sd_idx in matched.items()}

        n_tasks = len(aufgaben)
        schueler = []
        for sd_idx, s in enumerate(aktiv):
            ms = sd_to_moodle.get(sd_idx)
            punkte: list = []
            if ms and task_list:
                for t in task_list:
                    val = ms["punkte"].get(t["name"])
                    punkte.append(float(val) if val is not None else None)
            else:
                punkte = [None] * n_tasks

            total = sum(p for p in punkte if p is not None) if punkte else 0
            max_total = sum(a.get("max_punkte", 0) for a in aufgaben)
            note_15 = S.percent_to_note15(total, max_total) if ms and any(p is not None for p in punkte) else None
            note_6 = S.note15_to_note6(note_15) if note_15 is not None else None

            schueler.append({
                "name": f"{s['nachname']}, {s['vorname']}",
                "punkte": punkte,
                "note_15": note_15,
                "note_6": note_6,
            })

        data["leistungsnachweise"].append({
            "sheet_name": sheet_name,
            "name": name,
            "ln_typ": ln_typ,
            "hj": hj,
            "sl_zuordnung": sl_zuordnung,
            "aufgaben": aufgaben,
            "aufgaben_tree": aufgaben_tree,
            "schueler": schueler,
        })
        _save_gradebook(data)

        n_matched = len(matched)
        n_files = len(parsed_files)
        flash(
            f'Moodle-Import "{name}" abgeschlossen: {n_files} Datei(en), '
            f'{n_matched} von {len(aktiv)} Schülern zugeordnet.',
            "success",
        )
        if unmatched_moodle:
            names = ", ".join(f"{m['nachname']}, {m['vorname']}" for m in unmatched_moodle)
            flash(f"Nicht zugeordnete Moodle-Einträge (kein Schüler in Stammdaten): {names}", "warning")

        return redirect(url_for("grades.ln_detail", ln_idx=len(data["leistungsnachweise"]) - 1))

    return render_template("grades/moodle_import.html", form=form)


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_student_note(ln: dict, student_name: str) -> tuple:
    """Return (note_15, ignoriert) for a student in an LN."""
    for s in ln.get("schueler", []):
        if s["name"] == student_name:
            return s.get("note_15"), bool(s.get("ignoriert", False))
    return None, False


# ── SL-Detailseite ────────────────────────────────────────────────────────────

@grades_bp.route("/sl/<sl_key>")
@login_required
def sl_detail(sl_key):
    if sl_key not in ("SL1", "SL2", "SL3", "SL4"):
        abort(404)
    data = _require_gradebook()
    lns = data.get("leistungsnachweise", [])
    mdl_noten = data.get("mdl_noten") or {}
    gw = berechnung.get_gewichtung(data)

    sl_noten_actual = data.get("sl_noten_actual") or {}
    kln_list = [ln for ln in lns
                if ln.get("ln_typ") == "KLN" and ln.get("sl_zuordnung") == sl_key]
    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]

    rows = []
    for s in students:
        name = f"{s['nachname']}, {s['vorname']}"
        kln_cols = []
        for ln in kln_list:
            note_15, ignoriert = _get_student_note(ln, name)
            kln_cols.append({"ln_name": ln["name"], "note_15": note_15, "ignoriert": ignoriert})

        kln_notes_valid = [c["note_15"] for c in kln_cols if not c["ignoriert"] and c["note_15"] is not None]
        kln_mean = sum(kln_notes_valid) / len(kln_notes_valid) if kln_notes_valid else None

        mdl = mdl_noten.get(name, {}).get(sl_key)
        sl_raw = berechnung.compute_sl_note(name, sl_key, lns, mdl_noten, gw)
        sl_note_15 = berechnung.round_note15(sl_raw)
        sl_actual = sl_noten_actual.get(name, {}).get(sl_key)

        rows.append({
            "name": name,
            "kln_cols": kln_cols,
            "kln_mean": round(kln_mean, 2) if kln_mean is not None else None,
            "mdl": mdl,
            "sl_note_15": sl_note_15,
            "sl_actual": sl_actual,
        })

    return render_template(
        "grades/sl_detail.html",
        sl_key=sl_key,
        kln_list=kln_list,
        rows=rows,
        gewichtung=gw,
        note15_to6=S.NOTE_15_TO_6,
        rot_schwelle=_rot_schwelle(data.get("klasse")),
    )


@grades_bp.route("/api/mdl-noten/speichern", methods=["POST"])
@login_required
def mdl_noten_speichern():
    data = _require_gradebook()
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return {"ok": False, "error": "Invalid payload"}, 400
    sl_key = payload.get("sl_key")
    if sl_key not in ("SL1", "SL2", "SL3", "SL4"):
        return {"ok": False, "error": "Invalid sl_key"}, 400
    mdl_noten = data.setdefault("mdl_noten", {})
    sl_noten_actual = data.setdefault("sl_noten_actual", {})
    for item in payload.get("schueler", []):
        name = item.get("name")
        note = item.get("note")
        sl_act = item.get("sl_actual")
        if name:
            mdl_noten.setdefault(name, {})[sl_key] = (
                int(note) if note is not None else None
            )
            sl_noten_actual.setdefault(name, {})[sl_key] = (
                int(sl_act) if sl_act is not None else None
            )
    _save_gradebook(data)
    return {"ok": True}


# ── SL-Notenzettel drucken ────────────────────────────────────────────────────

@grades_bp.route("/sl/<sl_key>/druck")
@login_required
def sl_druck(sl_key):
    if sl_key not in ("SL1", "SL2", "SL3", "SL4"):
        abort(404)
    data = _require_gradebook()

    layout = request.args.get("layout", 1, type=int)
    if layout not in (1, 2, 4):
        layout = 1

    lns = data.get("leistungsnachweise", [])
    mdl_noten = data.get("mdl_noten") or {}
    sl_noten_actual = data.get("sl_noten_actual") or {}
    gw = berechnung.get_gewichtung(data)

    kln_list = [ln for ln in lns
                if ln.get("ln_typ") == "KLN" and ln.get("sl_zuordnung") == sl_key]
    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]

    # Build teacher display name from user profile
    lehrkraft_parts = []
    if current_user.lehrer_vorname:
        lehrkraft_parts.append(current_user.lehrer_vorname)
    if current_user.lehrer_nachname:
        lehrkraft_parts.append(current_user.lehrer_nachname)
    if not lehrkraft_parts:
        lehrkraft_parts.append(current_user.username)
    lehrkraft = " ".join(lehrkraft_parts)

    schueler_data = []
    for s in students:
        name = f"{s['nachname']}, {s['vorname']}"
        kln_noten = []
        for ln in kln_list:
            note_15, ignoriert = _get_student_note(ln, name)
            kln_noten.append({
                "name": ln["name"],
                "note_15": note_15,
                "ignoriert": ignoriert,
            })

        mdl_note = mdl_noten.get(name, {}).get(sl_key)
        sl_raw = berechnung.compute_sl_note(name, sl_key, lns, mdl_noten, gw)
        sl_note_15 = berechnung.round_note15(sl_raw)
        sl_actual = sl_noten_actual.get(name, {}).get(sl_key)

        schueler_data.append({
            "name": name,
            "mdl_note": mdl_note,
            "kln_noten": kln_noten,
            "sl_note_15": sl_note_15,
            "sl_note_6": S.note15_to_note6(sl_note_15) if sl_note_15 is not None else None,
            "sl_actual": sl_actual,
        })

    try:
        pdf_bytes = generate_sl_zettel_pdf(
            klasse=data.get("klasse", ""),
            fach=data.get("fach", ""),
            lehrkraft=lehrkraft,
            sl_key=sl_key,
            schueler=schueler_data,
            note15_to6=S.NOTE_15_TO_6,
            layout=layout,
        )
    except RuntimeError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("grades.sl_detail", sl_key=sl_key))

    klasse_safe = "".join(c for c in data.get("klasse", "Klasse") if c.isalnum() or c in "-_")
    filename = f"SL-Notenzettel_{sl_key}_{klasse_safe}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=filename,
    )


# ── HJ-Übersicht ──────────────────────────────────────────────────────────────

@grades_bp.route("/uebersicht/<hj>")
@login_required
def uebersicht(hj):
    if hj not in ("hj1", "hj2"):
        abort(404)
    data = _require_gradebook()
    lns = data.get("leistungsnachweise", [])
    mdl_noten = data.get("mdl_noten") or {}
    hj_noten = data.get("hj_noten") or {}
    gw = berechnung.get_gewichtung(data)

    hj_key = "HJ1" if hj == "hj1" else "HJ2"
    sl1_key, sl2_key = ("SL1", "SL2") if hj_key == "HJ1" else ("SL3", "SL4")

    gln_list = [ln for ln in lns if ln.get("ln_typ") == "GLN" and ln.get("hj") == hj_key]
    sl1_list = [ln for ln in lns if ln.get("ln_typ") == "KLN" and ln.get("sl_zuordnung") == sl1_key]
    sl2_list = [ln for ln in lns if ln.get("ln_typ") == "KLN" and ln.get("sl_zuordnung") == sl2_key]

    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]
    rows = []
    for s in students:
        name = f"{s['nachname']}, {s['vorname']}"

        gln_cols = [dict(zip(("note_15", "ignoriert"), _get_student_note(ln, name))) for ln in gln_list]
        sl1_cols = [dict(zip(("note_15", "ignoriert"), _get_student_note(ln, name))) for ln in sl1_list]
        sl2_cols = [dict(zip(("note_15", "ignoriert"), _get_student_note(ln, name))) for ln in sl2_list]

        gln_vals = [c["note_15"] for c in gln_cols if not c["ignoriert"] and c["note_15"] is not None]
        gln_mean = sum(gln_vals) / len(gln_vals) if gln_vals else None

        kln_mean_sl1 = berechnung.kln_mean_for_sl(name, sl1_key, lns)
        kln_mean_sl2 = berechnung.kln_mean_for_sl(name, sl2_key, lns)

        mdl1 = mdl_noten.get(name, {}).get(sl1_key)
        mdl2 = mdl_noten.get(name, {}).get(sl2_key)

        sl1_note_15 = berechnung.round_note15(
            berechnung.compute_sl_note(name, sl1_key, lns, mdl_noten, gw))
        sl2_note_15 = berechnung.round_note15(
            berechnung.compute_sl_note(name, sl2_key, lns, mdl_noten, gw))

        hj_vorschlag = berechnung.round_note15(
            berechnung.compute_hj_vorschlag(name, hj_key, lns, mdl_noten, gw))
        hj_actual = hj_noten.get(name, {}).get(hj_key)

        rows.append({
            "name": name,
            "gln_cols": gln_cols,
            "sl1_cols": sl1_cols,
            "sl2_cols": sl2_cols,
            "gln_mean": round(gln_mean, 2) if gln_mean is not None else None,
            "kln_mean_sl1": round(kln_mean_sl1, 2) if kln_mean_sl1 is not None else None,
            "kln_mean_sl2": round(kln_mean_sl2, 2) if kln_mean_sl2 is not None else None,
            "mdl1": mdl1,
            "mdl2": mdl2,
            "sl1_note_15": sl1_note_15,
            "sl2_note_15": sl2_note_15,
            "hj_vorschlag": hj_vorschlag,
            "hj_actual": hj_actual,
        })

    return render_template(
        "grades/uebersicht.html",
        hj=hj,
        hj_key=hj_key,
        sl1_key=sl1_key,
        sl2_key=sl2_key,
        gln_list=gln_list,
        sl1_list=sl1_list,
        sl2_list=sl2_list,
        rows=rows,
        gewichtung=gw,
        note15_to6=S.NOTE_15_TO_6,
        rot_schwelle=_rot_schwelle(data.get("klasse")),
    )


@grades_bp.route("/api/hj-speichern", methods=["POST"])
@login_required
def hj_speichern():
    """Save mdl notes (both SL slots) and actual HJ note for all students."""
    data = _require_gradebook()
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return {"ok": False, "error": "Invalid payload"}, 400
    hj_key = payload.get("hj")
    if hj_key not in ("HJ1", "HJ2"):
        return {"ok": False, "error": "Invalid hj"}, 400

    sl1_key, sl2_key = ("SL1", "SL2") if hj_key == "HJ1" else ("SL3", "SL4")
    mdl_noten = data.setdefault("mdl_noten", {})
    hj_noten = data.setdefault("hj_noten", {})

    for item in payload.get("schueler", []):
        name = item.get("name")
        if not name:
            continue
        mdl_noten.setdefault(name, {})[sl1_key] = (
            int(item["mdl1"]) if item.get("mdl1") is not None else None
        )
        mdl_noten.setdefault(name, {})[sl2_key] = (
            int(item["mdl2"]) if item.get("mdl2") is not None else None
        )
        hj_noten.setdefault(name, {})[hj_key] = (
            int(item["hj_actual"]) if item.get("hj_actual") is not None else None
        )

    _save_gradebook(data)
    return {"ok": True}


# ── Schuljahres-Übersicht ─────────────────────────────────────────────────────

@grades_bp.route("/uebersicht/schuljahr")
@login_required
def schuljahr_uebersicht():
    data = _require_gradebook()
    lns = data.get("leistungsnachweise", [])
    mdl_noten = data.get("mdl_noten") or {}
    hj_noten = data.get("hj_noten") or {}
    sl_noten_actual = data.get("sl_noten_actual") or {}
    sj_noten_actual = data.get("schuljahr_noten_actual") or {}
    gw = berechnung.get_gewichtung(data)
    students = [s for s in data.get("stammdaten", []) if s.get("status") == S.SD_STATUS_AKTIV]

    def _sl_display(name, sl_key):
        """Return (note_15, is_actual) – prefer saved actual over computed."""
        act = sl_noten_actual.get(name, {}).get(sl_key)
        if act is not None:
            return act, True
        computed = berechnung.round_note15(
            berechnung.compute_sl_note(name, sl_key, lns, mdl_noten, gw)
        )
        return computed, False

    rows = []
    for s in students:
        name = f"{s['nachname']}, {s['vorname']}"

        gln_hj1 = berechnung.round_note15(berechnung.gln_mean_for_hj(name, "HJ1", lns))
        sl1, sl1_actual = _sl_display(name, "SL1")
        sl2, sl2_actual = _sl_display(name, "SL2")
        hj1 = hj_noten.get(name, {}).get("HJ1")

        gln_hj2 = berechnung.round_note15(berechnung.gln_mean_for_hj(name, "HJ2", lns))
        sl3, sl3_actual = _sl_display(name, "SL3")
        sl4, sl4_actual = _sl_display(name, "SL4")
        hj2 = hj_noten.get(name, {}).get("HJ2")

        sj_vorschlag = berechnung.round_note15(berechnung.compute_schuljahr_note(name, hj_noten))
        sj_actual = sj_noten_actual.get(name)

        rows.append({
            "name": name,
            "gln_hj1": gln_hj1,
            "sl1": sl1, "sl1_actual": sl1_actual,
            "sl2": sl2, "sl2_actual": sl2_actual,
            "hj1": hj1,
            "gln_hj2": gln_hj2,
            "sl3": sl3, "sl3_actual": sl3_actual,
            "sl4": sl4, "sl4_actual": sl4_actual,
            "hj2": hj2,
            "sj_vorschlag": sj_vorschlag,
            "sj_actual": sj_actual,
        })

    return render_template(
        "grades/schuljahr.html",
        rows=rows,
        note15_to6=S.NOTE_15_TO_6,
        rot_schwelle=_rot_schwelle(data.get("klasse")),
    )


@grades_bp.route("/api/schuljahr-speichern", methods=["POST"])
@login_required
def schuljahr_speichern():
    data = _require_gradebook()
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return {"ok": False, "error": "Invalid payload"}, 400
    sj_actual = data.setdefault("schuljahr_noten_actual", {})
    for item in payload.get("schueler", []):
        name = item.get("name")
        note = item.get("sj_actual")
        if name:
            sj_actual[name] = int(note) if note is not None else None
    _save_gradebook(data)
    return {"ok": True}



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
        klasse = data.get("klasse", "Klasse") or "Klasse"
        schuljahr = data.get("schuljahr", "") or schuljahr_from_date()
        filename = f"Noten_{klasse}_{schuljahr}.xlsx"
        return send_file(
            io.BytesIO(file_bytes),
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return render_template("grades/export.html", form=form)


# ── Klasseneinstellungen ──────────────────────────────────────────────────────

@grades_bp.route("/einstellungen", methods=["GET", "POST"])
@login_required
def einstellungen():
    data = _require_gradebook()
    gw = berechnung.get_gewichtung(data)
    kgw = berechnung.get_kurs_gewichtung(data)
    modus = data.get("modus", "klasse")
    kurs_typ = data.get("kurs_typ", "GK")
    raw_stunden = data.get("kurs_stunden", 4)
    # LK always has 5 Stunden; clamp display to 4 since form only has 2/3/4
    stunden_display = str(min(int(raw_stunden), 4)) if raw_stunden else "4"
    form = KlassenEinstellungenForm(
        modus=modus,
        klasse=data.get("klasse", ""),
        fach=data.get("fach", ""),
        schuljahr=data.get("schuljahr", schuljahr_from_date()),
        kurs_typ=kurs_typ,
        kurs_stunden=stunden_display,
        sl_mdl_pct=gw["sl_mdl_pct"],
        sl_kln_pct=gw["sl_kln_pct"],
        hj_gln_w=gw["hj_gln_w"],
        hj_sl1_w=gw["hj_sl1_w"],
        hj_sl2_w=gw["hj_sl2_w"],
        kurs_gln_pct=kgw["hj_gln_pct"],
        kurs_mdl_pct=kgw["hj_mdl_pct"],
    )
    if form.validate_on_submit():
        data["modus"] = form.modus.data
        data["klasse"] = form.klasse.data.strip()
        data["fach"] = form.fach.data.strip()
        sj = form.schuljahr.data.strip()
        data["schuljahr"] = sj if sj else schuljahr_from_date()

        new_kurs_typ = form.kurs_typ.data
        new_stunden = int(form.kurs_stunden.data)
        # LK always gets 5 Stunden regardless of form selection
        if new_kurs_typ == "LK":
            new_stunden = 5
        data["kurs_typ"] = new_kurs_typ
        data["kurs_stunden"] = new_stunden

        data["sl_gewichtung"] = {
            "sl_mdl_pct": form.sl_mdl_pct.data if form.sl_mdl_pct.data is not None else 70.0,
            "sl_kln_pct": form.sl_kln_pct.data if form.sl_kln_pct.data is not None else 30.0,
            "hj_gln_w": form.hj_gln_w.data if form.hj_gln_w.data is not None else 1.0,
            "hj_sl1_w": form.hj_sl1_w.data if form.hj_sl1_w.data is not None else 1.0,
            "hj_sl2_w": form.hj_sl2_w.data if form.hj_sl2_w.data is not None else 1.0,
        }
        data["kurs_gewichtung"] = {
            "hj_gln_pct": form.kurs_gln_pct.data if form.kurs_gln_pct.data is not None else 70.0,
            "hj_mdl_pct": form.kurs_mdl_pct.data if form.kurs_mdl_pct.data is not None else 30.0,
        }
        _save_gradebook(data)
        flash("Einstellungen gespeichert.", "success")
        return redirect(url_for("grades.einstellungen"))
    return render_template("grades/einstellungen.html", form=form, data=data)


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

    # Note distribution 0-15 (skip ignored students)
    dist = {i: 0 for i in range(16)}
    afb_punkte = {"I": 0, "II": 0, "III": 0}
    for s in ln.get("schueler", []):
        if s.get("ignoriert"):
            continue
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


# ── Kurs-Übersicht ────────────────────────────────────────────────────────────

@grades_bp.route("/kurs/uebersicht/<hj>")
@login_required
def kurs_uebersicht(hj):
    data = _require_gradebook()
    if data.get("modus") != "kurs":
        flash("Diese Seite ist nur im Kurs-Modus verfügbar.", "warning")
        return redirect(url_for("grades.index"))
    if hj not in berechnung.HJ_ORDER:
        abort(404)

    kurs_typ = data.get("kurs_typ", "GK")
    kurs_stunden = int(data.get("kurs_stunden", 4))
    valid_slots = berechnung.valid_gln_slots(kurs_typ, kurs_stunden)

    # Active students in this HJ
    students = [s for s in data.get("stammdaten", [])
                if berechnung.student_active_in_hj(s, hj)]

    lns = data.get("leistungsnachweise", [])
    kgw = berechnung.get_kurs_gewichtung(data)
    mdl_noten_kurs = data.get("mdl_noten_kurs", {})
    hj_noten = data.get("hj_noten", {})

    # Build per-student row
    rows = []
    for s in students:
        name = f"{s['nachname']}, {s['vorname']}"
        gln_notes = {}
        for slot in valid_slots:
            slot_hj = berechnung.gln_slot_to_hj(slot)
            if slot_hj != hj:
                continue
            for ln in lns:
                if ln.get("gln_slot") == slot:
                    for sc in ln.get("schueler", []):
                        if sc["name"] == name and not sc.get("ignoriert"):
                            gln_notes[slot] = sc.get("note_15")
        kn = mdl_noten_kurs.get(name, {})
        mdl1 = kn.get(f"{hj}_mdl1")
        mdl2 = kn.get(f"{hj}_mdl2")
        vorschlag = berechnung.compute_hj_vorschlag_kurs(name, hj, lns, mdl_noten_kurs, kgw)
        tatsaechlich = hj_noten.get(name, {}).get(hj)
        rows.append({
            "name": name,
            "gln_notes": gln_notes,
            "mdl1": mdl1,
            "mdl2": mdl2,
            "vorschlag": vorschlag,
            "tatsaechlich": tatsaechlich,
        })

    # Only slots for this HJ
    hj_slots = [sl for sl in valid_slots if berechnung.gln_slot_to_hj(sl) == hj]

    return render_template("grades/kurs_uebersicht.html",
                           hj=hj, rows=rows, hj_slots=hj_slots,
                           all_hj=berechnung.HJ_ORDER,
                           data=data)


@grades_bp.route("/api/hj-kurs-speichern", methods=["POST"])
@login_required
def hj_kurs_speichern():
    data = _require_gradebook()
    if data.get("modus") != "kurs":
        return {"ok": False, "error": "Not in Kurs mode"}, 400

    payload = request.get_json(force=True, silent=True)
    if not payload:
        return {"ok": False, "error": "Invalid payload"}, 400

    hj = payload.get("hj")
    if hj not in berechnung.HJ_ORDER:
        return {"ok": False, "error": "Invalid HJ"}, 400

    mdl_noten_kurs = data.setdefault("mdl_noten_kurs", {})
    hj_noten = data.setdefault("hj_noten", {})

    for entry in payload.get("rows", []):
        name = entry.get("name", "")
        if not name:
            continue
        kn = mdl_noten_kurs.setdefault(name, {})
        # Save mündliche Noten
        for key in (f"{hj}_mdl1", f"{hj}_mdl2"):
            val = entry.get(key)
            if val is not None:
                try:
                    kn[key] = float(val)
                except (TypeError, ValueError):
                    kn[key] = None
            else:
                kn[key] = None
        # Save tatsächliche HJ-Note
        tats = entry.get("tatsaechlich")
        hn = hj_noten.setdefault(name, {})
        if tats is not None:
            try:
                hn[hj] = float(tats)
            except (TypeError, ValueError):
                hn[hj] = None
        else:
            hn[hj] = None

    _save_gradebook(data)
    return {"ok": True}
