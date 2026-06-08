import os
from app import create_app
from app.versioning import format_version, load_version_data

app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    print(f"Starte NotenApp Version {format_version(load_version_data())} auf http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)
