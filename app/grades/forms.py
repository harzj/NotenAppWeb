from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, HiddenField, RadioField
from wtforms.validators import DataRequired, Optional, Length, NumberRange, ValidationError


def _is_valid_schuljahr_start(raw: str) -> bool:
    raw = (raw or "").strip()
    return raw.isdigit() and len(raw) in (2, 4)


class UploadForm(FlaskForm):
    file = FileField(
        "Excel-Datei (.xlsx)",
        validators=[FileRequired(), FileAllowed(["xlsx"], "Nur .xlsx-Dateien erlaubt.")],
    )
    password = PasswordField("Dateipasswort (leer lassen falls ungeschützt)", validators=[Optional()])
    submit = SubmitField("Datei laden")


class StammdatenForm(FlaskForm):
    """Add a new student."""
    nachname = StringField("Nachname", validators=[DataRequired(), Length(max=100)])
    vorname = StringField("Vorname", validators=[DataRequired(), Length(max=100)])
    submit = SubmitField("Schüler hinzufügen")


class AustrittForm(FlaskForm):
    """Mark student as left."""
    student_index = HiddenField(validators=[DataRequired()])
    abgang_nach_hj = SelectField("Abgang nach Halbjahr", choices=[
        ("HJ1", "nach Halbjahr 1"), ("HJ2", "nach Halbjahr 2"),
        ("HJ3", "nach Halbjahr 3 (Kurs)"), ("HJ4", "nach Halbjahr 4 (Kurs)")], default="HJ2")
    submit = SubmitField("Ausscheiden bestätigen")


LN_TYP_CHOICES = [
    ("GLN", "GLN – Großer Leistungsnachweis"),
    ("KLN", "KLN – Kleiner Leistungsnachweis"),
    ("ABT", "ABT – Abiturprüfung"),
]
HJ_CHOICES = [("HJ1", "Halbjahr 1"), ("HJ2", "Halbjahr 2")]
SL_CHOICES = [
    ("SL1", "SL1 (HJ1 – Note 1)"),
    ("SL2", "SL2 (HJ1 – Note 2)"),
    ("SL3", "SL3 (HJ2 – Note 1)"),
    ("SL4", "SL4 (HJ2 – Note 2)"),
]
GLN_SLOT_CHOICES = [
    ("GLN1", "GLN 1 (HJ1 – 1. Klausur)"), ("GLN2", "GLN 2 (HJ1 – 2. Klausur)"),
    ("GLN3", "GLN 3 (HJ2 – 1. Klausur)"), ("GLN4", "GLN 4 (HJ2 – 2. Klausur)"),
    ("GLN5", "GLN 5 (HJ3 – 1. Klausur)"), ("GLN6", "GLN 6 (HJ3 – 2. Klausur)"),
    ("GLN7", "GLN 7 (HJ4 – 1. Klausur)"), ("GLN8", "GLN 8 (HJ4 – 2. Klausur)"),
]


class NewLNForm(FlaskForm):
    name = StringField("Bezeichnung (z.B. Klausur 1)", validators=[DataRequired(), Length(max=80)])
    thema = StringField("Thema (optional)", validators=[Optional(), Length(max=200)])
    datum = StringField("Datum (optional, z.B. 2025-05-25)", validators=[Optional(), Length(max=20)])
    ln_typ = SelectField("Typ", choices=LN_TYP_CHOICES, default="GLN")
    hj = SelectField("Halbjahr (für GLN)", choices=HJ_CHOICES, default="HJ1")
    sl_zuordnung = SelectField("SL-Zuordnung (für KLN)", choices=SL_CHOICES, default="SL1")
    gln_slot = SelectField("GLN-Slot (Kurs)", choices=GLN_SLOT_CHOICES, default="GLN1")
    submit = SubmitField("Leistungsnachweis anlegen")


class MoodleImportForm(FlaskForm):
    name = StringField("Bezeichnung", validators=[DataRequired(), Length(max=80)])
    ln_typ = SelectField("Typ", choices=LN_TYP_CHOICES, default="GLN")
    hj = SelectField("Halbjahr (für GLN)", choices=HJ_CHOICES, default="HJ1")
    sl_zuordnung = SelectField("SL-Zuordnung (für KLN)", choices=SL_CHOICES, default="SL1")
    gln_slot = SelectField("GLN-Slot (Kurs)", choices=GLN_SLOT_CHOICES, default="GLN1")
    submit = SubmitField("Importieren")


