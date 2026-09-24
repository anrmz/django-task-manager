"""
Django settings for the Task Manager project.

Environment-aware so the same codebase runs in local development (SQLite +
console email, permissive-ish defaults) and in production (PostgreSQL via
``DATABASE_URL``, WhiteNoise-served static files, HTTPS-only cookies).

Configuration is read from environment variables — supported names are the
plain form documented in ``.env.example`` (``SECRET_KEY``, ``DEBUG``,
``ALLOWED_HOSTS``, ``CSRF_TRUSTED_ORIGINS``, ``DATABASE_URL``…) with the older
``DJANGO_*`` aliases still accepted.  A tiny zero-dependency loader reads a
gitignored ``.env`` file; real shell environment variables always win.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Tiny dependency-free ``.env`` loader (KEY=VALUE lines, ``#`` comments).

    Existing environment variables always win, so values exported in the shell
    take precedence over the file. Blank values are ignored so an empty
    ``EMAIL_BACKEND=`` does not override the console default. Never reads
    secrets out of the repo: the real file is gitignored.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("'\"")
        if not value:
            continue
        os.environ.setdefault(key.strip(), value)


def _get_env(name, default=None):
    """Read ``NAME`` from the environment, falling back to the legacy
    ``DJANGO_NAME`` alias so older setups keep working."""
    value = os.environ.get(name)
    if value is None:
        value = os.environ.get(f"DJANGO_{name}")
    return default if value is None else value


def _env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


_load_env_file(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
# Production refuses to start without a strong explicit value.
SECRET_KEY = _get_env("SECRET_KEY")
DEBUG = _env_bool(_get_env("DEBUG"), default=True)

if not SECRET_KEY and DEBUG:
    # Development-only fallback so the app runs out of the box. Never use this
    # value anywhere public.
    SECRET_KEY = "django-insecure-local-development-key-1x5vq($)k7nw%m&9zp#4s@2!t8h6g3e0r"
if not SECRET_KEY or (not DEBUG and (len(SECRET_KEY) < 50 or "django-insecure-" in str(SECRET_KEY))):
    raise ImproperlyConfigured(
        "SECRET_KEY must be set to a strong, unique value via the SECRET_KEY "
        "environment variable when DEBUG=False. Generate one with:\n"
        "  python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in (_get_env("ALLOWED_HOSTS") or "127.0.0.1,localhost").split(",")
    if host.strip()
]

# Trusted origins for cross-site requests (CSRF) — assign the real Render /
# custom domain here in production, e.g. "https://app.yourapp.onrender.com".
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in (_get_env("CSRF_TRUSTED_ORIGINS") or "").split(",")
    if origin.strip()
]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local app
    "tasks.apps.TasksConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves static files efficiently in production (and freely in
    # development). Must sit close to the top, after SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "taskmanager.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "tasks.context_processors.nav",
            ],
        },
    },
]

WSGI_APPLICATION = "taskmanager.wsgi.application"


# Database
# ---------------------------------------------------------------------------
# Local development keeps the zero-config SQLite database. When ``DATABASE_URL``
# is provided (the production case, e.g. a Render PostgreSQL URL) it is parsed
# with ``dj-database-url`` and used instead. Development data is never migrated
# automatically.
DATABASE_URL = _get_env("DATABASE_URL")
if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/
LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

# In production static files are collected into ``STATIC_ROOT`` and served by
# WhiteNoise with manifest-hashed filenames (fingerprinting). Development keeps
# Django's plain staticfiles backend so ``{% static %}`` works without running
# ``collectstatic`` first.
if not DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }


# Authentication
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "my_day"
LOGOUT_REDIRECT_URL = "login"


# Security
# ---------------------------------------------------------------------------
# HTTPS / secure-cookie settings are intentionally environment-aware: they can
# be forced via SECURE_* variables, and otherwise default to ON in production
# and OFF in development so local HTTP testing keeps working. HSTS is
# configurable through ``SECURE_HSTS_SECONDS`` (0 disables it) — enable HSTS
# only once you know the exact domain(s) the app will be served from.
if not DEBUG:
    # Render and other TLS-terminating proxies forward the original scheme in
    # this header. Never trust it in development where clients could spoof it.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = _env_bool(_get_env("SECURE_SSL_REDIRECT"), default=not DEBUG)
SESSION_COOKIE_SECURE = _env_bool(_get_env("SESSION_COOKIE_SECURE"), default=not DEBUG)
CSRF_COOKIE_SECURE = _env_bool(_get_env("CSRF_COOKIE_SECURE"), default=not DEBUG)

SECURE_HSTS_SECONDS = max(
    0,
    int(
        _get_env("SECURE_HSTS_SECONDS")
        or ("31536000" if not DEBUG else "0")
    ),
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

# Clickjacking: DENY by default via X-Frame-Options middleware.
X_FRAME_OPTIONS = "DENY"


# Email
# ---------------------------------------------------------------------------
# Fully environment-driven — no SMTP credentials live in source control.
#
# Local development defaults to the console backend, which prints every
# message (including password-reset codes) to the terminal so nothing needs
# to be configured to try the feature. To send real email, set the EMAIL_*
# variables in `.env` (see `.env.example`) and the backend switches to SMTP.
# Production refuses to run on the console backend so email is never silently
# dropped.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _env_bool(os.environ.get("EMAIL_USE_TLS"), default=False)
EMAIL_USE_SSL = _env_bool(os.environ.get("EMAIL_USE_SSL"), default=False)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "Task Manager <noreply@localhost>"
)

if not DEBUG and EMAIL_BACKEND.endswith("console.EmailBackend"):
    raise ImproperlyConfigured(
        "Console email backend cannot be used in production. "
        "Set EMAIL_BACKEND (and EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD) "
        "via environment variables in .env."
    )

# Default primary key field type
# https://docs.djangoproject.com/en/6.1/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"