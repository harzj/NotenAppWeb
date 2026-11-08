"""Produktionsstart für den Notfallserver (Windows-Dienst, siehe deploy/).

waitress statt Flask-Entwicklungsserver; Host/Port aus NOTENAPP_HOST/NOTENAPP_PORT.
Die exe startet weiterhin über tray.py.
"""
import os

from waitress import serve

from app import create_app
from app.versioning import format_version, load_version_data

app = create_app(os.environ.get("FLASK_ENV", "default"))

if __name__ == "__main__":
    host = app.config.get("HOST", "0.0.0.0")
    port = app.config.get("PORT", 5000)
    print(f"Starte NotenApp {format_version(load_version_data())} (waitress) auf {host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=8)
