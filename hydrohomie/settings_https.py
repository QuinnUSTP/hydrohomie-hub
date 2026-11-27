from .settings import *

DEBUG = False

SECURE_SSL_REDIRECT = True
SECURE_SSL_HOST = "192.168.100.9:8443"

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [
    "https://192.168.100.9:8443",
    "https://localhost:8443",
    "https://127.0.0.1:8443",
]

# Waitress sets the WSGI scheme using headers from the trusted local proxy.
SECURE_PROXY_SSL_HEADER = None

# Leave HSTS off while testing local certificate trust.
SECURE_HSTS_SECONDS = 0