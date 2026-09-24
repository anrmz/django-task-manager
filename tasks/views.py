"""Views for the Task Manager product.

Information architecture
------------------------
CPATURE → ORGANIZE → DO → COMPLETE → REVIEW

Primary:
  My Day       today's focus (due today / overdue)
  Inbox        captured but unorganised tasks (no project, no date)
  Upcoming     everything due after today, grouped by date
  All Tasks    searchable, filterable task database

Organize:      Projects · Tags
Insights:      Productivity (real metrics only)
Account:       Settings

Every queryset is scoped to ``request.user``; unrelated users always get a 404.
All statistics are computed from real database rows — nothing is fabricated.
"""

from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, When
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import resolve, Resolver404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ProjectForm, QuickAddForm, RegisterForm, TaskForm, UserPreferencesForm
from .models import Project, Subtask, Task, TaskEvent, UserSettings, log_task_event

STATUS = Task.Status
PRIORITY = Task.Priority


def _priority_order():
    """A ``Case`` expression that sorts high → medium → low."""
    return Case(
        When(priority=PRIORITY.HIGH, then=0),
        When(priority=PRIORITY.MEDIUM, then=1),
        When(priority=PRIORITY.LOW, then=2),
        default=3,
        output_field=IntegerField(),
    )


def _ordered_tasks(qs):
    """Priority-first ordering plus flattened subtask progress numbers so
    list rows can render "2/4" without an N+1 query."""
    return (
        qs.annotate(
            _priority_order=_priority_order(),
            sub_count=Count("subtasks", distinct=True),
            sub_done=Count(
                "subtasks", filter=Q(subtasks__done=True), distinct=True
            ),
        ).order_by("_priority_order", "due_date", "-created_at")
    )


def _counts(user):
    """Badge numbers for the sidebar / bottom nav, recomputed server-side so
    quick-add and toggles can keep them honest without a full reload."""
    today = timezone.localdate()
    base = Task.objects.filter(user=user)
    return {
        "inbox": base.filter(
            status=STATUS.PENDING, project__isnull=True, due_date__isnull=True
        ).count(),
        "upcoming": base.filter(
            status=STATUS.PENDING, due_date__gt=today
        ).count(),
        "overdue": base.filter(status=STATUS.PENDING, due_date__lt=today).count(),
        "completed": base.filter(status=STATUS.COMPLETED).count(),
    }


def _landing(user):
    """The user's preferred landing view (from Settings), validated."""
    preference = UserSettings.for_user(user).default_view
    if preference in dict(UserSettings.DefaultView.choices):
        return preference
    return "my_day"


def _rename(field, value):
    return dict(field.choices).get(value, value)


def _due_bucket(due_date, today):
    days = (due_date - today).days
    if days == 1:
        return "tomorrow"
    if days <= 7:
        return "week"
    return "later"


# ---------------------------------------------------------------------------
# Entry / landing
# ---------------------------------------------------------------------------


def home(request):
    """Root URL: signed-in users go straight to their preferred landing."""
    if request.user.is_authenticated:
        return redirect(_landing(request.user))
    return redirect("login")


@login_required
def dashboard(request):
    """Legacy name — redirect to My Day, the real home screen."""
    return redirect("my_day")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _greeting(user):
    hour = timezone.localtime().hour
    if hour < 5:
        return "Working late"
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _safe_next(request, fallback="my_day"):
    """Trusted ``next`` URL or, when none is given, a view name we redirect to.

    ``url_has_allowed_host_and_scheme`` rejects scheme/backslash/``//`` tricks
    so a crafted parameter can never become an open redirect.
    """
    url = request.POST.get("next") or request.GET.get("next") or ""
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}
    ):
        return url
    return fallback


def _streak(query):
    days = set(
        query.filter(completed_at__isnull=False)
        .annotate(day=TruncDate("completed_at"))
        .values_list("day", flat=True)
    )
    current = timezone.localdate()
    if current not in days:
        current -= timedelta(days=1)
    streak = 0
    while current in days:
        streak += 1
        current -= timedelta(days=1)
    return streak


