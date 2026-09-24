from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

import hashlib
import hmac
import secrets


class Project(models.Model):
    """A lightweight container for a group of tasks (e.g. Work, Personal).

    Owned by a single user so ownership is always scoped to ``user``.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="projects",
        verbose_name="Owner",
    )
    name = models.CharField(max_length=120)
    color = models.CharField(
        max_length=7,
        default="#2563EB",
        help_text="Accent color used for the project chip, e.g. #2563EB.",
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_project_per_user",
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("project_detail", args=[self.pk])


class Tag(models.Model):
    """A lightweight free-form label (e.g. ``urgent``, ``frontend``).

    Owned by a single user so no two users can collide on a tag name.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tags",
        verbose_name="Owner",
    )
    name = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_tag_per_user",
            )
        ]

    def __str__(self):
        return self.name


class TaskQuerySet(models.QuerySet):
    """Base queryset for ``Task``.

    The default manager filters out soft-deleted (trashed) tasks so every
    existing view is automatically correct. ``all_objects`` is the escape
    hatch used only by the Trash view and the permanent-delete flow.
    """

    def visible(self):
        return self.filter(deleted_at__isnull=True)


class TaskManager(models.Manager.from_queryset(TaskQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class Task(models.Model):
    """A task owned by a single user.

    Deleting a task is reversible: ``deleted_at`` moves it to Trash and every
    normal query hides it. ``Task.all_objects`` is required to reach rows in
    the trash.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Owner",
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
        verbose_name="Project",
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="tasks",
        verbose_name="Tags",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    due_date = models.DateField(null=True, blank=True)
    due_time = models.TimeField(
        null=True,
        blank=True,
        help_text="Optional time-of-day for the due date.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = TaskManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="task_user_status_idx"),
            models.Index(fields=["user", "due_date"], name="task_user_due_idx"),
            models.Index(fields=["user", "priority"], name="task_user_prio_idx"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("task_detail", args=[self.pk])

    def is_trashed(self):
        return self.deleted_at is not None

    def move_to_trash(self):
        """Soft-delete — the task leaves every normal query but stays in the
        database so it can be restored from Trash."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])
        return self

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])
        return self

    # -- behaviour ---------------------------------------------------------------

    def is_overdue(self):
        """Overdue only matters for unfinished tasks with a past due date."""
        today = timezone.localdate()
        return (
            self.status == Task.Status.PENDING
            and self.due_date is not None
            and self.due_date < today
        )

    def is_due_on(self, day):
        return self.due_date is not None and self.due_date == day

    def belongs_to_my_day(self):
        """My Day = due today or overdue (and not yet completed)."""
        if self.status == Task.Status.COMPLETED:
            return False
        return self.is_overdue() or self.is_due_on(timezone.localdate())

    def is_upcoming(self):
        return (
            self.status == Task.Status.PENDING
            and self.due_date is not None
            and self.due_date > timezone.localdate()
        )

    def toggle(self):
        """Flip between pending and completed, maintaining ``completed_at``."""
        if self.status == Task.Status.COMPLETED:
            self.status = Task.Status.PENDING
            self.completed_at = None
        else:
            self.status = Task.Status.COMPLETED
            self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])
        return self

    @classmethod
    def completed_on(cls, user, day):
        """Tasks the user completed on the given date (completed_at, local)."""
        start = timezone.make_aware(
            timezone.datetime.combine(day, timezone.datetime.min.time()),
            timezone.get_current_timezone(),
        )
        end = start + timedelta(days=1)
        return cls.objects.filter(
            user=user,
            status=cls.Status.COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )


class Subtask(models.Model):
    """A tiny checkbox item nested under a task (e.g. "test mobile layout").

    Ownership is denormalised onto the row so every query is scoped with a
    simple ``user=`` filter and no cross-table joins are needed for checks.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="Owner",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="subtasks",
        verbose_name="Task",
    )
    title = models.CharField(max_length=200)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["user", "task"], name="subtask_user_task_idx"),
        ]

    def __str__(self):
        return self.title

    def toggle(self):
        self.done = not self.done
        self.save(update_fields=["done"])
        return self


class TaskEvent(models.Model):
    """One line of a task's activity timeline ("You changed priority to High").

    Cheap to write, expensive to over-engineer: just a verb + optional detail
    string rendered under the task. Created entirely server-side.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_events",
        verbose_name="Actor",
    )
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="Task",
    )
    verb = models.CharField(max_length=24)
    detail = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task", "-created_at"], name="event_task_created_idx"),
        ]

    def __str__(self):
        return f"{self.verb} {self.detail or '·'}"


