import secrets
import subprocess

from desktop.paths import BASE_DIR, DATA_DIR, LOG_DIR, NO_WINDOW, child_env, python_exe

ENV_TEMPLATE = """SECRET_KEY={secret}
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,localhost
PUBLIC_PUBLISH_ENABLED=False
PUBLIC_SITE_URL=
PUBLIC_SITE_TOKEN=
SMS_ENABLED=False
"""


def prepare():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env_file = DATA_DIR / ".env"
    if not env_file.exists():
        env_file.write_text(ENV_TEMPLATE.format(secret=secrets.token_urlsafe(50)), encoding="utf-8")
    with open(LOG_DIR / "migrate.log", "ab") as log:
        result = subprocess.run(
            [str(python_exe()), str(BASE_DIR / "manage.py"), "migrate", "--noinput"],
            cwd=BASE_DIR, env=child_env(), stdout=log, stderr=subprocess.STDOUT,
            creationflags=NO_WINDOW)
    return result.returncode == 0