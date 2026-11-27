import json
import os
import time
from datetime import datetime

import serial
from django.core.management.base import BaseCommand
from django.db import OperationalError
from serial.tools import list_ports

from monitor.models import SensorNode
from monitor.serializers import MAX_DISTANCE_CM
from monitor.services import save_reading

# USB vendor IDs tried first: Espressif, Silicon Labs (CP210x), WCH (CH340), FTDI.
KNOWN_VIDS = {0x303A, 0x10C4, 0x1A86, 0x0403}


def parse_line(raw):
    """Turn one serial line into a clean dict, or None if it is not valid."""
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    node = data.get("node")
    cm = data.get("cm")
    float_state = data.get("float")

    if not isinstance(node, str) or not node:
        return None
    if cm is not None:
        if isinstance(cm, bool) or not isinstance(cm, (int, float)):
            return None
        if not 0 <= cm <= MAX_DISTANCE_CM:
            return None
    if float_state not in (0, 1):
        return None

    return {"node": node, "cm": cm, "float": bool(float_state)}


class Command(BaseCommand):
    help = "Read HydroHomie JSON lines from a serial port and save them as readings."

    def add_arguments(self, parser):
        parser.add_argument("--port", default="", help="COM port, for example COM5.")
        parser.add_argument(
            "--list", action="store_true", help="List serial ports and exit."
        )

    def log(self, message):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.stdout.write(f"[{stamp}] {message}")
        self.stdout.flush()

    def handle(self, *args, **options):
        if options["list"]:
            self.print_ports()
            return

        self.baud = int(os.getenv("SERIAL_BAUD", "115200"))
        self.save_interval = float(os.getenv("SERIAL_SAVE_INTERVAL", "10"))
        self.dtr_rts = os.getenv("SERIAL_DTR_RTS", "true").strip().lower() == "true"
        self.probe_seconds = 8
        self.data_timeout = 30
        self.last_saved = {}
        self.warned_nodes = set()

        preferred = (options["port"] or os.getenv("SERIAL_PORT", "")).strip()

        self.log("Serial bridge started. Press Ctrl+C to stop.")
        try:
            while True:
                ser = self.find_device(preferred)
                if ser is None:
                    self.log("No HydroHomie device found. Retrying in 5 seconds.")
                    time.sleep(5)
                    continue

                self.log(f"Connected on {ser.port}.")
                try:
                    self.read_loop(ser)
                except (serial.SerialException, OSError) as exc:
                    self.log(f"Serial error: {exc}")
                finally:
                    try:
                        ser.close()
                    except (serial.SerialException, OSError):
                        pass

                self.log("Reconnecting in 3 seconds.")
                time.sleep(3)
        except KeyboardInterrupt:
            self.log("Stopped.")

    def print_ports(self):
        ports = list(list_ports.comports())
        if not ports:
            self.stdout.write("No serial ports found.")
            return
        for port in ports:
            if port.vid is not None:
                ids = f"{port.vid:04X}:{port.pid:04X}"
            else:
                ids = "no USB ID"
            self.stdout.write(f"{port.device}  [{ids}]  {port.description}")

    def find_device(self, preferred):
        candidates = []
        if preferred:
            candidates.append(preferred)

        usb_ports = [p for p in list_ports.comports() if p.vid is not None]
        usb_ports.sort(key=lambda p: p.vid not in KNOWN_VIDS)
        for port in usb_ports:
            if port.device not in candidates:
                candidates.append(port.device)

        for device in candidates:
            ser = self.probe(device)
            if ser is not None:
                if preferred and device != preferred:
                    self.log(
                        f"Configured port {preferred} gave no valid data. Using {device}."
                    )
                return ser
        return None

    def probe(self, device):
        """Open a port and accept it only if it sends a valid HydroHomie line."""
        ser = serial.Serial()
        ser.port = device
        ser.baudrate = self.baud
        ser.timeout = 1
        if not self.dtr_rts:
            ser.dtr = False
            ser.rts = False

        try:
            ser.open()
        except (serial.SerialException, OSError):
            return None

        deadline = time.monotonic() + self.probe_seconds
        try:
            while time.monotonic() < deadline:
                if parse_line(ser.readline()) is not None:
                    return ser
        except (serial.SerialException, OSError):
            pass

        try:
            ser.close()
        except (serial.SerialException, OSError):
            pass
        return None

    def read_loop(self, ser):
        last_data = time.monotonic()
        while True:
            raw = ser.readline()
            now = time.monotonic()
            data = parse_line(raw) if raw else None

            if data is None:
                if now - last_data > self.data_timeout:
                    raise serial.SerialException(
                        f"No valid data for {self.data_timeout} seconds."
                    )
                continue

            last_data = now
            self.handle_reading(data, now)

    def handle_reading(self, data, now):
        node = SensorNode.objects.filter(node_id=data["node"], is_active=True).first()
        if node is None:
            if data["node"] == "HUB":
                return
            if data["node"] not in self.warned_nodes:
                self.warned_nodes.add(data["node"])
                self.log(
                    f"Node '{data['node']}' is unknown or inactive. "
                    "Add it in the admin. Its readings are skipped."
                )
            return

        previous = self.last_saved.get(node.node_id)
        float_changed = previous is not None and previous[1] != data["float"]
        due = previous is None or now - previous[0] >= self.save_interval
        if not (due or float_changed):
            return

        try:
            save_reading(
                node=node,
                distance_cm=data["cm"],
                float_triggered=data["float"],
            )
        except OperationalError as exc:
            self.log(f"Database error, reading skipped: {exc}")
            return

        self.last_saved[node.node_id] = (now, data["float"])
        self.log(
            f"Saved {node.node_id}: cm={data['cm']} float={int(data['float'])}"
        )