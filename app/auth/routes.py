from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import User
from app.auth.forms import LoginForm, RegistrationForm, ChangePasswordForm, LehrerProfilForm

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("grades.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash("Ungültiger Benutzername oder Passwort.", "danger")
            return render_template("auth/login.html", form=form)

        if not user.is_approved:
            flash("Dein Konto wurde noch nicht freigeschaltet. Bitte warte auf die Admin-Freischaltung.", "warning")
            return render_template("auth/login.html", form=form)

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

    return render_template("auth/login.html", form=form)


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
    form = LehrerProfilForm(
        lehrer_vorname=current_user.lehrer_vorname or "",
        lehrer_nachname=current_user.lehrer_nachname or "",
        dienstbezeichnung=current_user.dienstbezeichnung or "",
        anrede=current_user.anrede or "keine",
    )
    if form.validate_on_submit():
        current_user.lehrer_vorname = form.lehrer_vorname.data.strip() or None
        current_user.lehrer_nachname = form.lehrer_nachname.data.strip() or None
        current_user.dienstbezeichnung = form.dienstbezeichnung.data or None
        current_user.anrede = form.anrede.data or None
        db.session.commit()
        flash("Profil gespeichert.", "success")
        return redirect(url_for("auth.profil"))
    return render_template("auth/profil.html", form=form)


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
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("auth/admin_users.html", users=users)


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
