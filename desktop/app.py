import ctypes
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import pystray
import webview
from PIL import Image, ImageDraw

from desktop.supervisor import DATA_DIR, LOG_DIR, Supervisor

PORT = int(os.getenv("HYDROHOMIE_PORT", "8000"))
URL = f"http://127.0.0.1:{PORT}/dashboard/"
TITLE = "HydroHomie Control Center"

GREEN, AMBER, RED = (46, 160, 67, 255), (219, 153, 0, 255), (207, 34, 46, 255)

SPLASH = ("<body style='font-family:Segoe UI,sans-serif;display:grid;place-items:center;"
          "height:100vh;margin:0;color:#0b2545'><h2>Starting HydroHomie...</h2></body>")
FAILED = ("<body style='font-family:Segoe UI,sans-serif;padding:3rem;color:#0b2545'>"
          "<h2>HydroHomie could not start</h2><p>Right-click the droplet icon near the clock, "
          "choose Open logs folder, and send the files to your support person.</p></body>")


def message(text, flags=0x40):
    return ctypes.windll.user32.MessageBoxW(0, text, TITLE, flags)


def already_running():
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\HydroHomieControlCenter")
    return ctypes.windll.kernel32.GetLastError() == 183


def make_icon(dot):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([12, 24, 52, 64], fill=(20, 121, 201, 255))
    d.polygon([(32, 2), (14, 42), (50, 42)], fill=(20, 121, 201, 255))
    d.ellipse([38, 38, 62, 62], fill=dot, outline=(255, 255, 255, 255), width=3)
    return img


def overall(status):
    if status["web"] != "running":
        return RED
    if any(value != "running" for value in status.values()):
        return AMBER
    return GREEN


def wait_for_web(timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/robots.txt", timeout=2)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(1)
    return False


class App:
    def __init__(self):
        self.supervisor = Supervisor()
        self.quitting = False
        self.window = webview.create_window(
            TITLE, html=SPLASH, width=1280, height=800, min_size=(900, 600),
            hidden="--background" in sys.argv)
        self.window.events.closing += self.on_closing
        self.tray = pystray.Icon("hydrohomie", make_icon(AMBER), TITLE, pystray.Menu(
            pystray.MenuItem("Open HydroHomie", self.open_window, default=True),
            pystray.MenuItem(self.status_text, None, enabled=False),
            pystray.MenuItem("Restart services", self.restart),
            pystray.MenuItem("Open logs folder", self.open_logs),
            pystray.MenuItem("Quit", self.quit)))

    def status_text(self, item):
        s = self.supervisor.status()
        return f"Web {s['web']} | Sensors {s['bridge']} | Public {s['publisher']}"

    def on_closing(self):
        if self.quitting:
            return True
        self.window.hide()
        return False

    def open_window(self, *_):
        self.window.show()
        self.window.restore()

    def restart(self, *_):
        for service in self.supervisor.services.values():
            service.stop()
            service.start()

    def open_logs(self, *_):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(LOG_DIR)

    def quit(self, *_):
        answer = message(
            "If you quit, HydroHomie stops reading the sensors and stops updating the "
            "public website.\n\nQuit anyway?", 0x04 | 0x30 | 0x40000)
        if answer != 6:
            return
        self.quitting = True
        self.tray.stop()
        self.supervisor.stop_all()
        self.window.destroy()

    def watch(self):
        last = None
        while not self.quitting:
            color = overall(self.supervisor.status())
            if color != last:
                self.tray.icon = make_icon(color)
                last = color
            time.sleep(2)

    def on_started(self):
        self.supervisor.start_all()
        self.tray.run_detached()
        threading.Thread(target=self.watch, daemon=True).start()
        if wait_for_web():
            self.window.load_url(URL)
        else:
            self.window.load_html(FAILED)


def main():
    if already_running():
        message("HydroHomie is already running. Look for the droplet icon near the clock.")
        return
    app = App()
    webview.start(app.on_started, private_mode=False, storage_path=str(DATA_DIR / "webview"))
    app.supervisor.stop_all()


if __name__ == "__main__":
    main()