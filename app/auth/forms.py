from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, EmailField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError
from app.models import User


class LoginForm(FlaskForm):
    username = StringField("Benutzername", validators=[DataRequired()])
    password = PasswordField("Passwort", validators=[DataRequired()])
    remember_me = BooleanField("Angemeldet bleiben")
    submit = SubmitField("Anmelden")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Benutzername",
        validators=[DataRequired(), Length(min=3, max=64)],
    )
    email = EmailField("E-Mail", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField(
        "Passwort",
        validators=[DataRequired(), Length(min=10, message="Mindestens 10 Zeichen")],
    )
    password2 = PasswordField(
        "Passwort wiederholen",
        validators=[DataRequired(), EqualTo("password", message="Passwörter stimmen nicht überein")],
    )
    submit = SubmitField("Registrieren")

    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError("Benutzername bereits vergeben.")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError("E-Mail-Adresse bereits registriert.")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Aktuelles Passwort", validators=[DataRequired()])
    new_password = PasswordField(
        "Neues Passwort",
        validators=[DataRequired(), Length(min=10)],
    )
    new_password2 = PasswordField(
        "Neues Passwort wiederholen",
        validators=[DataRequired(), EqualTo("new_password", message="Passwörter stimmen nicht überein")],
    )
    submit = SubmitField("Passwort ändern")


# Ränge unabhängig vom Geschlecht als (Key, männliche Abkürzung, weibliche Abkürzung).
# AdL hat keine eigene weibliche Abkürzung, daher identisch in beiden Spalten.
DIENSTBEZEICHNUNG_RANGE = [
    ("adl", "AdL", "AdL"),
    ("stref", "StRef", "StRef'in"),
    ("str", "StR", "StR'in"),
    ("ostr", "OStR", "OStR'in"),
    ("std", "StD", "StD'in"),
    ("ostd", "OStD", "OStD'in"),
]

# Bildet frühere, ausgeschriebene Werte auf die neuen Kurz-Keys ab (Bestandsdaten).
LEGACY_DIENSTBEZEICHNUNG_MAP = {
    "ADL": "adl",
    "Studienreferendar/in": "stref",
    "Studienrat/rätin": "str",
    "Oberstudienrat/rätin": "ostr",
    "Studiendirektor/in": "std",
    "Oberstudiendirektor/in": "ostd",
}


def dienstbezeichnung_choices(anrede: str) -> list[tuple[str, str]]:
    """Baut die Auswahlliste mit der zur Anrede passenden Abkürzung."""
    is_female = anrede == "Frau"
    choices = [("", "– keine –")]
    for key, label_m, label_w in DIENSTBEZEICHNUNG_RANGE:
        choices.append((key, label_w if is_female else label_m))
    return choices


ANREDEN = [
    ("keine", "keine"),
    ("Herr", "Herr"),
    ("Frau", "Frau"),
]


class LehrerProfilForm(FlaskForm):
    lehrer_vorname = StringField("Vorname", validators=[Optional(), Length(max=64)])
    lehrer_nachname = StringField("Nachname", validators=[Optional(), Length(max=64)])
    dienstbezeichnung = SelectField(
        "Dienstbezeichnung",
        choices=dienstbezeichnung_choices("keine"),  # wird pro Request in routes.py neu gesetzt
        validators=[Optional()],
    )
    anrede = SelectField(
        "Anrede",
        choices=ANREDEN,
        validators=[Optional()],
    )
    submit = SubmitField("Profil speichern")