class PasswordResetCode(models.Model):
    """One 6-digit, time-limited, single-use password-reset code.

    The plaintext code is never stored — only a salted SHA-256 ``code_hash``,
    so a database leak never yields usable codes. ``attempts`` bounds brute
    force, ``verified``/``used_at`` enforce single-use, ``invalidated`` marks
    rows superseded by a newer request, and ``expires_at`` bounds validity.

    Contains password-reset metadata only; no password material lives here.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="password_reset_codes",
        verbose_name="User",
    )
    code_hash = models.CharField(max_length=64)  # hex SHA-256, never the code
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    verified = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    invalidated = models.BooleanField(
        default=False,
        help_text="True when superseded by a newer request or brute-force lockout.",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="pwrc_user_created_idx"),
        ]

    def __str__(self):
        return f"reset-code for {self.user_id} ({self.expires_at:%Y-%m-%d %H:%M})"

    # -- hashing (never store the randecode) ----------------------------------

    @staticmethod
    def _digest(code, user_pk):
        """Salted digest of a code for a given user (peppered with SECRET_KEY)."""
        raw = f"{code}:{user_pk}:{settings.SECRET_KEY}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def generate(cls, user, ttl_minutes=10):
        """Create a fresh single-use code row, invalidating any previous ones."""
        code = f"{secrets.randbelow(1_000_000):06d}"
        obj = cls(
            user=user,
            code_hash=cls._digest(code, user.pk),
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
        )
        obj.save()
        # Only the newest unconsumed code may be valid (request B kills code A).
        cls.objects.filter(user=user, invalidated=False, verified=False).exclude(
            pk=obj.pk
        ).update(invalidated=True)
        return obj, code

    def matches(self, code):
        return hmac.compare_digest(self.code_hash, self._digest(code, self.user_id))

    def is_expired(self, now=None):
        now = now or timezone.now()
        return now > self.expires_at

    def complete(self):
        """Mark verified as used — the code can never be replayed."""
        self.verified = True
        self.used_at = timezone.now()
        self.save(update_fields=["verified", "used_at"])

    @classmethod
    def cleanup_expired(cls, now=None, older_than_hours=24):
        """Simple housekeeping: purge expired codes, plus verified/invalidated
        ones older than ``older_than_hours``. Cheap, no task queue needed."""
        now = now or timezone.now()
        horizon = now - timedelta(hours=older_than_hours)
        deleted = cls.objects.filter(expires_at__lt=now).delete()[0]
        deleted += (
            cls.objects.filter(expires_at__lt=horizon, verified=True).delete()[0]
        )
        deleted += (
            cls.objects.filter(expires_at__lt=horizon, invalidated=True).delete()[0]
        )
        return deleted


class UserSettings(models.Model):
    """Per-user preferences. Created lazily, edited from Settings."""

    class Density(models.TextChoices):
        COMFORTABLE = "comfortable", "Comfortable"
        COMPACT = "compact", "Compact"

    class DefaultView(models.TextChoices):
        MY_DAY = "my_day", "My Day"
        INBOX = "inbox", "Inbox"
        UPCOMING = "upcoming", "Upcoming"
        ALL_TASKS = "all_tasks", "All Tasks"
        PRODUCTIVITY = "productivity", "Productivity"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    density = models.CharField(
        max_length=16,
        choices=Density.choices,
        default=Density.COMFORTABLE,
    )
    default_view = models.CharField(
        max_length=16,
        choices=DefaultView.choices,
        default=DefaultView.MY_DAY,
    )
    onboarding_done = models.BooleanField(
        default=False,
        help_text="True once the guided first-run tour has been completed or skipped.",
    )

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj


def log_task_event(user, task, verb, detail=""):
    """Record one activity-line for a task (ownership checked by caller)."""
    return TaskEvent.objects.create(
        user=user, task=task, verb=verb, detail=detail[:255]
    )
