"""
Root URL configuration for the Task Manager project.
"""

from django.contrib import admin
from django.urls import include, path

from tasks import password_reset, views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Landing / authentication
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.logout_view, name="logout"),
    # Forgot password — email → 6-digit code → new password → success
    path("password-reset/", password_reset.forgot_password, name="password_reset"),
    path(
        "password-reset/verify/",
        password_reset.verify_reset_code,
        name="password_reset_verify",
    ),
    path(
        "password-reset/resend/",
        password_reset.resend_code,
        name="password_reset_resend",
    ),
    path(
        "password-reset/new-password/",
        password_reset.new_password,
        name="password_reset_new_password",
    ),
    path(
        "password-reset/success/",
        password_reset.password_reset_success,
        name="password_reset_success",
    ),
    # Task functionality
    path("", include("tasks.urls")),
]
