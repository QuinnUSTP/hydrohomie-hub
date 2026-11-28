"""Where the app lives and where its data lives."""
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _default_data_dir():
    # Installed layout: <install>\python and <install>\app. Data goes to ProgramData.
    if (BASE_DIR.parent / "python" / "python.exe").exists():
        return Path(os.getenv("PROGRAMDATA", r"C:\ProgramData")) / "HydroHomie"
    return BASE_DIR


DATA_DIR = Path(os.getenv("HYDROHOMIE_DATA_DIR") or _default_data_dir())
LOG_DIR = DATA_DIR / "logs"
os.environ["HYDROHOMIE_DATA_DIR"] = str(DATA_DIR)


def python_exe():
    # Child services need python.exe even when the app itself runs under pythonw.exe.
    candidate = Path(sys.executable).with_name("python.exe")
    return candidate if candidate.exists() else Path(sys.executable)


def child_env():
    return dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")