class NotendateiImportForm(FlaskForm):
    file = FileField("Notendatei (.xlsx)", validators=[FileRequired(), FileAllowed(["xlsx"], "Nur .xlsx-Dateien erlaubt.")])
    password = PasswordField("Dateipasswort (leer lassen falls ungeschützt)", validators=[Optional()])
    name = StringField("Bezeichnung (leer = Thema aus Datei)", validators=[Optional(), Length(max=80)])
    ln_typ = SelectField("Typ", choices=LN_TYP_CHOICES, default="GLN")
    hj = SelectField("Halbjahr (für GLN)", choices=HJ_CHOICES, default="HJ1")
    sl_zuordnung = SelectField("SL-Zuordnung (für KLN)", choices=SL_CHOICES, default="SL1")
    gln_slot = SelectField("GLN-Slot (Kurs)", choices=GLN_SLOT_CHOICES, default="GLN1")
    submit = SubmitField("Importieren")


class ExportForm(FlaskForm):
    password = PasswordField("Exportpasswort (leer = ungeschützt)", validators=[Optional()])
    submit = SubmitField("Excel exportieren")


class KlassenEinstellungenForm(FlaskForm):
    modus = RadioField("Modus", choices=[("klasse", "Klasse"), ("kurs", "Kurs (Oberstufe)")], default="klasse")
    klasse = StringField("Klassenbezeichner (z.B. 7p)", validators=[Optional(), Length(max=20)])
    fach = StringField("Fach (z.B. Informatik)", validators=[Optional(), Length(max=80)])
    schuljahr = StringField(
        "Start-Schuljahr (z.B. 25 oder 2025)",
        validators=[
            Optional(),
            Length(min=2, max=4, message="Bitte 2 oder 4 Ziffern angeben, z.B. 25 oder 2025"),
        ],
    )
    kurs_typ = SelectField("Kurstyp", choices=[("LK", "Leistungskurs (LK)"), ("GK", "Grundkurs (GK)")], default="GK")
    kurs_stunden = SelectField("Wochenstunden", choices=[("2", "2 Stunden"), ("3", "3 Stunden"), ("4", "4 Stunden")], default="4")
    # SL-Note weights (Klasse mode)
    sl_mdl_pct = FloatField(
        "Gewicht mündl. Note in SL-Note (%)",
        validators=[Optional(), NumberRange(0, 100)],
        default=70.0,
    )
    sl_kln_pct = FloatField(
        "Gewicht KLN-Mittel in SL-Note (%)",
        validators=[Optional(), NumberRange(0, 100)],
        default=30.0,
    )
    # HJ-Note weights (Klasse mode, relative, normalized internally)
    hj_gln_w = FloatField(
        "Gewicht GLN in HJ-Note",
        validators=[Optional(), NumberRange(0)],
        default=1.0,
    )
    hj_sl1_w = FloatField(
        "Gewicht SL1/3 in HJ-Note",
        validators=[Optional(), NumberRange(0)],
        default=1.0,
    )
    hj_sl2_w = FloatField(
        "Gewicht SL2/4 in HJ-Note",
        validators=[Optional(), NumberRange(0)],
        default=1.0,
    )
    # Kurs mode weights
    kurs_gln_pct = FloatField(
        "Gewicht GLN-Mittel in HJ-Note (%)",
        validators=[Optional(), NumberRange(0, 100)],
        default=70.0,
    )
    kurs_mdl_pct = FloatField(
        "Gewicht mündl. Noten in HJ-Note (%)",
        validators=[Optional(), NumberRange(0, 100)],
        default=30.0,
    )
    submit = SubmitField("Einstellungen speichern")

    def validate_schuljahr(self, field):
        if field.data and not _is_valid_schuljahr_start(field.data):
            raise ValidationError("Bitte 2 oder 4 Ziffern angeben, z.B. 25 oder 2025.")


LAYOUT_CHOICES = [("1", "1 pro Seite (A4 Hochformat)"), ("2", "2 pro Seite (A4 Querformat)"), ("4", "4 pro Seite (A4 Hochformat)")]


class LnZettelForm(FlaskForm):
    layout = SelectField("Zettel pro Seite", choices=LAYOUT_CHOICES, default="1")
    submit = SubmitField("PDF erstellen")
