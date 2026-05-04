"""
Tray-Launcher für NotenApp.
Startet den Flask-Server + ngrok-Tunnel im Hintergrund und zeigt ein Windows-Tray-Icon.
Rechtsklick → "Beenden" stoppt Server und App.
"""
import os
import sys
import io
import logging
import subprocess
import threading
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

# ngrok-Konfiguration
NGROK_DOMAIN = "enzyme-cognitive-nearly.ngrok-free.dev"
# ngrok.exe im gleichen Ordner wie tray.py suchen, sonst im PATH
_here = Path(__file__).parent
NGROK_EXE = str(_here / "ngrok.exe") if (_here / "ngrok.exe").exists() else "ngrok"

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
    # use_reloader=False und threaded=True für Tray-Betrieb
    flask_app.run(host="0.0.0.0", port=5000, use_reloader=False, threaded=True)


def _run_ngrok():
    """ngrok-Tunnel starten."""
    global _ngrok_proc
    _ngrok_proc = subprocess.Popen(
        [NGROK_EXE, "http", f"--domain={NGROK_DOMAIN}", "5000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_browser(icon, item):
    webbrowser.open(f"https://{NGROK_DOMAIN}")


def _open_local(icon, item):
    webbrowser.open("http://localhost:5000")


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
    # Flask starten
    t = threading.Thread(target=_run_flask, daemon=True)
    t.start()

    # ngrok starten
    threading.Thread(target=_run_ngrok, daemon=True).start()

    # Tray-Icon erstellen
    icon = pystray.Icon(
        name="NotenApp",
        icon=_make_icon(),
        title=f"NotenApp → {NGROK_DOMAIN}",
        menu=pystray.Menu(
            pystray.MenuItem("Im Browser öffnen (ngrok)", _open_browser, default=True),
            pystray.MenuItem("Lokal öffnen (localhost)", _open_local),
            pystray.MenuItem("Konsole anzeigen", _show_console),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Beenden", _quit),
        ),
    )
    icon.run()


if __name__ == "__main__":
    main()
