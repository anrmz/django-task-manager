# Django Task Manager

A professional, SaaS-style task manager built with Django. Server-rendered
templates, a from-scratch design system (light/dark themes), progressive
vanilla JavaScript, and strictly owner-scoped data.

Users register, log in, and manage **their own** tasks through a Today-style
workspace — My Day, Inbox, Upcoming, All Tasks — plus Projects, Tags,
Productivity insights and a complete password-recovery flow. Every query is
scoped to the signed-in user: another user's data is always a **404**, never a
leak.

The project runs identically in local development (SQLite, console email) and
in production (PostgreSQL, SMTP email, Gunicorn + WhiteNoise on Render, or the
WSGI entry point behind Vercel's functions + CDN).

---

## Features

- **Workspace views** — My Day (overdue / due today / next up / done today),
  Inbox, Upcoming (grouped, with jump-to-date), All Tasks (search,
  status/priority/project/tag filters, sorting, pagination), Completed.
- **Projects & tags** — organize tasks; every project/tag is owner-scoped.
- **Productivity** — honest stats derived from real rows (completion rate,
  streak, 7-day trend), no fake metrics.
- **Quick capture** — one primary add action (title-only to save, "More
  details" for the full form).
- **Command palette** — `Ctrl+K` / `/` to jump to any task or link; `N` starts
  a new task.
- **Instant toggle** — mark tasks done with an async POST, no page reload.
- **Full task CRUD** — create, view, edit, soft-delete to Trash, restore,
  permanent delete, subtasks.
- **Due date + time** — tasks can carry an optional time-of-day.
- **Light / dark theme** — system default, persistable per user, no flash.
- **Responsive** — sidebar → icon rail → drawer/bottom tab bar, 320–1920px.
- **Password recovery** — email → 6-digit code → new password. Codes are
  cryptographically random, stored only as salted SHA-256 hashes, expire,
  are single-use, rate-limited and brute-force bound; account existence is
  never revealed.
- **Tests** — 67 Django tests covering auth, CRUD, ownership, filters,
  quick-add, palette, project/tag scoping, subtasks, trash lifecycle,
  preferences and the full password-recovery flow.

---

## Technology stack

- **Python 3.13** (pinned via `.python-version`)
- **Django 6.1**
- **SQLite** (local development, zero-config) · **PostgreSQL** (production,
  via `DATABASE_URL`)
- **Gunicorn + WhiteNoise** (production serving/static files — no `runserver`)
- **Django Templates** (no JS framework) + modular CSS + vanilla JS

---

## Local development

Requirements: Python 3.13, git.

```bash
# 1. Clone
git clone https://github.com/anrmz/django-task-manager.git
cd django-task-manager

# 2. Virtual environment
python -m venv .venv

# 3. Activate
#    Windows (PowerShell):  .venv\Scripts\Activate.ps1
#    macOS / Linux:         source .venv/bin/activate

# 4. Dependencies
pip install -r requirements.txt

# 5. Database (SQLite created automatically; optional superuser for /admin/)
python manage.py migrate
python manage.py createsuperuser

# 6. Run
python manage.py runserver
```

Open http://127.0.0.1:8000/.

### Environment variables

Copy the template and edit as needed:

```bash
cp .env.example .env   # .env is gitignored — never commit it
```

Local development needs **nothing set** — defaults are functional (SQLite,
console email, DEBUG on). The `.env` file simply overrides them. The full list:

| Variable | Local default | Required in production |
|---|---|---|
| `SECRET_KEY` | dev-only fallback | **Yes** — strong random value |
| `DEBUG` | `True` | **Yes** — `False` |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` | **Yes** — your Render/custom domain(s) |
| `CSRF_TRUSTED_ORIGINS` | *(empty)* | **Yes** — `https://your-app.onrender.com` |
| `DATABASE_URL` | *(empty → SQLite)* | **Yes** — PostgreSQL URL |
| `SECURE_SSL_REDIRECT` / `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | auto (secure when `DEBUG=False`) | Optional override |
| `SECURE_HSTS_SECONDS` | `0` (dev) / `31536000` (prod) | Optional — set `0` to disable HSTS |
| `EMAIL_BACKEND` | console backend | **Yes** for real email |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` | — | Required for SMTP |

---

## Database setup

- **Local:** leave `DATABASE_URL` empty — a `db.sqlite3` file is used. Run
  `python manage.py migrate`.
- **Production:** set `DATABASE_URL` (e.g. `postgresql://user:pass@host:5432/name`).
  The same codebase uses it automatically; SQLite support stays untouched for
  development.

---

## Email / password reset

All email settings come from environment variables — **no SMTP credentials are
recorded in source control**.

- **Local:** the default **console backend** prints every outgoing message
  (including password-reset codes) to the server terminal. Nothing to configure.
- **Production:** set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
  plus the `EMAIL_*` variables. If `DEBUG=False` with the console backend
  still selected, Django **refuses to start** rather than silently dropping
  email. For Gmail use an **App Password**, never your account password.

> Password-reset email is only delivered once a real SMTP backend is
> configured — verify it before promising users email-based recovery.

---

## Static files

`collectstatic` gathers everything into `staticfiles/` (gitignored):

```bash
python manage.py collectstatic --noinput
```

- **Development:** Django serves directly from `static/`.
- **Production:** WhiteNoise serves from `STATIC_ROOT` with fingerprinting
  (`whitenoise.storage.CompressedManifestStaticFilesStorage`), so no separate
  web server configuration is required. On Vercel, `collectstatic` runs
  automatically and the collected files are served from the CDN at `/static/`
  (absolute `STATIC_URL`, so assets load correctly from nested routes like
  `/tasks/1/edit/`).

---

## Tests

```bash
python manage.py test tasks
```

The suite also runs a production-safety check:

```bash
python manage.py check --deploy
```

---

## Production / deployment preparation

The repository is deployment-ready: PostgreSQL via `DATABASE_URL`, Gunicorn
(`gunicorn taskmanager.wsgi:application`), WhiteNoise static serving,
`build.sh` build script, and an optional `render.yaml` blueprint, plus a
minimal `vercel.json` for deploying on Vercel's zero-config Django support.
**The app has not been deployed yet** — the steps below are what a first
deployment requires.

### Render (when you're ready)

1. Create a new **Web Service** from this repository (or "New Blueprint" with
   `render.yaml`).
2. Build command: `./build.sh` · Start command: `gunicorn taskmanager.wsgi:application --access-logfile -`
3. Attach a PostgreSQL database (free tier works for evaluation) so
   `DATABASE_URL` is injected.
4. Set environment variables (see table above — most importantly `DEBUG=False`
   and a generated `SECRET_KEY`, which `render.yaml` creates automatically).
5. After the first deploy, replace the placeholder SMTP values with real
   credentials and set `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` to the assigned
   `*.onrender.com` URL (or a custom domain).

### Vercel (when you're ready)

Vercel detects Django automatically (it finds `manage.py`, discovers the
settings module and reads `WSGI_APPLICATION`). It runs `collectstatic` and
serves the collected files from the CDN at `/static/`; every other route hits
the single WSGI function configured in `vercel.json`.

Database migrations are applied automatically on every deployment: the Build
Command defined in `pyproject.toml` (`[tool.vercel.scripts].build`) runs
`python manage.py migrate --noinput` once during the build, before the new
code serves traffic. Migrations are never run per HTTP request.

1. Import the repo into Vercel — no Build Command or Output directory is
   needed (zero-config Django support). Do **not** set a Build Command in the
   Vercel dashboard: one there would override the `pyproject.toml` build
   script that applies migrations.
2. `DATABASE_URL`: attach a managed PostgreSQL provider, e.g. the **Neon**
   integration, which injects `DATABASE_URL` automatically (Supabase or any
   Postgres provider also works).
3. Set the environment variables listed in the table above (`SECRET_KEY`,
   `DEBUG=False`, `EMAIL_*`) in **Project Settings → Environment Variables**
   for the Production, Preview, and Development scopes. `SECRET_KEY` and an
   SMTP `EMAIL_BACKEND` are required for the settings to load (and therefore
   for `migrate`) once `DEBUG=False`.
4. `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`: only your **custom domains** need to
   be listed. Every `*.vercel.app` deployment/branch/production hostname is
   merged in automatically from Vercel's system environment variables, and
   `DEBUG` defaults to `False` whenever `VERCEL=1` is present.

> Because `DATABASE_URL` is a build/runtime variable that rarely changes, you
> can also keep it in `.env` locally (gitignored) — the Vercel dashboard value
> always wins at runtime.

### Production do's and don'ts

- **Never** run `python manage.py runserver` in production.
- **Never** commit `.env`, `db.sqlite3`, or any credentials (all gitignored).
- **Never** use `DEBUG=True` or a weak/placeholder `SECRET_KEY` in production —
  the app blocks startup with a clear error if the key is missing or weak.

---

## License

Educational project — free to use for your coursework.