from datetime import datetime, timezone
import secrets

from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import User, UsedZugangslink
from sqlalchemy.exc import IntegrityError
from app.auth import dateilogin, zugangslinks
from app.auth.forms import (
    LoginForm, RegistrationForm, ChangePasswordForm, LehrerProfilForm, DateiLoginForm, NeuesPasswortForm,
    dienstbezeichnung_choices, LEGACY_DIENSTBEZEICHNUNG_MAP, DIENSTBEZEICHNUNG_RANGE,
)

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("grades.index"))

    form = LoginForm()
    datei_form = DateiLoginForm() if current_app.config.get("FILE_LOGIN_ACCEPT") else None
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Ungültiger Benutzername oder Passwort.", "danger")
            return render_template("auth/login.html", form=form, datei_form=datei_form)

        if not user.is_approved:
            flash("Dein Konto wurde noch nicht freigeschaltet. Bitte warte auf die Admin-Freischaltung.", "warning")
            return render_template("auth/login.html", form=form, datei_form=datei_form)

        login_user(user, remember=form.remember_me.data)
        user.last_login = datetime.now(timezone.utc)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            current_app.logger.warning("Could not persist last_login for %s: %s", user.username, exc)

        next_page = request.args.get("next")
        # Prevent open redirect
        if next_page and not next_page.startswith("/"):
            next_page = None
        return redirect(next_page or url_for("grades.index"))

    return render_template("auth/login.html", form=form, datei_form=datei_form)


def _user_from_token(info: dict) -> User | None:
    """Find or (re-)create the user described by a valid access token."""
    user = User.query.filter_by(username=info["username"]).first()
    if user is None:
        if User.query.filter_by(email=info["email"]).first() is not None:
            return None  # e-mail belongs to another account on this server
        user = User(username=info["username"], email=info["email"], is_admin=False)
        user.set_password(secrets.token_urlsafe(24))  # login only via file until changed
        db.session.add(user)
    user.is_approved = True
    for attr in ("lehrer_vorname", "lehrer_nachname", "dienstbezeichnung", "anrede"):
        if not getattr(user, attr) and info.get(attr):
            setattr(user, attr, info[attr])
    if info.get("notendatei_import"):
        user.notendatei_import = True
    return user