def _weekly_trend(query, monday):
    """Per-day completed counts Mon→Sun for the given week."""
    counts = {i: 0 for i in range(7)}
    rows = (
        query.filter(
            completed_at__isnull=False,
            completed_at__date__gte=monday,
            completed_at__date__lte=monday + timedelta(days=6),
        )
        .annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(total=Count("id"))
    )
    for row in rows:
        counts[row["day"].weekday()] = row["total"]
    return [
        {"label": label, "count": counts[i]}
        for i, label in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    ]


def _week_bounds(day=None):
    day = day or timezone.localdate()
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


# ---------------------------------------------------------------------------
# My Day — the heart of the product
# ---------------------------------------------------------------------------


@login_required
def my_day(request):
    today = timezone.localdate()
    base = (
        Task.objects.filter(user=request.user)
        .select_related("project")
        .prefetch_related("tags")
    )

    on_plate = _ordered_tasks(base.filter(status=STATUS.PENDING, due_date__lte=today))
    overdue = [t for t in on_plate if t.is_overdue()]
    due_today = [t for t in on_plate if not t.is_overdue()]

    done_today = base.filter(
        status=STATUS.COMPLETED, completed_at__date=today
    ).order_by("-completed_at")

    completed_count = done_today.count()
    plate_total = due_today.__len__() + completed_count

    tomorrow = today + timedelta(days=1)
    next_up = _ordered_tasks(base.filter(status=STATUS.PENDING, due_date=tomorrow))[:5]
    later_week = base.filter(
        status=STATUS.PENDING, due_date__gt=tomorrow, due_date__lte=today + timedelta(days=7)
    ).count()

    context = {
        "page": "my_day",
        "greeting": _greeting(request.user),
        "today": today,
        "overdue": overdue,
        "due_today": due_today,
        "done_today": done_today,
        "next_up": next_up,
        "later_week_count": later_week,
        "progress_done": completed_count,
        "progress_total": plate_total,
        "progress_pct": round((completed_count / plate_total) * 100) if plate_total else 0,
    }
    return render(request, "tasks/my_day.html", context)


@login_required
def inbox(request):
    """Unorganised captures — no project, no due date, still open."""
    tasks = _ordered_tasks(
        Task.objects.filter(
            user=request.user,
            status=STATUS.PENDING,
            project__isnull=True,
            due_date__isnull=True,
        ).select_related("project").prefetch_related("tags")
    )
    return render(request, "tasks/inbox.html", {
        "page": "inbox",
        "tasks": tasks,
    })


@login_required
def upcoming(request):
    """Everything due after today, grouped into helpful buckets."""
    today = timezone.localdate()
    all_upcoming = (
        Task.objects.filter(
            user=request.user, status=STATUS.PENDING, due_date__gt=today
        )
        .select_related("project")
        .prefetch_related("tags")
        .order_by("due_date")
    )

    def bucket(date_val):
        days = (date_val - today).days
        if days == 1:
            return "tomorrow"
        if days <= 7:
            return "week"
        return "later"

    grouped = {"tomorrow": [], "week": [], "later": []}
    for t in all_upcoming:
        grouped[bucket(t.due_date)].append(t)

    groups = [
        {"key": "tomorrow", "label": "Tomorrow", "sub": "Due tomorrow", "tasks": grouped["tomorrow"]},
        {"key": "week", "label": "This week", "sub": "Next 7 days", "tasks": grouped["week"]},
        {"key": "later", "label": "Later", "sub": "Beyond this week", "tasks": grouped["later"]},
    ]
    for g in groups:
        g["tasks"].sort(key=lambda t: (t.priority != PRIORITY.HIGH, t.due_date))
    has_tasks = any(g["tasks"] for g in groups)

    return render(request, "tasks/upcoming.html", {
        "page": "upcoming",
        "today": today,
        "groups": groups,
        "has_tasks": has_tasks,
    })


