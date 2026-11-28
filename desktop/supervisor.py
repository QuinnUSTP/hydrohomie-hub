"""Starts and watches the three HydroHomie background services."""
import subprocess
import threading
import time

from dotenv import dotenv_values

from desktop.paths import BASE_DIR, DATA_DIR, LOG_DIR, NO_WINDOW, child_env, python_exe

SERVICES = {
    "web": ["serve.py"],
    "bridge": ["manage.py", "serial_bridge"],
    "publisher": ["manage.py", "publish_public"],
}


def publisher_enabled():
    value = dotenv_values(DATA_DIR / ".env").get("PUBLIC_PUBLISH_ENABLED") or ""
    return value.strip().lower() == "true"


class Service:
    def __init__(self, name, args):
        self.name, self.args = name, args
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
        cmd = [str(python_exe()), str(BASE_DIR / self.args[0]), *self.args[1:]]
        self.proc = subprocess.Popen(
            cmd, cwd=BASE_DIR, env=child_env(), stdout=self.log,
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
        self.services = {n: Service(n, a) for n, a in SERVICES.items()}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _start_services(self):
        for name, service in self.services.items():
            if name == "publisher" and not publisher_enabled():
                service.stop()
                service.state = "disabled"
            else:
                service.start()

    def start_all(self):
        self._start_services()
        if not self._thread.is_alive():
            self._thread.start()

    def restart_all(self):
        for service in self.services.values():
            service.stop()
        self._start_services()

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