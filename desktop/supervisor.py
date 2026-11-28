"""Starts and watches the three HydroHomie background services."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("HYDROHOMIE_DATA_DIR", BASE_DIR))
LOG_DIR = DATA_DIR / "logs"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SERVICES = {
    "web": [sys.executable, str(BASE_DIR / "serve.py")],
    "bridge": [sys.executable, str(BASE_DIR / "manage.py"), "serial_bridge"],
    "publisher": [sys.executable, str(BASE_DIR / "manage.py"), "publish_public"],
}


class Service:
    def __init__(self, name, cmd):
        self.name, self.cmd = name, cmd
        self.proc, self.log = None, None
        self.wanted = False
        self.state = "stopped"
        self.delay = 2
        self.next_start = 0.0
        self.started_at = 0.0
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            self.wanted = True
            self.delay, self.next_start = 2, 0.0

    def stop(self):
        with self.lock:
            self.wanted = False
            self._kill()
            self.state = "stopped"

    def tick(self):
        with self.lock:
            if not self.wanted:
                return
            now = time.monotonic()
            if self.proc and self.proc.poll() is None:
                if now - self.started_at > 30:
                    self.delay = 2
                return
            if self.proc:
                self._kill()
                self.state = "restarting"
                self.next_start = now + self.delay
                self.delay = min(self.delay * 2, 60)
            if now >= self.next_start:
                self._launch()

    def _launch(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log = open(LOG_DIR / f"{self.name}.log", "ab")
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                   HYDROHOMIE_DATA_DIR=str(DATA_DIR))
        self.proc = subprocess.Popen(
            self.cmd, cwd=BASE_DIR, env=env, stdout=self.log,
            stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        self.started_at = time.monotonic()
        self.state = "running"

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.log:
            self.log.close()
            self.log = None


class Supervisor:
    def __init__(self):
        self.services = {n: Service(n, c) for n, c in SERVICES.items()}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start_all(self):
        for service in self.services.values():
            service.start()
        if not self._thread.is_alive():
            self._thread.start()

    def stop_all(self):
        self._stop.set()
        for service in self.services.values():
            service.stop()

    def status(self):
        return {name: s.state for name, s in self.services.items()}

    def _run(self):
        while not self._stop.is_set():
            for service in self.services.values():
                service.tick()
            self._stop.wait(1)