@login_required
def all_tasks(request):
    """Searchable, filterable, sortable task database."""
    qs = (
        Task.objects.filter(user=request.user)
        .select_related("project")
        .prefetch_related("tags")
    )

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    project_id = request.GET.get("project", "")
    tag = request.GET.get("tag", "").strip()
    overdue = request.GET.get("overdue") == "1"
    sort = request.GET.get("sort", "due")

    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(project__name__icontains=query)
            | Q(tags__name__icontains=query)
        )
    if status:
        qs = qs.filter(status=status)
    if priority:
        qs = qs.filter(priority=priority)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if tag:
        qs = qs.filter(tags__name=tag)
    if overdue:
        qs = qs.filter(status=STATUS.PENDING, due_date__lt=timezone.localdate())

    ordering = {
        "due": ["due_date", "-priority", "_priority_order"],
        "priority": ["_priority_order", "due_date"],
        "created": ["-created_at"],
        "updated": ["-updated_at"],
    }.get(sort)

    qs = qs.annotate(_priority_order=_priority_order())
    if ordering:
        qs = qs.order_by(*ordering)
    else:
        qs = qs.order_by("-created_at")
    qs = qs.distinct()

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Everything except page/sort, so sort tabs and pagination keep the active
    # filters while changing only their own dimension.
    preserved = request.GET.copy()
    preserved.pop("page", None)
    preserved.pop("sort", None)

    return render(request, "tasks/all_tasks.html", {
        "page": "all_tasks",
        "tasks": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "query": query,
        "current_status": status,
        "current_priority": priority,
        "current_project": project_id,
        "current_tag": tag,
        "current_overdue": overdue,
        "sort": sort,
        "preserved_qs": preserved.urlencode(),
        "statuses": STATUS.choices,
        "priorities": PRIORITY.choices,
        "projects": Project.objects.filter(user=request.user).order_by("name"),
        "tag_options": Task.objects.filter(
            user=request.user, tags__isnull=False
        ).values_list("tags__name", flat=True).distinct().order_by("tags__name"),
        "today": timezone.localdate(),
    })


@login_required
def completed(request):
    """Completed archive, newest first (kept for deep links)."""
    tasks = (
        Task.objects.filter(user=request.user, status=STATUS.COMPLETED)
        .select_related("project")
        .prefetch_related("tags")
        .order_by("-completed_at")
    )
    return render(request, "tasks/completed.html", {
        "page": "all_tasks",
        "tasks": tasks,
        "completed_count": tasks.count(),
        "today": timezone.localdate(),
    })


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@login_required
def project_list(request):
    projects = (
        Project.objects.filter(user=request.user)
        .annotate(
            total_count=Count("tasks", distinct=True),
            open_count=Count("tasks", filter=Q(tasks__status=STATUS.PENDING), distinct=True),
            done_count=Count("tasks", filter=Q(tasks__status=STATUS.COMPLETED), distinct=True),
        )
        .order_by("name")
    )
    return render(request, "tasks/projects.html", {
        "page": "projects",
        "projects": projects,
    })


@login_required
def project_create(request):
    form = ProjectForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Give the project a name (up to 120 characters).")
        return redirect("project_list")
    name = form.cleaned_data["name"].strip()
    project, created = Project.objects.get_or_create(
        user=request.user, name=name
    )
    if created:
        messages.success(request, f"Project “{project.name}” created.")
    else:
        messages.info(request, f"A project named “{name}” already exists.")
    return redirect("project_list")


@login_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    if request.method == "POST":
        project.delete()
        messages.success(request, f"Project “{project.name}” deleted. Its tasks were kept.")
        return redirect("project_list")
    return render(request, "tasks/project_confirm_delete.html", {
        "page": "projects",
        "project": project,
    })


@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        Project.objects.annotate(
            total_count=Count("tasks", distinct=True),
            open_count=Count("tasks", filter=Q(tasks__status=STATUS.PENDING), distinct=True),
            done_count=Count("tasks", filter=Q(tasks__status=STATUS.COMPLETED), distinct=True),
        ),
        pk=pk,
        user=request.user,
    )
    open_tasks = _ordered_tasks(
        Task.objects.filter(user=request.user, project=project, status=STATUS.PENDING)
        .select_related("project").prefetch_related("tags")
    )
    done_tasks = (
        Task.objects.filter(user=request.user, project=project, status=STATUS.COMPLETED)
        .select_related("project").prefetch_related("tags")
        .order_by("-completed_at")
    )
    return render(request, "tasks/project_detail.html", {
        "page": "projects",
        "project": project,
        "open_tasks": open_tasks,
        "done_tasks": done_tasks[:30],
        "open_count": open_tasks.count(),
        "done_count": done_tasks.count(),
        "total_count": project.total_count,
        "today": timezone.localdate(),
    })


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@login_required
def tags_list(request):
    from .models import Tag

    tags = (
        Tag.objects.filter(user=request.user)
        .annotate(
            open_count=Count("tasks", filter=Q(tasks__status=STATUS.PENDING)),
            total_count=Count("tasks"),
        )
        .order_by("name")
    )
    return render(request, "tasks/tags.html", {
        "page": "tags",
        "tags": tags,
    })


