import re

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Project, Subtask, Tag, Task, UserSettings


CODE_RE = re.compile(r"^\d{6}$")


class PasswordResetRequestForm(forms.Form):
    """Step 1 — the user's account email. No email address is ever asserted
    to exist here (account enumeration), validation is format-only."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "you@example.com",
                "autocomplete": "email",
                "class": "field__control",
            }
        ),
    )


class PasswordResetCodeForm(forms.Form):
    """Step 2 — the 6-digit verification code. Purely syntactic: existence,
    expiry and brute-force checks happen against the stored hash server-side."""

    code = forms.CharField(
        label="Verification code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "pattern": r"\d{6}",
                "maxlength": "6",
                "class": "field__control field__control--code",
                "aria-describedby": "code-help",
            }
        ),
    )

    def clean_code(self):
        value = self.cleaned_data.get("code", "").strip()
        if not CODE_RE.fullmatch(value or ""):
            raise forms.ValidationError("Enter the 6-digit code from the email.")
        return value


class SetNewPasswordForm(forms.Form):
    """Step 3 — new password. Reuses Django's configured validators and
    ``set_password()``; no custom password rules are invented."""

    error_messages = {
        "password_mismatch": "Passwords do not match.",
        "password_incorrect": "Your old password was entered incorrectly. Please enter it again.",
    }

    password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "class": "field__control"}
        ),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "class": "field__control"}
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password1(self):
        password = self.cleaned_data.get("password1", "")
        if self.user is not None:
            password_validation.validate_password(password, user=self.user)
        else:
            password_validation.validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 != p2:
            raise forms.ValidationError(
                self.error_messages["password_mismatch"],
                code="password_mismatch",
            )
        return cleaned

    def save(self):
        """Persist the new password. Never stores it in plaintext."""
        self.user.set_password(self.cleaned_data["password1"])
        self.user.save(update_fields=["password"])
        return self.user


def _tag_names(text):
    """Split free-text comma/space separated tags into unique names.

    ``#`` prefixes and empty tokens are tolerated so ``"#urgent, meeting "``
    yields ``["urgent", "meeting"]``.
    """
    if not text:
        return []
    parts = [p.strip().lstrip("#") for p in text.replace(";", ",").split(",")]
    return list(dict.fromkeys(p for p in parts if p))


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"placeholder": "yourname", "autocomplete": "username"}
        )
        self.fields["password1"].widget.attrs.update(
            {"placeholder": "Choose a password", "autocomplete": "new-password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"placeholder": "Repeat your password", "autocomplete": "new-password"}
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = "field__control"


class ProjectForm(forms.ModelForm):
    """Server-side validation for project creation (the one place a plain
    POST handler used to accept unchecked input)."""

    class Meta:
        model = Project
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "field__control",
                "placeholder": "New project name\u2026",
                "autocomplete": "off",
                "spellcheck": "false",
                "required": True,
            }),
        }


class _UserOwnedFormMixin:
    """Shared save logic for forms that own their rows server-side.

    ``save_with_user`` commits with the current user as owner and applies the
    free-text tag field; the ``user`` field never appears in the form.
    """

    def _save_tags(self, task, user):
        names = _tag_names(self.cleaned_data.get("tags", ""))
        tags = [Tag.objects.get_or_create(user=user, name=n[:32])[0] for n in names]
        task.tags.set(tags)
        return task

    def _save_subtasks(self, task, user):
        """Materialise the optional free-text subtask list (one per line).

        Subtasks are only created when the task itself is brand new — editing an
        existing task never re-adds or mutates subtask rows, keeping the detail
        page the single source of truth for breakdown editing.
        """
        lines = [
            ln.strip()[:200]
            for ln in self.cleaned_data.get("subtasks", "").replace(";", "\n").splitlines()
            if ln.strip()
        ]
        for index, title in enumerate(lines):
            Subtask.objects.create(user=user, task=task, title=title)

    def save(self, commit=True):
        task = super().save(commit=False)
        user = getattr(self, "_user", None)
        is_new = task.pk is None
        if commit and user is not None:
            task.user = user
            task.save()
            self._save_tags(task, user)
            if is_new:
                self._save_subtasks(task, user)
        return task

    def save_with_user(self, user):
        self._user = user
        return self.save(commit=True)


class TaskForm(_UserOwnedFormMixin, forms.ModelForm):
    """Create/update a task.

    Past due dates are allowed: My Day treats overdue as a normal state, so
    scheduling something already late (e.g. logging a task after the fact) is
    a legitimate workflow rather than an error.
    """

    tags = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(attrs={
            "placeholder": "#urgent, #backend, meeting",
            "autocomplete": "off",
            "spellcheck": "false",
        }),
    )
    due_time = forms.TimeField(
        required=False,
        label="Due time",
        widget=forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        help_text="Optional time-of-day, e.g. 18:00.",
    )
    subtasks = forms.CharField(
        required=False,
        label="Subtasks",
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "One per line — added when the task is created."}
        ),
        help_text="Break the work down before you start.",
    )

    class Meta:
        model = Task
        fields = ["title", "description", "project", "priority", "status", "due_date", "due_time", "tags", "subtasks"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "What's the context?"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("description", "due_date", "due_time", "status", "priority", "project"):
            self.fields[name].required = False
        self.fields["priority"].empty_label = "Priority (optional)"
        self.fields["project"].empty_label = "Project (optional)"

        if user is not None and "project" in self.fields:
            self.fields["project"].queryset = Project.objects.filter(user=user)

        for name, field in self.fields.items():
            css = "field__control"
            if name == "project":
                css += " field__control--select"
            if name == "tags":
                css += " field__control--tags"
            if name in ("due_date", "due_time"):
                css += " field__control--datetime"
            field.widget.attrs["class"] = css

        if self.instance and self.instance.pk:
            existing = self.instance.tags.all()
            if existing:
                self.initial["tags"] = ", ".join(t.name for t in existing)


class QuickAddForm(_UserOwnedFormMixin, forms.ModelForm):
    """Primary capture form — title is the only required field.

    Everything else stays optional so capture is frictionless; users refine
    details later from the task or the full form.
    """

    tags = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "#urgent, #backend"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Add a note, link or context…"}
        ),
    )
    due_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    subtasks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "One per line — added when the task is created."}
        ),
        help_text="Break the work down before you start.",
    )

    class Meta:
        model = Task
        fields = ["title", "description", "priority", "due_date", "due_time", "project", "tags", "subtasks"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update(
            {"placeholder": "What needs to be done?", "autofocus": True}
        )
        for name in ("description", "priority", "due_date", "due_time", "project", "tags", "subtasks"):
            self.fields[name].required = False
        self.fields["priority"].empty_label = "Priority"
        self.fields["project"].empty_label = "Project"

        if user is not None:
            self.fields["project"].queryset = Project.objects.filter(user=user)

        for name, field in self.fields.items():
            css = "field__control"
            if isinstance(field.widget, forms.Select):
                css += " field__control--select"
            if name in ("due_date", "due_time"):
                css += " field__control--datetime"
            field.widget.attrs["class"] = css


class UserPreferencesForm(forms.ModelForm):
    """Appearance + landing behaviour, edited from the Settings page."""

    class Meta:
        model = UserSettings
        fields = ["density", "default_view"]
        widgets = {
            "density": forms.Select(
                attrs={"class": "field__control field__control--select"}
            ),
            "default_view": forms.Select(
                attrs={"class": "field__control field__control--select"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["density"].label = "List density"
        self.fields["density"].help_text = "Tighter rows for power users."
        self.fields["default_view"].label = "Start on"
        self.fields["default_view"].help_text = "The first page you see after signing in."