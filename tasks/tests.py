import json
import re
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import QuickAddForm, TaskForm
from .models import PasswordResetCode, Project, Subtask, Tag, Task, UserSettings


class TaskManagerTests(TestCase):
    """End-to-end behaviour of the Task Manager application."""

    def setUp(self):
        # Two independent users to prove ownership boundaries.
        self.alice = User.objects.create_user(
            username="alice", password="password123"
        )
        self.bob = User.objects.create_user(
            username="bob", password="password123"
        )

    # --- helpers ---------------------------------------------------------------

    def _login(self, user=None):
        user = user or self.alice
        self.client.login(username=user.username, password="password123")
        return user

    def _make_task(self, user=None, title="Sample task", due_date=None):
        user = user or self.alice
        return Task.objects.create(
            user=user,
            title=title,
            priority=Task.Priority.MEDIUM,
            due_date=due_date,
        )

    # --- registration & authentication ----------------------------------------

    def test_user_can_register(self):
        data = {
            "username": "newbie",
            "email": "newbie@example.com",
            "password1": "Str0ng-Pass-2024",
            "password2": "Str0ng-Pass-2024",
        }
        response = self.client.post(reverse("register"), data)
        self.assertRedirects(response, reverse("my_day"))
        self.assertTrue(
            User.objects.filter(username="newbie").exists(),
            "New user should be saved to the database.",
        )

    def test_duplicate_username_is_rejected(self):
        data = {
            "username": "alice",  # already taken in setUp
            "email": "alice2@example.com",
            "password1": "Str0ng-Pass-2024",
            "password2": "Str0ng-Pass-2024",
        }
        response = self.client.post(reverse("register"), data)
        self.assertEqual(response.status_code, 200)  # re-renders the form
        self.assertContains(response, "already exists", msg_prefix="Username error shown")

    def test_user_can_login(self):
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "password123"},
        )
        self.assertRedirects(response, reverse("my_day"))
        # The legacy dashboard alias now hands off to My Day.
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("my_day"))
        self.assertEqual(self.client.get(reverse("my_day")).status_code, 200)

    # --- authenticated access & CRUD ------------------------------------------

    def test_authenticated_user_can_create_task(self):
        self._login()
        data = {"title": "Finish report", "priority": Task.Priority.HIGH}
        response = self.client.post(reverse("task_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Task.objects.filter(user=self.alice, title="Finish report").exists()
        )

    def test_user_can_view_own_task(self):
        self._login()
        task = self._make_task()
        response = self.client.get(reverse("task_detail", args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, task.title)

    def test_user_can_edit_own_task(self):
        self._login()
        task = self._make_task(title="Original title")
        response = self.client.post(
            reverse("task_edit", args=[task.pk]),
            {"title": "Updated title", "priority": Task.Priority.HIGH},
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.title, "Updated title")

    def test_user_can_delete_own_task(self):
        self._login()
        task = self._make_task()
        response = self.client.post(reverse("task_delete", args=[task.pk]))
        self.assertEqual(response.status_code, 302)
        # Soft delete: it leaves every normal query, but is restorable.
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        self.assertIsNotNone(Task.all_objects.get(pk=task.pk).deleted_at)

    def test_trash_restore_and_delete_forever(self):
        self._login()
        task = self._make_task()
        self.client.post(reverse("task_delete", args=[task.pk]))

        response = self.client.get(reverse("trash"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, task.title)

        # Trash page still lists it, restore brings it back everywhere.
        response = self.client.post(reverse("task_restore", args=[task.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Task.all_objects.get(pk=task.pk).deleted_at)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

        # Permanent delete truly purges it.
        self.client.post(reverse("task_delete", args=[task.pk]))
        response = self.client.post(reverse("task_delete_forever", args=[task.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Task.all_objects.filter(pk=task.pk).exists())

        # The restore endpoint is scoped to the trash, so a live task is 404.
        live = self._make_task(title="Alive")
        response = self.client.post(reverse("task_restore", args=[live.pk]))
        self.assertEqual(response.status_code, 404)

    def test_trash_empty_removes_all_trashed(self):
        user = self._login()
        a = self._make_task(title="One")
        b = self._make_task(title="Two")
        self.client.post(reverse("task_delete", args=[a.pk]))
        self.client.post(reverse("task_delete", args=[b.pk]))
        response = self.client.post(reverse("trash_empty"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Task.all_objects.filter(user=user).count(), 0)

    def test_subtask_lifecycle(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("subtask_add", args=[task.pk]), {"title": "QA pass"}
        )
        self.assertEqual(response.status_code, 302)
        subtask = task.subtasks.get(title="QA pass")

        response = self.client.post(reverse("subtask_toggle", args=[subtask.pk]))
        self.assertEqual(response.status_code, 302)
        subtask.refresh_from_db()
        self.assertTrue(subtask.done)

        response = self.client.post(reverse("subtask_delete", args=[subtask.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(task.subtasks.filter(pk=subtask.pk).exists())

    def test_subtasks_are_owner_scoped(self):
        task = self._make_task(user=self.alice, title="Alice's")
        self._login(self.bob)
        response = self.client.post(
            reverse("subtask_add", args=[task.pk]), {"title": "Sneaky"}
        )
        self.assertEqual(response.status_code, 404)

    def test_task_patch_priority_and_due(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "priority", "value": "high"},
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.priority, Task.Priority.HIGH)

        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "due_date", "value": ""},
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertIsNone(task.due_date)

    def test_task_patch_rejects_bad_values(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "priority", "value": "urgent"},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "due_date", "value": "not-a-date"},
        )
        self.assertEqual(response.status_code, 400)

    def test_completing_task_writes_event(self):
        self._login()
        task = self._make_task()
        self.assertEqual(task.events.count(), 0)
        self.client.post(reverse("task_toggle", args=[task.pk]))
        task.refresh_from_db()
        verbs = set(task.events.values_list("verb", flat=True))
        self.assertIn("completed", verbs)

    def test_preferences_save_and_landing(self):
        user = self._login()
        response = self.client.post(
            reverse("settings"),
            {"prefs-density": "compact", "prefs-default_view": "inbox"},
        )
        self.assertEqual(response.status_code, 302)
        prefs = UserSettings.objects.get(user=user)
        self.assertEqual(prefs.density, "compact")
        self.assertEqual(prefs.default_view, "inbox")

        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("inbox"))

    def test_overdue_filter_shows_only_past_due_open(self):
        self._login()
        past = self._make_task(title="Late", due_date=date.today() - timedelta(days=1))
        future = self._make_task(title="Soon", due_date=date.today() + timedelta(days=2))
        done_late = self._make_task(
            title="Completed late", due_date=date.today() - timedelta(days=1)
        )
        Task.objects.filter(pk=done_late.pk).update(status=Task.Status.COMPLETED)
        response = self.client.get(reverse("all_tasks"), {"overdue": "1"})
        self.assertContains(response, past.title)
        self.assertNotContains(response, future.title)
        self.assertNotContains(response, "Completed late")

    def test_palette_hides_trashed_tasks(self):
        self._login()
        task = self._make_task(title="ZombieTask")
        task.move_to_trash()
        response = self.client.get(reverse("palette_json"), {"q": "Zombie"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ZombieTask")

    def test_user_can_toggle_task_status(self):
        self._login()
        task = self._make_task()
        Task.objects.filter(pk=task.pk).update(status=Task.Status.PENDING)
        task.refresh_from_db()
        response = self.client.post(reverse("task_toggle", args=[task.pk]))
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.COMPLETED)

    # --- unauthenticated access ----------------------------------------------

    def test_unauthenticated_user_cannot_access_dashboard(self):
        response = self.client.get(reverse("dashboard"))
        # Redirects to the login page.
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_unauthenticated_user_cannot_open_workspace(self):
        for name in ("my_day", "inbox", "upcoming", "all_tasks", "project_list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)
            self.assertIn(reverse("login"), response.url, name)

    # --- ownership boundaries -------------------------------------------------

    def test_user_cannot_view_another_users_task(self):
        task = self._make_task(user=self.alice)
        self._login(self.bob)
        response = self.client.get(reverse("task_detail", args=[task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_edit_another_users_task(self):
        task = self._make_task(user=self.alice, title="Alice's secret")
        self._login(self.bob)
        response = self.client.post(
            reverse("task_edit", args=[task.pk]),
            {"title": "Hacked", "priority": Task.Priority.HIGH},
        )
        self.assertEqual(response.status_code, 404)
        task.refresh_from_db()
        self.assertEqual(task.title, "Alice's secret")

    def test_user_cannot_delete_another_users_task(self):
        task = self._make_task(user=self.alice)
        self._login(self.bob)
        response = self.client.post(reverse("task_delete", args=[task.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def test_user_cannot_toggle_another_users_task(self):
        task = self._make_task(user=self.alice)
        self._login(self.bob)
        response = self.client.post(reverse("task_toggle", args=[task.pk]))
        self.assertEqual(response.status_code, 404)

    # --- search & filtering ---------------------------------------------------

    def test_search_filters_by_title(self):
        self._login()
        self._make_task(title="Buy groceries")
        self._make_task(title="Pay the rent")

        response = self.client.get(reverse("all_tasks"), {"q": "groceries"})
        self.assertContains(response, "Buy groceries")
        self.assertNotContains(response, "Pay the rent")

    def test_filter_by_status_and_priority(self):
        self._login()
        low_done = self._make_task(title="Low and done")
        Task.objects.filter(pk=low_done.pk).update(
            status=Task.Status.COMPLETED, priority=Task.Priority.LOW
        )
        high_open = self._make_task(title="High and open")
        Task.objects.filter(pk=high_open.pk).update(
            status=Task.Status.PENDING, priority=Task.Priority.HIGH
        )

        # Only completed tasks.
        response = self.client.get(
            reverse("all_tasks"), {"status": Task.Status.COMPLETED}
        )
        self.assertContains(response, "Low and done")
        self.assertNotContains(response, "High and open")

        # Only high priority + pending.
        response = self.client.get(
            reverse("all_tasks"),
            {"status": Task.Status.PENDING, "priority": Task.Priority.HIGH},
        )
        self.assertContains(response, "High and open")
        self.assertNotContains(response, "Low and done")

    # --- new information architecture -----------------------------------------

    def test_my_day_shows_due_and_overdue(self):
        self._login()
        from django.utils import timezone
        today = timezone.localdate()
        Task.objects.create(
            user=self.alice, title="Due today", due_date=today,
            status=Task.Status.PENDING,
        )
        Task.objects.create(
            user=self.alice, title="Someday", status=Task.Status.PENDING,
        )
        response = self.client.get(reverse("my_day"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Due today")
        self.assertNotContains(response, "Someday")

    def test_inbox_holds_unorganised_captures(self):
        self._login()
        Task.objects.create(
            user=self.alice, title="Fleeting thought",
            status=Task.Status.PENDING, project=None, due_date=None,
        )
        response = self.client.get(reverse("inbox"))
        self.assertContains(response, "Fleeting thought")

    def test_quick_add_requires_title_and_scopes_ownership(self):
        form = QuickAddForm(
            {"title": "Capture me", "priority": Task.Priority.HIGH},
            user=self.alice,
        )
        self.assertTrue(form.is_valid())
        task = form.save_with_user(self.alice)
        self.assertEqual(task.user, self.alice)

    def test_task_form_never_leaks_other_projects(self):
        other = Project.objects.create(user=self.bob, name="Bob's project")
        form = TaskForm(
            {"title": "x", "project": other.pk}, user=self.alice
        )
        self.assertFalse(form.is_valid())

    def test_projects_are_ownership_scoped(self):
        self._login()
        Project.objects.create(user=self.bob, name="Secret project")
        Project.objects.create(user=self.alice, name="Alice project")
        response = self.client.get(reverse("project_list"))
        self.assertContains(response, "Alice project")
        self.assertNotContains(response, "Secret project")

    def test_tags_are_ownership_scoped(self):
        self._login()
        task = self._make_task(title="Tagged task")
        task.tags.add(Tag.objects.create(user=self.alice, name="important"))
        bob_task = Task.objects.create(
            user=self.bob, title="Bob's", status=Task.Status.PENDING
        )
        bob_task.tags.add(Tag.objects.create(user=self.bob, name="hidden-tag"))

        response = self.client.get(reverse("tags_list"))
        self.assertContains(response, "important")
        self.assertNotContains(response, "hidden-tag")

    def test_palette_only_returns_own_rows(self):
        self._login()
        self._make_task(title="Alice's palette task")
        Task.objects.create(
            user=self.bob, title="Bob's palette task",
            status=Task.Status.PENDING,
        )
        response = self.client.get(reverse("palette_json"), {"q": "palette"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        titles = [t["title"] for t in data["tasks"]]
        self.assertIn("Alice's palette task", titles)
        self.assertNotIn("Bob's palette task", titles)

    # --- regressions: filter preservation / security / edge cases --------------

    def test_edit_page_cancel_link_points_at_the_task(self):
        self._login()
        task = self._make_task()
        response = self.client.get(reverse("task_edit", args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, 'href="%s"' % reverse("task_detail", args=[task.pk]),
            msg_prefix="Edit page Cancel link should return to the task detail page.",
        )

    def test_all_tasks_sort_and_pagination_keep_filters(self):
        self._login()
        self._make_task(title="Filtered task")
        response = self.client.get(
            reverse("all_tasks"),
            {"status": Task.Status.PENDING, "priority": Task.Priority.HIGH, "sort": "created"},
        )
        # The sort tabs must carry the active filters.
        self.assertContains(response, "?sort=due&amp;status=pending&amp;priority=high")
        # Pagination links (present even on one page? only >1 pages) — use 30 tasks to force pages.
        for i in range(30):
            self._make_task(title=f"Bulk {i}")
        response = self.client.get(
            reverse("all_tasks"),
            {"status": Task.Status.PENDING, "sort": "created"},
        )
        self.assertContains(response, "&amp;sort=created&amp;status=pending")
        self.assertContains(response, "?page=2&amp;sort=created&amp;status=pending")

    def test_next_parameter_cannot_open_redirect(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("task_toggle", args=[task.pk]),
            {"next": "//evil.example.com/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, "//evil.example.com/phish")
        self.assertNotIn("evil.example.com", response.url)
        # Backslash trick must be rejected too.
        response = self.client.post(
            reverse("task_toggle", args=[task.pk]),
            {"next": "/\\evil.example.com"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response.url)

    def test_past_due_date_is_allowed_on_creation(self):
        self._login()
        today = timezone.localdate()
        two_days_ago = today - timedelta(days=2)
        response = self.client.post(
            reverse("task_create"),
            {"title": "Logged late", "due_date": two_days_ago.isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(user=self.alice, title="Logged late")
        self.assertEqual(task.due_date, two_days_ago)

    def test_project_name_is_validated(self):
        self._login()
        response = self.client.post(reverse("project_create"), {"name": "x" * 200})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Project.objects.filter(user=self.alice, name="x" * 200).exists(),
            "Over-long project name must be rejected, not saved.",
        )
        response = self.client.post(reverse("project_create"), {"name": "   "})
        self.assertFalse(
            Project.objects.filter(user=self.alice).exists(),
            "Blank project name must be rejected.",
        )

    def test_toggle_returns_json_for_xhr(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("task_toggle", args=[task.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], Task.Status.COMPLETED)

    # --- due time + subtasks on the capture forms -----------------------------

    def test_task_form_saves_due_time_and_subtasks(self):
        self._login()
        response = self.client.post(
            reverse("task_create"),
            {
                "title": "Ship the release",
                "due_date": (date.today() + timedelta(days=1)).isoformat(),
                "due_time": "18:00",
                "subtasks": "Update changelog\nRun the build\n; QA pass",
            },
        )
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(user=self.alice, title="Ship the release")
        self.assertEqual(task.due_time.strftime("%H:%M"), "18:00")
        titles = list(task.subtasks.values_list("title", flat=True))
        self.assertEqual(titles, ["Update changelog", "Run the build", "QA pass"])
        self.assertTrue(all(s.user == self.alice for s in task.subtasks.all()))

    def test_task_edit_does_not_recreate_subtasks(self):
        self._login()
        task = self._make_task(title="Existing")
        Subtask.objects.create(user=self.alice, task=task, title="Original")
        response = self.client.post(
            reverse("task_edit", args=[task.pk]),
            {
                "title": "Existing",
                "priority": Task.Priority.MEDIUM,
                "subtasks": "Original\nBrand new",
            },
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        titles = list(task.subtasks.values_list("title", flat=True))
        self.assertEqual(titles, ["Original"], "Editing must never add subtasks.")

    def test_quick_add_accepts_description_due_date_and_time(self):
        self._login()
        response = self.client.post(
            reverse("quick_add"),
            {
                "title": "Call the dentist",
                "description": "Ask about the appointment",
                "priority": Task.Priority.LOW,
                "due_date": date.today().isoformat(),
                "due_time": "09:15",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        task = Task.objects.get(user=self.alice, title="Call the dentist")
        self.assertEqual(task.description, "Ask about the appointment")
        self.assertEqual(task.due_time.strftime("%H:%M"), "09:15")

    def test_task_patch_due_time(self):
        self._login()
        task = self._make_task()
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "due_time", "value": "14:30"},
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.due_time.strftime("%H:%M"), "14:30")
        # A time without a date implies today.
        today = timezone.localdate()
        self.assertEqual(task.due_date, today)

        # Invalid times are rejected.
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "due_time", "value": "not-a-time"},
        )
        self.assertEqual(response.status_code, 400)

        # Clearing the time works and keeps the date.
        today = timezone.localdate()
        response = self.client.post(
            reverse("task_patch", args=[task.pk]),
            {"field": "due_time", "value": ""},
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertIsNone(task.due_time)
        self.assertEqual(task.due_date, today)

    def test_due_time_is_owner_scoped_and_not_leaked_in_forms(self):
        form = QuickAddForm(
            {"title": "Private", "due_time": "12:00", "due_date": date.today().isoformat()},
            user=self.alice,
        )
        self.assertTrue(form.is_valid())
        task = form.save_with_user(self.alice)
        self.assertEqual(task.due_time.strftime("%H:%M"), "12:00")
        self.assertEqual(task.user, self.alice)

    # --- onboarding tour: server-side state -----------------------------------

    def _register(self, username="newbie"):
        data = {
            "username": username,
            "email": f"{username}@example.com",
            "password1": "Str0ng-Pass-2024",
            "password2": "Str0ng-Pass-2024",
        }
        return self.client.post(reverse("register"), data)

    def test_new_user_settings_default_to_not_onboarded(self):
        self._register("newbie")
        self.client.get(reverse("my_day"))  # nav context creates the settings row
        row = UserSettings.objects.get(user__username="newbie")
        self.assertFalse(row.onboarding_done)

    def test_new_user_sees_tour_on_first_page(self):
        self._register("newbie")
        response = self.client.get(reverse("my_day"))
        self.assertTrue(response.context["show_onboarding"])
        self.assertContains(response, 'id="onboardingDialog"')
        self.assertContains(response, "data-complete-url")

    def test_existing_user_with_completed_tour_skips_it(self):
        self._login()
        row = UserSettings.for_user(self.alice)
        row.onboarding_done = True
        row.save(update_fields=["onboarding_done"])
        response = self.client.get(reverse("my_day"))
        self.assertFalse(response.context["show_onboarding"])
        self.assertNotContains(response, 'id="onboardingDialog"')

    def test_onboarding_complete_marks_done_via_xhr(self):
        self._register("newbie")
        response = self.client.post(
            reverse("onboarding_complete"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ok"], True)
        row = UserSettings.objects.get(user__username="newbie")
        self.assertTrue(row.onboarding_done)

    def test_onboarding_complete_requires_login(self):
        response = self.client.post(reverse("onboarding_complete"))
        self.assertEqual(response.status_code, 302)

    def test_onboarding_restart_re_enables_tour(self):
        self._login()
        row = UserSettings.for_user(self.alice)
        row.onboarding_done = True
        row.save(update_fields=["onboarding_done"])
        response = self.client.post(reverse("onboarding_restart"))
        self.assertRedirects(response, reverse("my_day"))
        row = UserSettings.objects.get(user=self.alice)
        self.assertFalse(row.onboarding_done)
        page = self.client.get(reverse("my_day"))
        self.assertTrue(page.context["show_onboarding"])

    def test_onboarding_restart_is_post_only(self):
        self._login()
        response = self.client.get(reverse("onboarding_restart"))
        self.assertEqual(response.status_code, 405)

    # --- quotes ---------------------------------------------------------------

    def test_quote_is_deterministic_and_bounded(self):
        from .quotes import QUOTES, quote_for

        base = date(2026, 1, 5)
        for offset in range(0, 90):
            q = quote_for(base + timedelta(days=offset))
            self.assertEqual(len(q), 2)
            self.assertIn(q, QUOTES)
        self.assertEqual(quote_for(base), quote_for(base))
        self.assertNotEqual(
            quote_for(base), quote_for(base + timedelta(days=7))
        )

    def test_my_day_context_renders_quote_of_the_day(self):
        from .quotes import quote_for

        self._login()
        response = self.client.get(reverse("my_day"))
        text, author = quote_for()
        self.assertContains(response, text)
        self.assertContains(response, author)

    # --- dashboard & analytics context ----------------------------------------

    def test_my_day_renders_ring_and_next_up(self):
        self._login()
        self._make_task(
            title="Due tomorrow thing",
            due_date=timezone.localdate() + timedelta(days=1),
        )
        response = self.client.get(reverse("my_day"))
        self.assertContains(response, "progress-card")
        self.assertContains(response, "ring__bar")
        self.assertContains(response, "Due tomorrow thing")

    def test_productivity_empty_state_without_tasks(self):
        self._login()
        response = self.client.get(reverse("productivity"))
        self.assertFalse(response.context["has_data"])
        self.assertContains(response, "Your productivity, beautifully honest")

    def test_productivity_renders_analytics_with_data(self):
        self._login()
        project = Project.objects.create(user=self.alice, name="Launch")
        tag = Tag.objects.create(user=self.alice, name="ship")
        for title, completed in [
            ("A", True), ("B", True), ("C", True), ("D", False),
        ]:
            task = Task.objects.create(
                user=self.alice, title=title, project=project,
                priority=Task.Priority.MEDIUM,
            )
            if completed:
                task.status = Task.Status.COMPLETED
                task.completed_at = timezone.now()
                task.save(update_fields=["status", "completed_at"])
            task.tags.add(tag)

        response = self.client.get(reverse("productivity"))
        self.assertTrue(response.context["has_data"])
        self.assertEqual(response.context["top_project"], project)
        self.assertEqual(response.context["top_tag"], tag)
        self.assertEqual(response.context["completion_rate"], 75)
        self.assertContains(response, "Last 4 weeks")
        self.assertContains(response, "Launch")



@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="",
    EMAIL_PORT=25,
)
class PasswordResetTests(TestCase):
    """Forgot-password flow: email → 6-digit code → new password.

    Every code path is exercised against the real views, forms and models.
    The email backend is switched to the in-memory ``locmem`` backend so tests
    can inspect exactly what would be sent (this never touches the network).
    """

    def setUp(self):
        # Isolated rate-limit + mail state for every test.
        cache.clear()
        django_mail.outbox = []
        self.alice = User.objects.create_user(
            username="alice", password="Old-Pass-1234", email="alice@example.com"
        )
        self.bob = User.objects.create_user(
            username="bob", password="Old-Pass-1234", email="bob@example.com"
        )

    # --- helpers ---------------------------------------------------------------

    def _request_code(self, email="alice@example.com", client=None):
        client = client or self.client
        return client.post(reverse("password_reset"), {"email": email})

    def _code_from_outbox(self, index=-1):
        self.assertGreater(len(django_mail.outbox), 0, "No email was sent.")
        match = re.search(r"\b(\d{6})\b", django_mail.outbox[index].body)
        self.assertIsNotNone(match, "Email body must contain a 6-digit code.")
        return match.group(1)

    def _verify(self, code, client=None):
        client = client or self.client
        return client.post(reverse("password_reset_verify"), {"code": code})

    def _reach_new_password(self):
        """Walk a full request?verify session so the new-password page is open."""
        self._request_code()
        code = self._code_from_outbox()
        response = self._verify(code)
        self.assertRedirects(response, reverse("password_reset_new_password"))
        return self.client

    # --- 1. page loads ---------------------------------------------------------

    def test_forgot_password_page_loads(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Forgot your password?")
        self.assertContains(response, reverse("login"), msg_prefix="Has a back-to-login link")

    def test_login_page_links_to_forgot_password(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Forgot password?")
        self.assertContains(response, reverse("password_reset"))

    # --- 2/3/5. code generation, delivery & format -----------------------------

    def test_valid_email_generates_reset_code(self):
        response = self._request_code()
        self.assertRedirects(response, reverse("password_reset_verify"))
        row = PasswordResetCode.objects.get(user=self.alice)
        self.assertEqual(len(row.code_hash), 64, "Stored value is a SHA-256 hex hash.")
        self.assertFalse(
            row.code_hash.isdigit() or len(row.code_hash) == 6,
            "Plaintext code must never be stored.",
        )
        self.assertTrue(row.expires_at > timezone.now())

    def test_code_is_6_digits(self):
        self._request_code()
        code = self._code_from_outbox()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_email_is_sent_to_the_right_address(self):
        self._request_code()
        self.assertEqual(len(django_mail.outbox), 1)
        message = django_mail.outbox[0]
        self.assertEqual(message.subject, "Reset your Task Manager password")
        self.assertEqual(message.to, ["alice@example.com"])
        self.assertIn("expires in 10 minutes", message.body)
        self.assertNotIn("Old-Pass-1234", message.body, "Password must never be emailed.")

    # --- 4. no account enumeration ---------------------------------------------

    def test_unknown_email_does_not_reveal_account_existence(self):
        response = self._request_code("nobody@example.com")
        self.assertRedirects(
            response, reverse("password_reset_verify"), fetch_redirect_response=False
        )
        followed = self.client.get(reverse("password_reset_verify"))
        self.assertContains(
            followed,
            "If an account exists with this email address, a verification code has been sent.",
        )
        self.assertEqual(PasswordResetCode.objects.count(), 0)
        self.assertEqual(len(django_mail.outbox), 0)

    def test_known_and_unknown_email_return_identical_shape(self):
        self._request_code("nobody@example.com")  # consumes rate slot
        cache.clear()
        django_mail.outbox = []
        known = self.client.post(reverse("password_reset"), {"email": "alice@example.com"})
        unknown = self.client.post(reverse("password_reset"), {"email": "ghost@example.com"})
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.get("Location"), unknown.get("Location"))

    # --- 6. expiry -------------------------------------------------------------

    def test_code_expires(self):
        self._request_code()
        code = self._code_from_outbox()
        row = PasswordResetCode.objects.get(user=self.alice)
        row.expires_at = timezone.now() - timedelta(minutes=1)
        row.save(update_fields=["expires_at"])

        response = self._verify(code)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This verification code has expired.")

    # --- 7. invalid code -------------------------------------------------------

    def test_invalid_code_is_rejected(self):
        self._request_code()
        response = self._verify("000000")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid verification code.")
        row = PasswordResetCode.objects.get(user=self.alice)
        self.assertEqual(row.attempts, 1)

    # --- 8. correct code -------------------------------------------------------

    def test_correct_code_is_accepted(self):
        self._request_code()
        code = self._code_from_outbox()
        response = self._verify(code)
        self.assertRedirects(response, reverse("password_reset_new_password"))
        row = PasswordResetCode.objects.get(user=self.alice)
        self.assertTrue(row.verified)
        self.assertIsNotNone(row.used_at)

    # --- 9. single-use ---------------------------------------------------------

    def test_code_cannot_be_reused(self):
        self._reach_new_password()
        code = self._code_from_outbox()
        response = self._verify(code)  # same session, same email, same code
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid verification code.")

    # --- 10. new request invalidates old ---------------------------------------

    def test_new_code_invalidates_previous(self):
        self._request_code()
        code_a = self._code_from_outbox()
        cache.clear()  # a fresh request window so the cooldown does not block
        self._request_code()
        code_b = self._code_from_outbox()
        total = PasswordResetCode.objects.filter(user=self.alice).count()
        self.assertEqual(total, 2)

        response = self._verify(code_a)
        self.assertContains(response, "Invalid verification code.")
        response = self._verify(code_b)
        self.assertRedirects(response, reverse("password_reset_new_password"))

    # --- 11. brute-force lockout -----------------------------------------------

    def test_too_many_attempts_invalidate_request(self):
        self._request_code()
        for _ in range(5):
            response = self._verify("111111")
        self.assertContains(response, "Too many failed attempts")
        row = PasswordResetCode.objects.get(user=self.alice)
        self.assertTrue(row.invalidated)
        self.assertEqual(row.attempts, 5)

    # --- 12. resend cooldown / rate limiting -----------------------------------

    def test_resend_respects_cooldown(self):
        self._request_code()
        response = self.client.post(reverse("password_reset_resend"))
        self.assertRedirects(response, reverse("password_reset_verify"))
        self.assertEqual(len(django_mail.outbox), 1, "No second email during cooldown.")

    def test_rate_limit_blocks_excess_requests(self):
        from .password_reset import rate_consume

        rate_consume("alice@example.com")
        rate_consume("alice@example.com")
        response = self._request_code()  # third request within the window
        self.assertEqual(
            response.status_code, 302, "Blocked request back to the request page."
        )
        self.assertRedirects(
            response, reverse("password_reset"), fetch_redirect_response=False
        )
        self.assertEqual(len(django_mail.outbox), 0, "Window-exhausted sends nothing.")
        followed = self.client.get(reverse("password_reset"))
        self.assertContains(followed, "Too many requests")

    # --- 13. password confirmation ---------------------------------------------

    def test_password_confirmation_mismatch_is_rejected(self):
        self._reach_new_password()
        response = self.client.post(
            reverse("password_reset_new_password"),
            {"password1": "N3w-Strong-Pass!x", "password2": "Different-Pass!x"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passwords do not match.")
        self.alice.refresh_from_db()
        self.assertFalse(self.alice.check_password("N3w-Strong-Pass!x"))

    # --- 14. weak password -----------------------------------------------------

    def test_weak_password_is_rejected(self):
        self._reach_new_password()
        response = self.client.post(
            reverse("password_reset_new_password"),
            {"password1": "password", "password2": "password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This password is too common")

    # --- 15/16/17. valid password + login -------------------------------------

    def test_valid_password_is_accepted_and_works(self):
        client = self._reach_new_password()
        new_password = "N3w-Strong-Pass!2026"
        response = client.post(
            reverse("password_reset_new_password"),
            {"password1": new_password, "password2": new_password},
        )
        self.assertRedirects(response, reverse("password_reset_success"))
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.check_password(new_password))
        self.assertFalse(self.alice.check_password("Old-Pass-1234"))
        self.assertEqual(
            PasswordResetCode.objects.filter(
                user=self.alice, invalidated=False, verified=False
            ).count(),
            0,
            "No unconsumed reset request may survive a completed reset.",
        )

    def test_user_can_log_in_with_new_password(self):
        self.test_valid_password_is_accepted_and_works()
        ok = self.client.login(username="alice", password="N3w-Strong-Pass!2026")
        self.assertTrue(ok)

    # --- 18. no direct access to new-password ---------------------------------

    def test_new_password_requires_verification(self):
        response = self.client.get(reverse("password_reset_new_password"))
        self.assertRedirects(response, reverse("password_reset"))

    def test_new_password_session_expires(self):
        client = self._reach_new_password()
        session = client.session

        session["password_reset_expires"] = (
            timezone.now() - timedelta(minutes=1)
        ).isoformat()
        session.save()
        response = client.get(reverse("password_reset_new_password"))
        self.assertRedirects(response, reverse("password_reset"))

    # --- 19. cross-user isolation ---------------------------------------------

    def test_another_user_cannot_use_someone_elses_code(self):
        self._request_code()  # alice's request
        code_a = self._code_from_outbox()

        bob_client = self.client.__class__()
        bob_client.post(reverse("password_reset"), {"email": "bob@example.com"})
        bob_code = self._code_from_outbox()
        self.assertNotEqual(code_a, bob_code)

        # Bob is in his own session and supplies alice's leaked code.
        response = bob_client.post(reverse("password_reset_verify"), {"code": code_a})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid verification code.")
        alice_row = PasswordResetCode.objects.get(user=self.alice)
        self.assertFalse(alice_row.verified, "Alice's code stays usable.")
        self.assertFalse(alice_row.invalidated)

    # --- 20. existing auth still works -----------------------------------------

    def test_login_logout_still_work(self):
        response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "Old-Pass-1234"},
        )
        self.assertRedirects(response, reverse("my_day"))
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
