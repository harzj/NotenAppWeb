"""
Tray-Launcher für NotenApp.
Startet den Flask-Server + (optional) ngrok-Tunnel im Hintergrund und zeigt ein Windows-Tray-Icon.
Im frozen-Modus (Distribution) läuft nur der lokale Server auf localhost:5000.
Rechtsklick → "Beenden" stoppt Server und App.
"""
import os
import sys
import io
import json
import logging
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from app.versioning import format_version, load_version_data


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    val = val.strip().lower()
    if val == "":
        return default
    return val in {"1", "true", "yes", "on"}


# ngrok-Konfiguration
NGROK_DOMAIN = os.environ.get("NGROK_DOMAIN", "enzyme-cognitive-nearly.ngrok-free.dev")
NGROK_ENABLED = _env_bool("NGROK_ENABLED", True)
APP_HOST = os.environ.get("NOTENAPP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("NOTENAPP_PORT", "5000"))
# ngrok.exe im gleichen Ordner wie tray.py suchen, sonst im PATH
_here = Path(__file__).parent
NGROK_EXE = os.environ.get(
    "NGROK_EXE",
    str(_here / "ngrok.exe") if (_here / "ngrok.exe").exists() else "ngrok",
)

_ngrok_proc = None

# --- Log-Capture: alle Ausgaben in einer Liste puffern ---
_log_parts: list[str] = []
_log_lock = threading.Lock()


class _CapStream:
    """Leitet stdout/stderr in den Log-Puffer um."""
    def __init__(self, original=None):
        self._orig = original

    def write(self, text):
        if text:
            with _log_lock:
                _log_parts.append(text)
        if self._orig:
            try:
                self._orig.write(text)
            except Exception:
                pass

    def flush(self):
        if self._orig:
            try:
                self._orig.flush()
            except Exception:
                pass

    def isatty(self):
        return False


class _LogHandler(logging.Handler):
    """Leitet logging-Records in den Log-Puffer um."""
    def emit(self, record):
        msg = self.format(record) + "\n"
        with _log_lock:
            _log_parts.append(msg)


# Sofort installieren – vor Flask-Start
sys.stdout = _CapStream(sys.stdout)
sys.stderr = _CapStream(sys.stderr)

_log_handler = _LogHandler()
_log_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s: %(message)s"))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.INFO)

APP_VERSION = format_version(load_version_data())


def _make_icon() -> Image.Image:
    """Erzeugt ein einfaches blaues 'N'-Icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Blauer Kreis
    draw.ellipse((0, 0, size - 1, size - 1), fill=(13, 110, 253))
    # Weißes 'N' (zwei Linien + Diagonale)
    m = size // 6
    lw = max(3, size // 12)
    pts_left = [(m, m), (m, size - m)]
    pts_right = [(size - m, m), (size - m, size - m)]
    pts_diag = [(m, m), (size - m, size - m)]
    draw.line(pts_left, fill="white", width=lw)
    draw.line(pts_right, fill="white", width=lw)
    draw.line(pts_diag, fill="white", width=lw)
    return img


def _run_flask():
    """Flask-Server in eigenem Thread starten."""
    from app import create_app
    flask_app = create_app(os.environ.get("FLASK_ENV", "development"))
    print(f"[INFO] Starte NotenApp Version {APP_VERSION} auf http://localhost:{APP_PORT}")
    # use_reloader=False und threaded=True für Tray-Betrieb
    flask_app.run(host=APP_HOST, port=APP_PORT, use_reloader=False, threaded=True)


def _run_ngrok():
    """ngrok-Tunnel starten."""
    global _ngrok_proc
    popen_kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd_with_domain = [NGROK_EXE, "http", f"--domain={NGROK_DOMAIN}", str(APP_PORT)]
    _ngrok_proc = subprocess.Popen(cmd_with_domain, **popen_kwargs)

    # If the reserved domain fails quickly, fall back to a random ngrok URL.
    time.sleep(1.2)
    if _ngrok_proc.poll() is not None:
        print("[WARN] ngrok mit fester Domain konnte nicht gestartet werden. Wechsle auf dynamische URL.")
        _ngrok_proc = subprocess.Popen([NGROK_EXE, "http", str(APP_PORT)], **popen_kwargs)


def _get_ngrok_public_url() -> str | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        tunnels = payload.get("tunnels", [])
        for tunnel in tunnels:
            url = tunnel.get("public_url", "")
            if url.startswith("https://"):
                return url
        for tunnel in tunnels:
            url = tunnel.get("public_url", "")
            if url:
                return url
    except Exception:
        return None
    return None


def _open_browser(icon, item):
    tunnel_url = _get_ngrok_public_url()
    if tunnel_url:
        webbrowser.open(tunnel_url)
    elif NGROK_DOMAIN:
        webbrowser.open(f"https://{NGROK_DOMAIN}")
    else:
        webbrowser.open(f"http://localhost:{APP_PORT}")


def _open_local(icon, item):
    webbrowser.open(f"http://localhost:{APP_PORT}")


def _show_console(icon, item):
    """Öffnet ein Tkinter-Fenster mit dem gepufferten Server-Log."""
    def _build():
        import tkinter as tk
        from tkinter import scrolledtext

        root = tk.Tk()
        root.title("NotenApp – Server-Konsole")
        root.geometry("900x520")
        root.configure(bg="#1e1e1e")

        txt = scrolledtext.ScrolledText(
            root, wrap=tk.WORD,
            font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white",
            state=tk.DISABLED,
        )
        txt.pack(fill=tk.BOTH, expand=True)

        # Vorhandenen Puffer einmalig einfügen
        with _log_lock:
            snapshot = list(_log_parts)
        _seen = [len(snapshot)]
        txt.configure(state=tk.NORMAL)
        txt.insert(tk.END, "".join(snapshot))
        txt.configure(state=tk.DISABLED)
        txt.see(tk.END)

        def _poll():
            with _log_lock:
                total = len(_log_parts)
                if total > _seen[0]:
                    new = "".join(_log_parts[_seen[0]:total])
                    _seen[0] = total
                else:
                    new = None
            if new:
                txt.configure(state=tk.NORMAL)
                txt.insert(tk.END, new)
                txt.configure(state=tk.DISABLED)
                txt.see(tk.END)
            root.after(250, _poll)

        root.after(250, _poll)
        root.mainloop()

    threading.Thread(target=_build, daemon=True).start()


def _quit(icon, item):
    if _ngrok_proc:
        _ngrok_proc.terminate()
    icon.stop()
    os._exit(0)


def main():
    # Im frozen-Modus (Distribution) nur lokaler Betrieb, kein ngrok
    is_frozen = getattr(sys, "frozen", False)

    # Flask starten
    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()

    if not is_frozen and NGROK_ENABLED:
        # ngrok nur im Entwicklungsmodus starten
        threading.Thread(target=_run_ngrok, daemon=True).start()

    # Kurz warten, dann Browser öffnen
    def _delayed_open():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{APP_PORT}")

    threading.Thread(target=_delayed_open, daemon=True).start()

    # Tray-Icon erstellen
    if is_frozen:
        menu = pystray.Menu(
            pystray.MenuItem("Im Browser öffnen", _open_local, default=True),
            pystray.MenuItem("Konsole anzeigen", _show_console),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", _quit),
        )
        title = f"NotenApp {APP_VERSION} – localhost:{APP_PORT}"
    else:
        if NGROK_ENABLED:
            menu = pystray.Menu(
                pystray.MenuItem("Im Browser öffnen (ngrok)", _open_browser, default=True),
                pystray.MenuItem("Lokal öffnen (localhost)", _open_local),
                pystray.MenuItem("Konsole anzeigen", _show_console),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Beenden", _quit),
            )
            title = f"NotenApp {APP_VERSION} -> {NGROK_DOMAIN}"
        else:
            menu = pystray.Menu(
                pystray.MenuItem("Im Browser öffnen", _open_local, default=True),
                pystray.MenuItem("Konsole anzeigen", _show_console),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Beenden", _quit),
            )
            title = f"NotenApp {APP_VERSION} – localhost:{APP_PORT}"

    icon = pystray.Icon(
        name="NotenApp",
        icon=_make_icon(),
        title=title,
        menu=menu,
    )
    icon.run()


if __name__ == "__main__":
    main()
