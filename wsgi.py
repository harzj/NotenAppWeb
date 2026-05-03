"""
WSGI entry point for PythonAnywhere and other WSGI servers.
"""
import os
from app import create_app

application = create_app(os.environ.get("FLASK_ENV", "production"))
