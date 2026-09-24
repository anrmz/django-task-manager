"""Test-only settings.

Imports the real settings verbatim and swaps the password hasher for the
fast MD5 one. `check_password`/`set_password` behave identically, but the
per-test PBKDF2 cost (~3s per hashed user on this machine) disappears, so
the test suite runs in a few seconds instead of many minutes.

Only used with ``manage.py test --settings=taskmanager.settings_test`` —
never in the running app, and never on Vercel (which uses ``settings``).
"""

# flake8: noqa: F401,F403  (deliberate star import of the real settings)
from .settings import *  # noqa

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]