# ---------------------------------------------------------------------------
# Tasks — create / detail / edit / delete / toggle
# ---------------------------------------------------------------------------


@login_required
def task_create(request):
    initial = {}
    project_id = request.GET.get("project", "")
    if project_id and Project.objects.filter(pk=project_id, user=request.user).exists():
        initial["project"] = project_id
    form = TaskForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        task = form.save_with_user(request.user)
        log_task_event(request.user, task, "created")
        messages.success(request, f"Task “{task.title}” created.")
        return redirect(_safe_next(request, "my_day"))
    return render(request, "tasks/task_form.html", {
        "page": "all_tasks",
        "form": form,
        "is_edit": False,
        "today": timezone.localdate(),
    })


def _editable_fields(task):
    """Snapshot of the fields that appear on the activity timeline."""
    return {
        "priority": task.priority,
        "due_date": task.due_date,
        "due_time": task.due_time,
        "project_id": task.project_id,
        "tags": {t.name for t in task.tags.all()},
    }


def _log_changes(user, before, task):
    if before["priority"] != task.priority:
        log_task_event(
            user, task, "priority",
            f"Changed to {_rename(PRIORITY, task.priority)}",
        )
    if before["due_date"] != task.due_date or before["due_time"] != task.due_time:
        detail = f"Set to {task.due_date:%b %d}"
        if task.due_time:
            detail += f" · {task.due_time:%H:%M}"
        log_task_event(user, task, "due", detail)
    if before["project_id"] != task.project_id:
        detail = (
            f"Moved to {task.project.name}" if task.project else "Removed from a project"
        )
        log_task_event(user, task, "project", detail)
    if before["tags"] != {t.name for t in task.tags.all()}:
        log_task_event(user, task, "tags", "Updated")


