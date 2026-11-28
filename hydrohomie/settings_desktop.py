from .settings import *

DEBUG = False

# One PC, local only: plain HTTP on this computer, no certificates.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = None
SECURE_HSTS_SECONDS = 0

FIRST_RUN_SETUP = True