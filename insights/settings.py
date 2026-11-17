"""The platform's Django settings.

Everything particular to one installation -- database, secret key, the Anthropic key,
the platform's address -- is read from a JSON file outside the repository, the way
Frappe's site_config.json was:

    INSIGHTS_CONFIG=/home/insights/insights.json   (default: ./insights.json)

    {
      "secret_key": "...",                 # Django's; long and random
      "encryption_key": "...",             # Fernet key for stored passwords (secrets.py)
      "db": {"engine": "mysql", "name": "insights", "user": "insights",
             "password": "...", "host": "127.0.0.1", "port": 3306},
      "allowed_hosts": ["insights.example.com"],
      "secure_cookies": true,
      "command_center_anthropic_key": "sk-ant-...",
      "command_center_ai_provider": "claude"
    }

Every key in that file is also what the business logic reads as frappe.conf.get(...),
so the command_center_* settings it always used keep working unchanged. Without a db
entry the platform runs on a local SQLite file -- fine for a laptop, not for
production.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("INSIGHTS_CONFIG", BASE_DIR / "insights.json"))


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


CONFIG = _load_config()

# The business logic imports `frappe`. That name is now insights.compat -- the
# platform's own layer, with no Frappe installed -- and it must be in place before
# any command_center module is imported.
from insights import compat  # noqa: E402

compat.install(CONFIG)

SECRET_KEY = CONFIG.get("secret_key") or "insecure-development-key-change-me"
DEBUG = bool(CONFIG.get("debug", not CONFIG.get("secret_key")))
ALLOWED_HOSTS = CONFIG.get("allowed_hosts") or (["*"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = CONFIG.get("csrf_trusted_origins") or [
    f"https://{h}" for h in ALLOWED_HOSTS if h not in ("*",)]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "insights.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "insights.urls"
WSGI_APPLICATION = "insights.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

_db = CONFIG.get("db") or {}
if _db.get("engine") == "mysql":
    import pymysql

    # Django 5.2 checks the MySQLdb driver's version; PyMySQL, a pure-Python driver that
    # needs no compiler or client library on the server, stands in for it.
    pymysql.version_info = (2, 2, 7, "final", 0)
    pymysql.install_as_MySQLdb()
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": _db.get("name", "insights"),
        "USER": _db.get("user", "insights"),
        "PASSWORD": _db.get("password", ""),
        "HOST": _db.get("host", "127.0.0.1"),
        "PORT": str(_db.get("port", 3306)),
        "OPTIONS": {"charset": "utf8mb4", "init_command": "SET sql_mode='STRICT_TRANS_TABLES'"},
        "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": _db.get("path") or str(BASE_DIR / "insights.sqlite3"),
        "OPTIONS": {"timeout": 30},
    }}

# "aux": a second connection for what must outlive a request's rollback -- the error log
# and the shared cache (a question's progress, load locks). On MariaDB it is the same
# database; on a local SQLite file it is a file of its own, because SQLite lets one
# connection write at a time and the request's own transaction would block it.
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["aux"] = {"ENGINE": "django.db.backends.sqlite3",
                        "NAME": str(Path(DATABASES["default"]["NAME"]).with_suffix(".aux.sqlite3")),
                        "OPTIONS": {"timeout": 30}}
    AUX_SEPARATE = True
    # The test databases are files, as the real ones are, not SQLite's shared in-memory
    # database: a screen reads on several threads at once (command_center/speed.py), and
    # in memory SQLite refuses a second thread's write outright ("table is locked")
    # instead of waiting its turn.
    import tempfile as _tempfile
    for _alias in ("default", "aux"):
        DATABASES[_alias]["TEST"] = {"NAME": os.path.join(
            _tempfile.gettempdir(), f"insights-test-{os.getpid()}-{_alias}.sqlite3")}
else:
    DATABASES["aux"] = dict(DATABASES["default"])
    AUX_SEPARATE = False
DATABASE_ROUTERS = ["insights.core.routers.AuxRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Shared by every web worker and the scheduler process: a table, so no Redis is needed.
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
    "LOCATION": "cc_cache",
    "OPTIONS": {"MAX_ENTRIES": 20000},
}}
# Keys such as "cc:fields:<business>:Sales Invoice" hold spaces, which only memcached
# minds; the platform's cache is a database table, so Django's warning is noise.
import warnings  # noqa: E402

from django.core.cache.backends.base import CacheKeyWarning  # noqa: E402

warnings.simplefilter("ignore", CacheKeyWarning)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# A set-password link (insights/core/invite.py) works once, for this long: Django's
# PasswordResetTokenGenerator reads it. The email and the page say the hours from here.
PASSWORD_RESET_TIMEOUT = 72 * 3600

# Sign-in sessions: a cookie the page's scripts cannot read, sent only to this site.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(CONFIG.get("session_hours", 12)) * 3600
SECURE = bool(CONFIG.get("secure_cookies", not DEBUG))
SESSION_COOKIE_SECURE = SECURE
CSRF_COOKIE_SECURE = SECURE
# The interface sends its token as X-Frappe-CSRF-Token (frontend/src/api/client.js).
CSRF_HEADER_NAME = "HTTP_X_FRAPPE_CSRF_TOKEN"
CSRF_FAILURE_VIEW = "insights.core.views.csrf_failure"
LOGIN_URL = "/sign-in"
if SECURE:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LANGUAGE_CODE = "en-gb"
# Frappe stored naive local times; so does the business logic. Accra is UTC+0.
TIME_ZONE = CONFIG.get("time_zone", "Africa/Accra")
USE_I18N = False
USE_TZ = False

STATIC_URL = "/static/"
STATIC_ROOT = CONFIG.get("static_root") or str(BASE_DIR / "staticfiles")
# The built interface and the app's images, served where the pages expect them.
APP_PUBLIC = BASE_DIR / "command_center" / "public"

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": CONFIG.get("log_level", "INFO")},
}
