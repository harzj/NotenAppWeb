import os
import sys
from flask import Flask
from app.config import config_by_name
from app.extensions import db, login_manager, sess, csrf, limiter


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    # When frozen by PyInstaller, templates/static are bundled in _MEIPASS.
    if getattr(sys, "frozen", False):
        root_path = sys._MEIPASS  # noqa: SLF001
    else:
        root_path = None  # default: package directory

    app = Flask(__name__, instance_relative_config=False,
                **{"root_path": root_path} if root_path else {})
    app.config.from_object(config_by_name[config_name])

    # Ensure instance and session directories exist
    os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
    os.makedirs(os.path.dirname(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")), exist_ok=True)

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    sess.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.grades.routes import grades_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(grades_bp, url_prefix="/")

    # Custom Jinja filters
    app.jinja_env.filters["enumerate"] = enumerate

    # Context processors
    @app.context_processor
    def inject_meta():
        from flask import session as _sess
        gb = _sess.get("gradebook")
        current_modus = gb.get("modus", "klasse") if gb else "klasse"
        kurs_typ = gb.get("kurs_typ", "") if gb else ""
        kurs_stunden = gb.get("kurs_stunden", "") if gb else ""
        current_kurs_info = (
            {"typ": kurs_typ, "stunden": kurs_stunden, "fach": gb.get("fach", "")}
            if (gb and current_modus == "kurs") else None
        )
        # Find ABT LN index (first non-NachTermin ABT LN)
        abt_ln_idx = None
        if gb:
            for i, ln in enumerate(gb.get("leistungsnachweise", [])):
                if ln.get("ln_typ") == "ABT" and not ln.get("nachtermin_von"):
                    abt_ln_idx = i
                    break
        return {
            "current_klasse": gb.get("klasse", "") if gb else "",
            "current_modus": current_modus,
            "current_kurs_info": current_kurs_info,
            "abt_ln_idx": abt_ln_idx,
        }

    # Create DB tables
    with app.app_context():
        db.create_all()
        _ensure_admin_exists()

    return app


def _ensure_admin_exists() -> None:
    """Create a default admin account if no users exist yet."""
    from app.models import User

    if User.query.count() == 0:
        admin = User(
            username="admin",
            email="admin@localhost",
            is_approved=True,
            is_admin=True,
        )
        admin.set_password("admin")  # Must be changed on first login
        db.session.add(admin)
        db.session.commit()
        print("[INFO] Default admin created: username=admin password=admin — CHANGE IMMEDIATELY")