@auth_bp.route("/login-datei", methods=["POST"])
@limiter.limit("10 per minute")
def login_datei():
    """Anmelden mit Notendatei: the file's password proves possession, the signed
    access token inside says who it belongs to. The classes are loaded right away."""
    key = current_app.config.get("FILE_LOGIN_KEY")
    if not current_app.config.get("FILE_LOGIN_ACCEPT") or not key:
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("grades.index"))
    from app.excel.reader import ExcelReadError, load_gradebook
    from app.grades.routes import _load_zip_gradebooks, _replace_all_gradebooks, _set_source_password

    form = DateiLoginForm()
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for e in errors:
                flash(e, "danger")
        return redirect(url_for("auth.login"))

    filename = (form.datei.data.filename or "").lower()
    file_bytes = form.datei.data.read()
    password = form.datei_passwort.data
    try:
        if filename.endswith(".zip"):
            books = _load_zip_gradebooks(file_bytes, password)
        else:
            books = [load_gradebook(file_bytes, password)]
    except ExcelReadError:
        flash("Die Datei konnte mit diesem Passwort nicht geöffnet werden.", "danger")
        return redirect(url_for("auth.login"))

    info = None
    for book in books:
        info = dateilogin.read_token(book.get("_zugang"), key)
        if info:
            break
    if not info:
        flash("Diese Datei enthält keinen gültigen Zugriffsschlüssel (oder er ist abgelaufen). "
              "Melde dich einmal normal an, lade die Datei und exportiere sie mit Passwort – "
              "danach klappt die Anmeldung mit der Datei.", "warning")
        return redirect(url_for("auth.login"))

    user = _user_from_token(info)
    if user is None:
        db.session.rollback()
        flash("Zu dieser Datei passt kein Konto auf diesem Server (E-Mail-Adresse bereits vergeben). "
              "Bitte wende dich an den Admin.", "danger")
        return redirect(url_for("auth.login"))
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    session.clear()
    login_user(user)
    _replace_all_gradebooks(books)
    _set_source_password(password)
    flash(f"Angemeldet als {user.username} – {len(books)} Klasse(n) aus deiner Notendatei geladen.", "success")
    return redirect(url_for("grades.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    # Wipe session data (removes uploaded grade data)
    session.clear()
    logout_user()
    flash("Erfolgreich abgemeldet.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("grades.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            is_approved=False,
            is_admin=False,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(
            "Registrierung erfolgreich! Dein Konto wird von einem Admin freigeschaltet.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/zugang/<token>", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def zugang(token):
    """Zugangslink: Einladung (Konto anlegen, sofort freigeschaltet) oder Passwort neu setzen."""
    payload = zugangslinks.read_token(token)
    if payload is None:
        return render_template("auth/zugang.html", fehler="Dieser Link ist ungültig oder abgelaufen "
                               "(Links gelten 14 Tage). Bitte lass dir einen neuen schicken.")
    if db.session.get(UsedZugangslink, payload["j"]) is not None:
        return render_template("auth/zugang.html", fehler="Dieser Link wurde bereits benutzt. "
                               "Bitte lass dir bei Bedarf einen neuen schicken.")
    if current_user.is_authenticated:
        return render_template("auth/zugang.html", fehler="Du bist gerade angemeldet. Bitte melde dich zuerst ab "
                               "und öffne den Link dann erneut – er ist noch unbenutzt.")

    art = payload["a"]
    form = RegistrationForm() if art == zugangslinks.EINLADUNG else NeuesPasswortForm()
    if form.validate_on_submit():
        if art == zugangslinks.EINLADUNG:
            user = User(username=form.username.data, email=form.email.data, is_admin=False)
            db.session.add(user)
        else:
            user = User.query.filter_by(username=payload["u"]).first()
            if user is None:
                # Link from the other server (Landkreis ↔ Notfallserver): create the account here
                if User.query.filter_by(email=payload["e"]).first() is not None:
                    return render_template("auth/zugang.html", fehler="Die E-Mail-Adresse dieses Kontos ist auf "
                                           "diesem Server schon einem anderen Benutzer zugeordnet. Bitte wende dich an den Admin.")
                user = User(username=payload["u"], email=payload["e"], is_admin=False)
                db.session.add(user)
        user.set_password(form.password.data)
        user.is_approved = True
        user.last_login = datetime.now(timezone.utc)
        db.session.add(UsedZugangslink(jti=payload["j"], art=art))
        try:
            db.session.commit()
        except IntegrityError:   # used in parallel or username/email just taken
            db.session.rollback()
            return render_template("auth/zugang.html", fehler="Der Link konnte nicht verwendet werden "
                                   "(bereits benutzt oder Benutzername/E-Mail inzwischen vergeben).")
        session.clear()
        login_user(user)
        if art == zugangslinks.EINLADUNG:
            flash(f"Willkommen, {user.username}! Dein Konto ist eingerichtet. "
                  "Trag hier noch deinen Namen ein – er erscheint auf den Notenzetteln.", "success")
            return redirect(url_for("auth.profil"))
        flash("Neues Passwort gespeichert – du bist angemeldet.", "success")
        return redirect(url_for("grades.index"))

    return render_template("auth/zugang.html", form=form, art=art,
                           username=payload.get("u"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Aktuelles Passwort ist falsch.", "danger")
            return render_template("auth/change_password.html", form=form)
        current_user.set_password(form.new_password.data)
        db.session.commit()
        flash("Passwort erfolgreich geändert.", "success")
        return redirect(url_for("grades.index"))

    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    # Bestandsdaten können noch die alten, ausgeschriebenen Werte enthalten
    stored_dienstbezeichnung = LEGACY_DIENSTBEZEICHNUNG_MAP.get(
        current_user.dienstbezeichnung or "", current_user.dienstbezeichnung or ""
    )
    form = LehrerProfilForm(
        lehrer_vorname=current_user.lehrer_vorname or "",
        lehrer_nachname=current_user.lehrer_nachname or "",
        dienstbezeichnung=stored_dienstbezeichnung,
        anrede=current_user.anrede or "keine",
    )
    # Auswahlliste hängt von der (bei POST bereits abgesendeten) Anrede ab
    form.dienstbezeichnung.choices = dienstbezeichnung_choices(form.anrede.data)
    if form.validate_on_submit():
        current_user.lehrer_vorname = form.lehrer_vorname.data.strip() or None
        current_user.lehrer_nachname = form.lehrer_nachname.data.strip() or None
        current_user.dienstbezeichnung = form.dienstbezeichnung.data or None
        current_user.anrede = form.anrede.data or None
        db.session.commit()
        flash("Profil gespeichert.", "success")
        return redirect(url_for("auth.profil"))
    dienstbezeichnung_labels = {
        key: {"m": label_m, "w": label_w} for key, label_m, label_w in DIENSTBEZEICHNUNG_RANGE
    }
    dienstbezeichnung_labels[""] = {"m": "– keine –", "w": "– keine –"}
    return render_template(
        "auth/profil.html", form=form, dienstbezeichnung_labels=dienstbezeichnung_labels
    )


# ── Admin area ──────────────────────────────────────────────────────────────

def admin_required(f):
    """Decorator: only allow admins."""
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Dieser Bereich ist nur für Administratoren.", "danger")
            return redirect(url_for("grades.index"))
        return f(*args, **kwargs)

    return decorated


@auth_bp.route("/admin/users")
@login_required
@admin_required
def admin_users():
    return _render_admin_users()


def _render_admin_users(**extra):
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("auth/admin_users.html", users=users,
                           link_server_uebergreifend=bool(current_app.config.get("FILE_LOGIN_KEY")),
                           **extra)


@auth_bp.route("/admin/einladung", methods=["POST"])
@login_required
@admin_required
def admin_einladung():
    """Create a single-use invitation link (account is approved right away)."""
    return _render_admin_users(
        neuer_link=zugangslinks.make_link(zugangslinks.EINLADUNG),
        link_titel="Einladungslink für eine neue Kollegin / einen neuen Kollegen")


@auth_bp.route("/admin/users/<int:user_id>/passwort-link", methods=["POST"])
@login_required
@admin_required
def admin_passwort_link(user_id):
    """Create a single-use link with which the user sets a new password."""
    user = db.get_or_404(User, user_id)
    return _render_admin_users(
        neuer_link=zugangslinks.make_link(zugangslinks.PASSWORT, user),
        link_titel=f"Link zum Passwort-Neusetzen für {user.username}")


@auth_bp.route("/admin/users/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Benutzer nicht gefunden.", "danger")
    else:
        user.is_approved = True
        db.session.commit()
        flash(f'Benutzer "{user.username}" wurde freigeschaltet.', "success")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/users/<int:user_id>/revoke", methods=["POST"])
@login_required
@admin_required
def revoke_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Benutzer nicht gefunden.", "danger")
    elif user.id == current_user.id:
        flash("Du kannst dich nicht selbst sperren.", "warning")
    else:
        user.is_approved = False
        db.session.commit()
        flash(f'Benutzer "{user.username}" wurde gesperrt.', "warning")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Benutzer nicht gefunden.", "danger")
    elif user.id == current_user.id:
        flash("Du kannst dich nicht selbst löschen.", "warning")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'Benutzer "{user.username}" wurde gelöscht.', "success")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/users/<int:user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Benutzer nicht gefunden.", "danger")
    elif user.id == current_user.id:
        flash("Du kannst deine eigenen Admin-Rechte nicht ändern.", "warning")
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        status = "Admin" if user.is_admin else "Benutzer"
        flash(f'"{user.username}" ist jetzt {status}.', "success")
    return redirect(url_for("auth.admin_users"))


@auth_bp.route("/admin/users/<int:user_id>/toggle-notendatei", methods=["POST"])
@login_required
@admin_required
def toggle_notendatei(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("Benutzer nicht gefunden.", "danger")
    else:
        user.notendatei_import = not user.notendatei_import
        db.session.commit()
        status = "aktiviert" if user.notendatei_import else "deaktiviert"
        flash(f'Notendatei-Import für "{user.username}" {status}.', "success")
    return redirect(url_for("auth.admin_users"))
