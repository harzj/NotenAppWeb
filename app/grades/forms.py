from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, HiddenField
from wtforms.validators import DataRequired, Optional, Length


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


class NewLNForm(FlaskForm):
    name = StringField("Bezeichnung (z.B. Klausur 1)", validators=[DataRequired(), Length(max=80)])
    submit = SubmitField("Leistungsnachweis anlegen")


class ExportForm(FlaskForm):
    password = PasswordField("Exportpasswort (leer = ungeschützt)", validators=[Optional()])
    submit = SubmitField("Excel exportieren")
