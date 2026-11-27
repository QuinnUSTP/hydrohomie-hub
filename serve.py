import os

from waitress import serve

# Use the HTTPS configuration only for this server process.
os.environ["DJANGO_SETTINGS_MODULE"] = "hydrohomie.settings_https"

from hydrohomie.wsgi import application

THREADS = int(os.getenv("SERVER_THREADS", "8"))

if __name__ == "__main__":
    print("Waitress backend: http://127.0.0.1:8000", flush=True)
    print("Open HydroHomie: https://192.168.100.9:8443", flush=True)

    serve(
        application,
        host="127.0.0.1",
        port=8000,
        threads=THREADS,
        trusted_proxy="127.0.0.1",
        trusted_proxy_headers={"x-forwarded-proto"},
        clear_untrusted_proxy_headers=True,
    )