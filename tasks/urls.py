"""URL configuration for the ``tasks`` app.

All names are globally unique so no namespace is required — templates stay
short: ``{% url 'my_day' %}``, ``{% url 'project_detail' project.pk %}``.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Workspace — primary flow.
    path("dashboard/", views.dashboard, name="dashboard"),  # legacy alias
    path("my-day/", views.my_day, name="my_day"),
    path("inbox/", views.inbox, name="inbox"),
    path("upcoming/", views.upcoming, name="upcoming"),
    path("tasks/", views.all_tasks, name="all_tasks"),
    path("completed/", views.completed, name="completed"),
    path("trash/", views.trash, name="trash"),
    # Insights + account.
    path("productivity/", views.productivity, name="productivity"),
    path("settings/", views.settings_view, name="settings"),
    # Projects.
    path("projects/", views.project_list, name="project_list"),
    path("projects/create/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/delete/", views.project_delete, name="project_delete"),
    # Tags.
    path("tags/", views.tags_list, name="tags_list"),
    # Command palette + quick capture.
    path("palette/", views.palette_json, name="palette_json"),
    path("tasks/quick-add/", views.quick_add, name="quick_add"),
    # Task CRUD.
    path("tasks/create/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("tasks/<int:pk>/toggle/", views.task_toggle, name="task_toggle"),
    path("tasks/<int:pk>/patch/", views.task_patch, name="task_patch"),
    path("tasks/<int:pk>/restore/", views.task_restore, name="task_restore"),
    path(
        "tasks/<int:pk>/delete-forever/",
        views.task_delete_forever,
        name="task_delete_forever",
    ),
    path("trash/empty/", views.trash_empty, name="trash_empty"),
    # Subtasks (owned by a task the current user can see).
    path("tasks/<int:pk>/subtasks/add/", views.subtask_add, name="subtask_add"),
    path("subtask/<int:pk>/toggle/", views.subtask_toggle, name="subtask_toggle"),
    path("subtask/<int:pk>/delete/", views.subtask_delete, name="subtask_delete"),
]