@login_required
def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related("project").prefetch_related("tags"),
        pk=pk,
        user=request.user,
    )
    subtasks = list(task.subtasks.all())
    sub_done = sum(1 for s in subtasks if s.done)
    events = task.events.all()[:15]
    return render(request, "tasks/task_detail.html", {
        "page": "all_tasks",
        "task": task,
        "subtasks": subtasks,
        "sub_total": len(subtasks),
        "sub_done": sub_done,
        "events": events,
        "today": timezone.localdate(),
    })


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    before = _editable_fields(task)
    form = TaskForm(request.POST or None, instance=task, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save_with_user(request.user)
        _log_changes(request.user, before, task)
        messages.success(request, f"Task “{task.title}” updated.")
        return redirect(_safe_next(request, task.get_absolute_url()))
    return render(request, "tasks/task_form.html", {
        "page": "all_tasks",
        "form": form,
        "is_edit": True,
        "today": timezone.localdate(),
    })


@login_required
def task_delete(request, pk):
    """Move a task to Trash (reversible) instead of deleting it outright."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    if request.method == "POST":
        task.move_to_trash()
        log_task_event(request.user, task, "deleted")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({
                "ok": True,
                "pk": task.pk,
                "next": _safe_next(request, "my_day"),
                "url": task.get_absolute_url(),
                "title": task.title,
            })
        messages.info(request, f"“{task.title}” moved to trash.")
        return redirect(_safe_next(request, "my_day"))
    return render(request, "tasks/task_confirm_delete.html", {
        "page": "all_tasks",
        "task": task,
    })


@login_required
def trash(request):
    """Everything soft-deleted, with restore and permanent-delete actions."""
    trashed = (
        Task.all_objects.filter(user=request.user, deleted_at__isnull=False)
        .select_related("project")
        .order_by("-deleted_at")
    )
    return render(request, "tasks/trash.html", {
        "page": "trash",
        "trashed": trashed,
        "trash_count": trashed.count(),
    })


@login_required
@require_POST
def trash_empty(request):
    """Empty the trash: permanently delete every soft-deleted task."""
    trashed = Task.all_objects.filter(user=request.user, deleted_at__isnull=False)
    count = trashed.count()
    trashed.delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": count})
    messages.success(
        request, "Trash emptied." if count else "Your trash is already empty."
    )
    return redirect(_safe_next(request, "trash"))


@login_required
@require_POST
def task_restore(request, pk):
    task = get_object_or_404(
        Task.all_objects.filter(deleted_at__isnull=False), pk=pk, user=request.user
    )
    task.restore()
    log_task_event(request.user, task, "restored")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "pk": task.pk,
            "url": task.get_absolute_url(),
        })
    messages.success(request, f"“{task.title}” restored.")
    return redirect(_safe_next(request, "trash"))


@login_required
@require_POST
def task_delete_forever(request, pk):
    task = get_object_or_404(
        Task.all_objects.filter(deleted_at__isnull=False), pk=pk, user=request.user
    )
    task.delete()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "pk": pk})
    messages.success(request, f"“{task.title}” permanently deleted.")
    return redirect(_safe_next(request, "trash"))


@login_required
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.toggle()
    verb = "completed" if task.status == STATUS.COMPLETED else "reopened"
    log_task_event(request.user, task, verb)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "status": task.status,
            "counts": _counts(request.user),
        })
    messages.success(
        request,
        "Task completed."
        if task.status == STATUS.COMPLETED
        else "Task reopened.",
    )
    return redirect(_safe_next(request, "my_day"))


@login_required
def quick_add(request):
    """One primary capture action everywhere.

    Server-rendered POST (progressive) or JSON for the fetch-based modal.
    The JSON path also returns the rendered row + placement hints so the page
    can grow in place instead of reloading.
    """
    form = QuickAddForm(request.POST or None, user=request.user)
    want_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if request.method == "POST":
        if form.is_valid():
            task = form.save_with_user(request.user)
            log_task_event(request.user, task, "created")
            if want_json:
                html = render_to_string(
                    "components/task_item.html", {"task": task}, request=request
                )
                return JsonResponse({
                    "ok": True,
                    "task": {"id": task.pk, "title": task.title},
                    "html": html,
                    "place": _placement(task, request.POST.get("next", "")),
                    "counts": _counts(request.user),
                })
            messages.success(request, f"Task “{task.title}” created.")
            return redirect(_safe_next(request, "my_day"))

        if want_json:
            return JsonResponse({"ok": False, "errors": form.errors.as_json()}, status=400)
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(_safe_next(request, "my_day"))

    if want_json:
        return JsonResponse({"ok": False, "errors": []}, status=405)
    return redirect("my_day")


def _placement(task, next_url):
    """Decide how the client should reflect a freshly created task.

    ``insert`` — prepend the returned row into the current task list
    ``insert:<bucket>`` — prepend into a specific Upcoming bucket
    ``reload`` — counts/progress on this page depend on the change
    ``toast`` — task belongs elsewhere; just confirm via toast/badges
    """
    import urllib.parse

    try:
        match = resolve(urllib.parse.urlsplit(next_url).path)
    except Resolver404:
        return "toast"
    name = match.url_name
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
    today = timezone.localdate()

    if name in ("my_day", "completed"):
        return "reload"
    if name in ("productivity", "tags_list", "settings"):
        return "toast"
    if name == "inbox":
        if not task.project_id and not task.due_date:
            return "insert"
        return "reload"
    if name == "upcoming":
        if task.due_date and task.due_date > today:
            return "insert:" + _due_bucket(task.due_date, today)
        return "reload"
    if name == "project_detail":
        if task.project_id == int(match.kwargs.get("pk") or 0):
            return "insert"
        return "reload"
    if name == "all_tasks":
        # With active filters the new task may not belong to the visible page.
        unsorted = ["q", "status", "priority", "project", "tag", "overdue"]
        if any(key in query for key in unsorted):
            return "reload"
        return "insert"
    return "toast"


@login_required
@require_POST
def task_patch(request, pk):
    """Inline, contextual editing (priority / due date) from the task page."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    field = request.POST.get("field", "")
    value = request.POST.get("value", "").strip()

    if field == "priority":
        if value not in dict(PRIORITY.choices):
            return JsonResponse({"ok": False, "error": "Unknown priority."}, status=400)
        task.priority = value
        task.save(update_fields=["priority", "updated_at"])
        log_task_event(request.user, task, "priority", f"Changed to {_rename(PRIORITY, value)}")
        return JsonResponse({"ok": True, "priority": value})

    if field == "due_date":
        due = parse_date(value) if value else None
        if value and not due:
            return JsonResponse({"ok": False, "error": "Invalid date."}, status=400)
        task.due_date = due
        task.save(update_fields=["due_date", "updated_at"])
        detail = f"Set to {due:%b %d}" if due else "Removed"
        if task.due_time:
            detail += f" · {task.due_time:%H:%M}"
        log_task_event(request.user, task, "due", detail)
        return JsonResponse({"ok": True, "due": value})

    if field == "due_time":
        due = parse_time(value) if value else None
        if value and not due:
            return JsonResponse({"ok": False, "error": "Invalid time."}, status=400)
        task.due_time = due
        if not task.due_date:
            task.due_date = timezone.localdate()
            task.save(update_fields=["due_date", "due_time", "updated_at"])
        else:
            task.save(update_fields=["due_time", "updated_at"])
        detail = f"Set to {task.due_date:%b %d}"
        detail += f" · {due:%H:%M}" if due else ""
        log_task_event(request.user, task, "due", detail)
        return JsonResponse({
            "ok": True,
            "time": value,
            "due": task.due_date.isoformat() if task.due_date else "",
        })

    return JsonResponse({"ok": False, "error": "Unknown field."}, status=400)


# ---------------------------------------------------------------------------
# Subtasks — lightweight breakdown under a task
# ---------------------------------------------------------------------------


def _sub_progress(task):
    subtasks = list(task.subtasks.all())
    return {"done": sum(1 for s in subtasks if s.done), "total": len(subtasks)}


@login_required
@require_POST
def subtask_add(request, pk):
    task = get_object_or_404(Task, pk=pk, user=request.user)
    title = request.POST.get("title", "").strip()
    want_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if not title:
        if want_json:
            return JsonResponse({"ok": False, "error": "Give the subtask a title."}, status=400)
        messages.error(request, "Give the subtask a title.")
        return redirect(task.get_absolute_url())

    subtask = Subtask.objects.create(user=request.user, task=task, title=title[:200])
    log_task_event(request.user, task, "subtask_add", title)
    if want_json:
        html = render_to_string(
            "components/subtask_item.html", {"subtask": subtask}, request=request
        )
        progress = _sub_progress(task)
        return JsonResponse({
            "ok": True,
            "html": html,
            "done": progress["done"],
            "total": progress["total"],
        })
    messages.success(request, f"Subtask “{title}” added.")
    return redirect(task.get_absolute_url())


@login_required
@require_POST
def subtask_toggle(request, pk):
    subtask = get_object_or_404(Subtask, pk=pk, user=request.user)
    subtask.toggle()
    log_task_event(
        request.user, subtask.task, "subtask_toggle", subtask.title
    )
    progress = _sub_progress(subtask.task)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "done": subtask.done,
            "done_count": progress["done"],
            "total": progress["total"],
        })
    messages.success(request, f"“{subtask.title}” updated.")
    return redirect(subtask.task.get_absolute_url())


