import os

from waitress import serve

# Local desktop mode by default. Set DJANGO_SETTINGS_MODULE to override.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hydrohomie.settings_desktop")

from hydrohomie.wsgi import application

THREADS = int(os.getenv("SERVER_THREADS", "8"))
PORT = int(os.getenv("HYDROHOMIE_PORT", "8000"))

if __name__ == "__main__":
    print(f"Open HydroHomie: http://127.0.0.1:{PORT}/dashboard/", flush=True)
    serve(application, host="127.0.0.1", port=PORT, threads=THREADS)