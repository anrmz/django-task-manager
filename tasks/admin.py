from django.contrib import admin

from .models import (
    PasswordResetCode,
    Subtask,
    Task,
    TaskEvent,
    UserSettings,
)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Admin list columns, filters and search for tasks."""

    list_display = (
        "title",
        "user",
        "status",
        "priority",
        "due_date",
        "deleted_at",
        "created_at",
    )
    list_filter = ("status", "priority", "deleted_at", "created_at")
    search_fields = ("title", "user__username")
    list_select_related = ("user",)
    list_per_page = 20
    ordering = ("-created_at",)


@admin.register(Subtask)
class SubtaskAdmin(admin.ModelAdmin):
    list_display = ("title", "task", "user", "done", "created_at")
    list_filter = ("done",)
    search_fields = ("title", "task__title", "user__username")
    list_per_page = 20


@admin.register(TaskEvent)
class TaskEventAdmin(admin.ModelAdmin):
    list_display = ("verb", "task", "user", "detail", "created_at")
    list_filter = ("verb", "created_at")
    search_fields = ("detail", "task__title", "user__username")
    list_select_related = ("task", "user")
    list_per_page = 20


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "density", "default_view")
    list_filter = ("density", "default_view")
    search_fields = ("user__username",)


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    """Admin visibility for support/debugging. The code itself is never shown
    (only its hash), and rows are read-only to avoid touching reset state."""

    list_display = (
        "user",
        "code_hash",
        "created_at",
        "expires_at",
        "attempts",
        "verified",
        "invalidated",
        "used_at",
    )
    list_filter = ("verified", "invalidated", "created_at", "expires_at")
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)
    list_per_page = 20
    ordering = ("-created_at",)
    readonly_fields = (
        "user",
        "code_hash",
        "created_at",
        "expires_at",
        "attempts",
        "verified",
        "used_at",
        "invalidated",
        "ip_address",
        "user_agent",
    )

    def has_add_permission(self, request):
        return False