from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, HiddenField
from wtforms.validators import DataRequired, Optional, Length, Regexp, NumberRange


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
    austritt_datum = StringField("Austrittsdatum (TT.MM.JJJJ)", validators=[Optional(), Length(max=20)])
    submit = SubmitField("Ausscheiden bestätigen")


LN_TYP_CHOICES = [("GLN", "GLN – Großer Leistungsnachweis"), ("KLN", "KLN – Kleiner Leistungsnachweis")]
HJ_CHOICES = [("HJ1", "Halbjahr 1"), ("HJ2", "Halbjahr 2")]
SL_CHOICES = [
    ("SL1", "SL1 (HJ1 – Note 1)"),
    ("SL2", "SL2 (HJ1 – Note 2)"),
    ("SL3", "SL3 (HJ2 – Note 1)"),
    ("SL4", "SL4 (HJ2 – Note 2)"),
]


class NewLNForm(FlaskForm):
    name = StringField("Bezeichnung (z.B. Klausur 1)", validators=[DataRequired(), Length(max=80)])
    ln_typ = SelectField("Typ", choices=LN_TYP_CHOICES, default="GLN")
    hj = SelectField("Halbjahr (für GLN)", choices=HJ_CHOICES, default="HJ1")
    sl_zuordnung = SelectField("SL-Zuordnung (für KLN)", choices=SL_CHOICES, default="SL1")
    submit = SubmitField("Leistungsnachweis anlegen")


class MoodleImportForm(FlaskForm):
    name = StringField("Bezeichnung", validators=[DataRequired(), Length(max=80)])
    ln_typ = SelectField("Typ", choices=LN_TYP_CHOICES, default="GLN")
    hj = SelectField("Halbjahr (für GLN)", choices=HJ_CHOICES, default="HJ1")
    sl_zuordnung = SelectField("SL-Zuordnung (für KLN)", choices=SL_CHOICES, default="SL1")
    submit = SubmitField("Importieren")


class ExportForm(FlaskForm):
    password = PasswordField("Exportpasswort (leer = ungeschützt)", validators=[Optional()])
    submit = SubmitField("Excel exportieren")


class KlassenEinstellungenForm(FlaskForm):
    klasse = StringField("Klassenbezeichner (z.B. 7p)", validators=[Optional(), Length(max=20)])
    fach = StringField("Fach (z.B. Informatik)", validators=[Optional(), Length(max=80)])
    schuljahr = StringField(
        "Schuljahr (z.B. 2526)",
        validators=[
            Optional(),
            Length(min=4, max=4, message="Schuljahr muss genau 4 Ziffern haben, z.B. 2526"),
            Regexp(r"^\d{4}$", message="Schuljahr muss genau 4 Ziffern haben, z.B. 2526"),
        ],
    )
    # SL-Note weights
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
    # HJ-Note weights (relative, normalized internally)
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
    submit = SubmitField("Einstellungen speichern")