@login_required
@require_POST
def subtask_delete(request, pk):
    subtask = get_object_or_404(Subtask, pk=pk, user=request.user)
    subtask.delete()
    log_task_event(
        request.user, subtask.task, "subtask_delete", subtask.title
    )
    progress = _sub_progress(subtask.task)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "done": progress["done"],
            "total": progress["total"],
        })
    messages.success(request, f"Subtask “{subtask.title}” removed.")
    return redirect(subtask.task.get_absolute_url())


# ---------------------------------------------------------------------------
# Command palette (search across tasks, projects and tags)
# ---------------------------------------------------------------------------


@login_required
def palette_json(request):
    query = request.GET.get("q", "").strip()
    payload = {"tasks": [], "projects": [], "tags": []}

    tasks = (
        Task.objects.filter(user=request.user)
        .select_related("project")
        .prefetch_related("tags")
    )
    if query:
        tasks = tasks.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(project__name__icontains=query)
        )
    payload["tasks"] = [
        {
            "id": t.pk,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "project": t.project.name if t.project else None,
            "due": t.due_date.isoformat() if t.due_date else None,
            "url": t.get_absolute_url(),
        }
        for t in tasks[:8]
    ]

    projects = Project.objects.filter(user=request.user)
    if query:
        projects = projects.filter(name__icontains=query)
    payload["projects"] = [
        {"id": p.pk, "name": p.name, "url": p.get_absolute_url()}
        for p in projects[:5]
    ]

    from .models import Tag

    tag_rows = (
        Task.tags.through.objects.filter(
            task__user=request.user, task__deleted_at__isnull=True
        )
        .filter(tag__name__icontains=query)
        .values("tag__name").distinct()[:6]
    )
    payload["tags"] = [r["tag__name"] for r in tag_rows]

    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# Productivity — honest metrics from real data
