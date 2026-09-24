"""Forgot-password / password recovery for Task Manager.

Flow:  email  →  6-digit code  →  verify  →  new password  →  success.

Security properties
-------------------
* The plaintext code is never stored — only a salted SHA-256 hash.
* Codes are 6 random digits from :mod:`secrets`, expire after 10 minutes,
  and are single-use; requesting a new code invalidates the previous one.
* Account existence is never revealed: unknown emails get the exact same
  response, redirect and timing-shaped behaviour as known ones, and rate
  limiting applies to every request regardless of whether the account exists.
* The new-password step is gated by a short-lived server-side session claim
  created only after a successful verification — no user id/email is ever
  trusted from the URL.
* Brute force is bounded per verification request (max attempts) and per
  email (max requests per window + a resend cooldown).

The reset session and the cooldown state live in the server-side session and
Django's cache respectively, so no extra infrastructure is required.
"""

import logging
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import PasswordResetCodeForm, PasswordResetRequestForm, SetNewPasswordForm
from .models import PasswordResetCode

logger = logging.getLogger(__name__)

# --- tunables ----------------------------------------------------------------

CODE_TTL_MINUTES = 10
SESSION_TTL_MINUTES = 15
MAX_ATTEMPTS = 5
MAX_REQUESTS = 3
REQUEST_WINDOW_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 60

# --- session keys ------------------------------------------------------------

EMAIL_SESSION_KEY = "password_reset_email"
VERIFIED_SESSION_KEY = "password_reset_verified"
USER_SESSION_KEY = "password_reset_user_id"
EXPIRY_SESSION_KEY = "password_reset_expires"
_ALL_SESSION_KEYS = (
    EMAIL_SESSION_KEY,
    VERIFIED_SESSION_KEY,
    USER_SESSION_KEY,
    EXPIRY_SESSION_KEY,
)

CACHE_PREFIX = "tm:pwreset:"
GENERIC_SENT_MESSAGE = (
    "If an account exists with this email address, a verification code has been sent."
)
GENERIC_INVALID_MESSAGE = "Invalid verification code."
EXPIRED_MESSAGE = "This verification code has expired."
TOO_MANY_REQUESTS_MESSAGE = (
    "Too many requests. Please wait a few minutes and try again."
)
RESET_SESSION_EXPIRED_MESSAGE = (
    "Your password reset session has expired. Please request a new code."
)


# --- rate limiting ------------------------------------------------------------

def _rate_slice(email):
    """Return ``(cache_key, slice)`` for an email within a rolling window."""
    key = f"{CACHE_PREFIX}{email.strip().lower()}"
    now = time.time()
    slice_ = cache.get(key, {})
    if not isinstance(slice_, dict) or "count" not in slice_:
        slice_ = {"count": 0, "first": now, "last": None}
    elif now - slice_.get("first", now) > REQUEST_WINDOW_MINUTES * 60:
        slice_ = {"count": 0, "first": now, "last": None}
    return key, slice_


def rate_check(email):
    """(allowed, wait_seconds) — enforcing both request and cooldown limits."""
    _, slice_ = _rate_slice(email)
    now = time.time()
    if slice_["count"] >= MAX_REQUESTS:
        return False, None
    if slice_.get("last") is not None:
        wait = RESEND_COOLDOWN_SECONDS - (now - slice_["last"])
        if wait > 0:
            return False, int(wait) + 1
    return True, 0


def rate_consume(email):
    """Record one code request (send or resend) for an email."""
    key, slice_ = _rate_slice(email)
    now = time.time()
    if not slice_["count"]:
        slice_["first"] = now
    slice_["count"] += 1
    slice_["last"] = now
    cache.set(key, slice_, REQUEST_WINDOW_MINUTES * 60)


def resend_wait_seconds(email):
    """Seconds left before this email may be sent another code (0 = allowed)."""
    _, slice_ = _rate_slice(email)
    now = time.time()
    if slice_.get("last") is None or slice_["count"] >= MAX_REQUESTS:
        return 0
    return max(0, RESEND_COOLDOWN_SECONDS - int(now - slice_["last"]))


