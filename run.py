import os
from app import create_app
from app.versioning import format_version, load_version_data

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    host = app.config.get("HOST", "0.0.0.0")
    port = app.config.get("PORT", 5000)
    print(f"Starte NotenApp Version {format_version(load_version_data())} auf http://localhost:{port}")
    app.run(host=host, port=port)
