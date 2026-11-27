import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from serial.tools import list_ports

DEFAULT_FQBN = "esp32:esp32:esp32s3:CDCOnBoot=cdc"


class Command(BaseCommand):
    help = "Compile node/node.ino and upload it to the ESP32-S3."

    def add_arguments(self, parser):
        parser.add_argument("--port", default="", help="For example COM5.")
        parser.add_argument("--fqbn", default=DEFAULT_FQBN)
        parser.add_argument("--sketch", default="hydrohomie_node")

    def handle(self, *args, **options):
        cli = shutil.which("arduino-cli")
        if not cli:
            raise CommandError("arduino-cli not found. Install it and add it to PATH.")
        name = options["sketch"]
        sketch = Path(settings.BASE_DIR) / "firmware" / name
        if not (sketch / f"{name}.ino").exists():
            raise CommandError(f"Missing {sketch / (name + '.ino')}")
        port = options["port"] or self.find_port()
        fqbn = options["fqbn"]
        self.stdout.write(f"Compiling for {fqbn} ...")
        self.run([cli, "compile", "--fqbn", fqbn, str(sketch)])
        self.stdout.write(f"Uploading to {port} ...")
        self.run([cli, "upload", "-p", port, "--fqbn", fqbn, str(sketch)])
        self.stdout.write(self.style.SUCCESS("Done. Now run: python manage.py serial_bridge"))

    def find_port(self):
        found = [p.device for p in list_ports.comports() if p.vid == 0x303A]
        if len(found) != 1:
            raise CommandError(f"Expected one Espressif port, found {found}. Use --port.")
        return found[0]

    def run(self, cmd):
        if subprocess.run(cmd).returncode != 0:
            raise CommandError("Command failed. Read the output above.")