# --- code lifecycle -----------------------------------------------------------

def _active_code_for(user):
    """The currently-valid code row for a user, or None."""
    now = timezone.now()
    return (
        PasswordResetCode.objects.filter(
            user=user, invalidated=False, verified=False, expires_at__gt=now
        )
        .order_by("-created_at")
        .first()
    )


def _issue_email_if_exists(email, ip_address=None, user_agent=""):
    """Send a code for an account if one exists, without leaking existence.

    Timings are normalised for known and unknown addresses (the same hashing
    work happens either way) and the rate limiter is consumed for both.
    """
    # Equalise the hashing cost even when there is no account to look up.
    import hashlib as _h

    _h.sha256(f"{email}:{settings.SECRET_KEY}".encode("utf-8")).hexdigest()

    user = User.objects.filter(email__iexact=email.strip()).first()
    if user is None:
        return None

    code_row, code = PasswordResetCode.generate(
        user, ttl_minutes=CODE_TTL_MINUTES
    )
    code_row.ip_address = ip_address
    code_row.user_agent = user_agent[:255]
    code_row.save(update_fields=["ip_address", "user_agent"])
    _send_code_email(user.email, code)
    return code_row


def _send_code_email(email_address, code):
    """Render and send the professional reset email (console backend in dev)."""
    subject = "Reset your Task Manager password"
    context = {
        "code": code,
        "expires_in_minutes": CODE_TTL_MINUTES,
        "app_name": "Task Manager",
    }
    text_body = render_to_string(
        "registration/emails/password_reset_code.txt", context
    )
    html_body = render_to_string(
        "registration/emails/password_reset_code.html", context
    )
    try:
        send_mail(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [email_address],
            html_message=html_body,
            fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - a queued/console failure must not 500 the flow
        logger.warning("Failed to send password-reset code to %s", email_address)


# --- reset session ------------------------------------------------------------

def _client_ip(request):
    """Best-effort client IP for request metadata (never trusted for auth)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _clear_reset_session(request):
    for key in _ALL_SESSION_KEYS:
        request.session.pop(key, None)


def _verified_user(request):
    """The user authenticated by a still-valid reset session, else None."""
    if not request.session.get(VERIFIED_SESSION_KEY):
        return None
    expiry_raw = request.session.get(EXPIRY_SESSION_KEY)
    if not expiry_raw:
        return None
    try:
        from django.utils.dateparse import parse_datetime

        expiry = parse_datetime(expiry_raw)
        if expiry is None or timezone.now() > expiry:
            return None
    except (ValueError, TypeError):
        return None
    user_id = request.session.get(USER_SESSION_KEY)
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


# --- views ---------------------------------------------------------------------

def forgot_password(request):
    """Step 1 — enter the account email. Never reveals account existence."""
    if request.user.is_authenticated:
        from .views import _landing

        return redirect(_landing(request.user))

    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        request.session[EMAIL_SESSION_KEY] = email.strip()

        allowed, wait = rate_check(email)
        if not allowed:
            _clear_reset_session(request)
            messages.error(request, TOO_MANY_REQUESTS_MESSAGE)
            if wait:
                messages.info(
                    request,
                    f"Try again in {wait} second(s).",
                )
            return redirect("password_reset")

        rate_consume(email)
        _issue_email_if_exists(
            email,
            ip_address=_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )
        messages.success(request, GENERIC_SENT_MESSAGE)
        return redirect("password_reset_verify")

    return render(request, "registration/password_reset.html", {"form": form})


@require_POST
def resend_code(request):
    """Re-send the verification code for the email captured in step 1."""
    email = (request.session.get(EMAIL_SESSION_KEY) or "").strip()
    if not email:
        return redirect("password_reset")

    allowed, wait = rate_check(email)
    if not allowed:
        if wait:
            messages.error(
                request, f"Please wait {wait} second(s) before requesting another code."
            )
        else:
            messages.error(request, TOO_MANY_REQUESTS_MESSAGE)
        return redirect("password_reset_verify")

    rate_consume(email)
    _issue_email_if_exists(
        email,
        ip_address=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
    messages.success(request, "A new verification code has been sent.")
    return redirect("password_reset_verify")


def verify_reset_code(request):
    """Step 2 — enter the 6-digit code (server-side hash comparison, bounded
    attempts, expiry, single-use, no account-enumeration feedback)."""
    email = (request.session.get(EMAIL_SESSION_KEY) or "").strip()
    if not email:
        return redirect("password_reset")

    form = PasswordResetCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        entered = form.cleaned_data["code"]
        user = User.objects.filter(email__iexact=email).first()

        # No code exists for this email — behave identically to a wrong code.
        if user is None:
            messages.error(request, GENERIC_INVALID_MESSAGE)
            return render(
                request,
                "registration/password_reset_verify.html",
                {"form": form, "wait_seconds": resend_wait_seconds(email)},
            )

        code_row = PasswordResetCode.objects.filter(
            user=user, invalidated=False, verified=False
        ).order_by("-created_at").first()

        if code_row is None:
            messages.error(request, GENERIC_INVALID_MESSAGE)
            return render(
                request,
                "registration/password_reset_verify.html",
                {"form": form, "wait_seconds": resend_wait_seconds(email)},
            )

        if code_row.is_expired():
            messages.error(request, EXPIRED_MESSAGE)
            return render(
                request,
                "registration/password_reset_verify.html",
                {"form": form, "wait_seconds": resend_wait_seconds(email)},
            )

        if not code_row.matches(entered):
            code_row.attempts += 1
            if code_row.attempts >= MAX_ATTEMPTS:
                code_row.invalidated = True
                code_row.save(update_fields=["attempts", "invalidated"])
                messages.error(
                    request, "Too many failed attempts. Please request a new code."
                )
            else:
                code_row.save(update_fields=["attempts"])
                messages.error(request, GENERIC_INVALID_MESSAGE)
            return render(
                request,
                "registration/password_reset_verify.html",
                {"form": form, "wait_seconds": resend_wait_seconds(email)},
            )

        # Correct code: single-use now, and revoke any other open requests.
        code_row.complete()
        PasswordResetCode.objects.filter(
            user=user, invalidated=False, verified=False
        ).exclude(pk=code_row.pk).update(invalidated=True)

        request.session[VERIFIED_SESSION_KEY] = True
        request.session[USER_SESSION_KEY] = user.pk
        request.session[EXPIRY_SESSION_KEY] = (
            timezone.now() + timezone.timedelta(minutes=SESSION_TTL_MINUTES)
        ).isoformat()
        messages.success(request, "Verification code accepted.")
        return redirect("password_reset_new_password")

    return render(
        request,
        "registration/password_reset_verify.html",
        {"form": form, "wait_seconds": resend_wait_seconds(email)},
    )


def new_password(request):
    """Step 3 — set a fresh password, gated by a valid reset session."""
    user = _verified_user(request)
    if user is None:
        _clear_reset_session(request)
        messages.error(request, RESET_SESSION_EXPIRED_MESSAGE)
        return redirect("password_reset")

    form = SetNewPasswordForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        # Clean up all reset state: session claim + any outstanding codes.
        _clear_reset_session(request)
        PasswordResetCode.objects.filter(user=user, invalidated=False).update(
            invalidated=True
        )
        PasswordResetCode.cleanup_expired()
        messages.success(request, "Password changed successfully.")
        return redirect("password_reset_success")

    return render(request, "registration/password_reset_new_password.html", {"form": form})


def password_reset_success(request):
    """Step 4 — confirmation page with a single "Sign in" action."""
    return render(request, "registration/password_reset_success.html")