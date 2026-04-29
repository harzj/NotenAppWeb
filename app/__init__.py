import os
from flask import Flask
from app.config import config_by_name
from app.extensions import db, login_manager, sess, csrf, limiter


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "default")

    app = Flask(__name__, instance_relative_config=False)
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
        return {"current_klasse": gb.get("klasse", "") if gb else ""}

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