# ---------------------------------------------------------------------------


@login_required
def productivity(request):
    today = timezone.localdate()
    monday, sunday = _week_bounds(today)
    month_start = today.replace(day=1)
    user_tasks = Task.objects.filter(user=request.user)

    completed_today = user_tasks.filter(
        status=STATUS.COMPLETED, completed_at__date=today
    ).count()
    completed_week = user_tasks.filter(
        status=STATUS.COMPLETED, completed_at__date__gte=monday
    ).count()
    completed_month = user_tasks.filter(
        status=STATUS.COMPLETED, completed_at__date__gte=month_start
    ).count()

    pending = user_tasks.filter(status=STATUS.PENDING).count()
    overdue = user_tasks.filter(
        status=STATUS.PENDING, due_date__lt=today
    ).count()
    created_month = user_tasks.filter(created_at__date__gte=month_start).count()
    completed = user_tasks.filter(status=STATUS.COMPLETED).count()
    total = user_tasks.count()
    completion_rate = round((completed / total) * 100) if total else 0
    streak = _streak(user_tasks.filter(status=STATUS.COMPLETED))

    # 7-day completed trend (Mon→Sun), normalised for the bar chart.
    trend = _weekly_trend(user_tasks.filter(status=STATUS.COMPLETED), monday)
    peak = max([d["count"] for d in trend] + [1])

    return render(request, "tasks/productivity.html", {
        "page": "productivity",
        "today": today,
        "completed_today": completed_today,
        "completed_week": completed_week,
        "completed_month": completed_month,
        "pending": pending,
        "overdue": overdue,
        "created_month": created_month,
        "completion_rate": completion_rate,
        "streak": streak,
        "trend": trend,
        "peak": peak,
        "week_label": f"{monday:%b %d} – {sunday:%b %d}",
    })


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@login_required
def settings_view(request):
    """Account + appearance preferences.

    Two independent POST forms share this page and are told apart by their
    field names: the password form carries ``old_password``.
    """
    prefs = UserSettings.for_user(request.user)

    # Always build both forms so the non-submitted view renders clean state.
    if request.method == "POST":
        if "old_password" in request.POST:
            pwd_form = PasswordChangeForm(request.user, data=request.POST)
            if pwd_form.is_valid():
                user = pwd_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated.")
                return redirect("settings")
            messages.error(request, "Check the password details and try again.")
        else:
            prefs_form = UserPreferencesForm(
                request.POST, instance=prefs, prefix="prefs"
            )
            if prefs_form.is_valid():
                prefs_form.save()
                messages.success(request, "Preferences saved.")
                return redirect("settings")
            messages.error(request, "Couldn't save preferences.")

    pwd_form = PasswordChangeForm(request.user)
    prefs_form = UserPreferencesForm(instance=prefs, prefix="prefs")

    completed = Task.objects.filter(
        user=request.user, status=STATUS.COMPLETED
    ).count()
    total = Task.objects.filter(user=request.user).count()

    return render(request, "tasks/settings.html", {
        "page": "settings",
        "pwd_form": pwd_form,
        "prefs": prefs,
        "prefs_form": prefs_form,
        "completed": completed,
        "total": total,
    })


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def register(request):
    if request.user.is_authenticated:
        return redirect(_landing(request.user))
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome — your workspace is ready.")
            return redirect("my_day")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


def user_login(request):
    if request.user.is_authenticated:
        return redirect(_landing(request.user))
    form = AuthenticationForm(request, data=request.POST or None)
    for field in form.fields.values():
        field.widget.attrs["class"] = "field__control"
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None:
            login(request, user)
            messages.success(request, "Welcome back.")
            return redirect(_safe_next(request, _landing(user)))
        messages.error(request, "Invalid username or password.")
    return render(request, "registration/login.html", {
        "form": form,
        "next": _safe_next(request, "my_day"),
    })


def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have been logged out.")
        return redirect("login")
    return render(request, "registration/logout_confirm.html")