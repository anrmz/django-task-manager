"""Context processors — shared data for authenticated templates."""

from django.db.models import Q
from django.utils import timezone

from .models import Project, Task, UserSettings


def nav(request):
    """Sidebar / topbar navigation counts for the current user.

    Computed with lightweight counts so everyday pages never pay for full
    querysets. Anonymous requests simply get ``nav=None``.
    """
    if not request.user.is_authenticated:
        return {"nav": None}

    user = request.user
    today = timezone.localdate()

    base = Task.objects.filter(user=user)

    name = getattr(request.resolver_match, "url_name", None)
    page_map = {
        "my_day": "my_day",
        "inbox": "inbox",
        "upcoming": "upcoming",
        "all_tasks": "all_tasks",
        "completed": "completed",
        "trash": "trash",
        "task_create": "all_tasks",
        "task_detail": "all_tasks",
        "task_edit": "all_tasks",
        "task_delete": "all_tasks",
        "task_toggle": "all_tasks",
        "quick_add": "all_tasks",
        "project_list": "projects",
        "project_create": "projects",
        "project_detail": "projects",
        "project_delete": "projects",
        "tags_list": "tags",
        "productivity": "productivity",
        "settings_view": "settings",
    }

    projects = list(Project.objects.filter(user=user).order_by("name"))

    nav = {
        "page": page_map.get(name, ""),
        "inbox_count": base.filter(
            status=Task.Status.PENDING,
            project__isnull=True,
            due_date__isnull=True,
        ).count(),
        "upcoming_count": base.filter(
            status=Task.Status.PENDING, due_date__gt=today
        ).count(),
        "overdue_count": base.filter(
            status=Task.Status.PENDING, due_date__lt=today
        ).count(),
        "completed_count": base.filter(status=Task.Status.COMPLETED).count(),
        "trash_count": Task.all_objects.filter(user=user, deleted_at__isnull=False).count(),
        "project_count": len(projects),
        "projects": projects[:8],
        "qa_projects": projects,
        "tag_options": list(
            Task.objects.filter(user=user, tags__isnull=False)
            .values_list("tags__name", flat=True)
            .distinct()
            .order_by("tags__name")[:12]
        ),
    }

    prefs = UserSettings.for_user(user)
    return {"nav": nav, "prefs": prefs}