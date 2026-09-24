"""Template helpers for the Task Manager product.

Provides one icon system (clean 24px outline strokes, uniform 2px weight) and
a couple of small presentation filters. Icons render inline as SVG so there is
no external icon font or unicode/emoji mixed in.
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Each icon is the SVG *body* rendered inside a 24x24 stroke-inheriting `<svg>`.
_ICONS = {
    "logo": '<rect x="3" y="3" width="18" height="18" rx="4" /><path d="m9 12 2 2 4-4" />',
    "search": '<circle cx="11" cy="11" r="7.5" /><path d="m21 21-4.2-4.2" />',
    "plus": '<path d="M12 5v14M5 12h14" />',
    "x": '<path d="M18 6 6 18M6 6l12 12" />',
    "sun": '<circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />',
    "appearance": '<circle cx="12" cy="12" r="3" /><path d="M12 2v1M12 21v1M4.2 4.2l.7.7M19.1 19.1l.7.7M2 12h1M21 12h1M4.2 19.8l.7-.7M19.1 4.9l.7-.7" />',
    "check": '<path d="M20 6 9 17l-5-5" />',
    "check-circle": '<circle cx="12" cy="12" r="9.5" /><path d="m8 12 2.5 2.5L16.5 9" />',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2" /><path d="M5.5 5.1 2.2 11.9V19a2 2 0 0 0 2 2h15.6a2 2 0 0 0 2-2v-7.1L18.5 5.1A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1Z" />',
    "calendar": '<rect x="3" y="4.5" width="18" height="17" rx="2.5" /><path d="M8 2.5v4M16 2.5v4M3 10.5h18" />',
    "list": '<rect x="3" y="5" width="6" height="6" rx="1.5" /><path d="m3 17 2 2 4-4M13 6.5h8M13 12.5h8M13 18.5h8" />',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.6 3.9A2 2 0 0 0 7.9 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />',
    "tag": '<path d="M12.6 2.6A2 2 0 0 0 11.2 2H4a2 2 0 0 0-2 2v7.2a2 2 0 0 0 .6 1.4l8.7 8.7a2.4 2.4 0 0 0 3.4 0l6.5-6.5a2.4 2.4 0 0 0 0-3.4Z" /><circle cx="7.5" cy="7.5" r="1" fill="currentColor" stroke="none" />',
    "chart": '<path d="M3 3v18h18" /><path d="m7 14 4-5 3 3 5-7" />',
    "settings": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" /><path d="M1 14h6M9 8h6M17 16h6" />',
    "menu": '<path d="M4 6.5h16M4 12h16M4 17.5h16" />',
    "command": '<path d="M15 5.5V18a2.5 2.5 0 1 0 2.5-2.5H6A2.5 2.5 0 1 0 8.5 18V5.5A2.5 2.5 0 1 0 6 8h12a2.5 2.5 0 1 0-3-2.5Z" />',
    "more": '<circle cx="12" cy="5" r="1.4" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" /><circle cx="12" cy="19" r="1.4" fill="currentColor" stroke="none" />',
    "pencil": '<path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />',
    "trash": '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />',
    "chevron-right": '<path d="m9 18 6-6-6-6" />',
    "chevron-left": '<path d="m15 18-6-6 6-6" />',
    "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6" />',
    "user": '<circle cx="12" cy="7.5" r="3.5" /><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />',
    "logout": '<path d="M9 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3" /><path d="m16 17 5-5-5-5M21 12H9" />',
    "flag": '<path d="M6 22V4" /><path d="M6 4c2.5 0 3.5 1.5 6 1.5S17 4 18.5 4v10c-1.5 0-2.5-1.5-5-1.5S8 14 6 14" />',
    "clock": '<circle cx="12" cy="12" r="9.5" /><path d="M12 7v5l3.5 2" />',
    "circle": '<circle cx="12" cy="12" r="9.5" />',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" />',
    "info": '<circle cx="12" cy="12" r="9.5" /><path d="M12 16v-4M12 8h.01" />',
    "zap": '<path d="M13 2 3 14h7l-1 8 10-12h-7Z" />',
    "trophy": '<path d="M6 3h12v4a6 6 0 0 1-12 0Z" /><path d="M6 6H3v1a4 4 0 0 0 4 4M18 6h3v1a4 4 0 0 1-4 4" /><path d="M12 13v4M8 21h8M10 17h4v4h-4Z" />',
    "target": '<circle cx="12" cy="12" r="9.5" /><circle cx="12" cy="12" r="5.5" /><circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />',
    "filter": '<path d="M21 5H3l7 8v7l4-2.5v-4.5Z" />',
    "sort": '<path d="M7 4v16M7 4 3.5 7.5M7 4l3.5 3.5" /><path d="M17 20V4M17 20l-3.5-3.5M17 20l3.5-3.5" />',
    "calendar-arrow": '<rect x="3" y="4.5" width="18" height="17" rx="2.5" /><path d="M8 2.5v4M16 2.5v4M3 10.5h18" /><path d="m9 18 3 3 3-3M12 21v-9" />',
    "layers": '<path d="m12 2.5 10 5-10 5-10-5Z" /><path d="m2 12.5 10 5 10-5" /><path d="m2 17 10 5 10-5" />',
    "restore": '<path d="M3 12a9 9 0 1 0 2 5.7" /><path d="M3 4v5h5" />',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /><path d="M12 8v4l2.5 1.5" />',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M6 14h.01M18 14h.01M9 14h6" />',
    "sparkles": '<path d="M12 3l1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7Z" /><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8Z" />',
    "x-circle": '<circle cx="12" cy="12" r="9.5" /><path d="m9 9 6 6M15 9l-6 6" />',
}

_FALLBACK = '<circle cx="12" cy="12" r="9" />'


@register.simple_tag
def icon(name, cls="", size=18):
    """Render a 24px-outline icon as inline SVG.

    Usage: ``{% icon "inbox" cls="i-lg" %}`` — stroke inherits ``currentColor``.
    """
    body = _ICONS.get(name, _FALLBACK)
    classes = ("icon " + cls).strip()
    return mark_safe(
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        f"{body}</svg>"
    )


@register.filter
def priority_tone(value):
    """Priority key used for accent styling (flag colour)."""
    return {"low": "low", "medium": "medium", "high": "high"}.get(value, "medium")


@register.filter
def days_until(value):
    """Whole days from today until the given date (negative = in the past)."""
    if not value:
        return None
    from datetime import date
    from django.utils import timezone
    return (value - timezone.localdate()).days


_EVENT_ICONS = {
    "created": "plus",
    "completed": "check-circle",
    "reopened": "restore",
    "deleted": "trash",
    "restored": "restore",
    "priority": "flag",
    "due": "calendar",
    "project": "folder",
    "tags": "tag",
    "subtask_add": "layers",
    "subtask_toggle": "layers",
    "subtask_delete": "x-circle",
}

_EVENT_LINES = {
    "created": "Created the task",
    "completed": "Completed this task",
    "reopened": "Reopened this task",
    "deleted": "Moved to trash",
    "restored": "Restored from trash",
    "priority": "Set priority",
    "due": "Due date",
    "project": "Project",
    "tags": "Updated tags",
    "subtask_add": "Added subtask",
    "subtask_toggle": "Updated subtask",
    "subtask_delete": "Removed subtask",
}


@register.filter
def event_icon(verb):
    return _EVENT_ICONS.get(verb, "circle")


@register.filter
def event_line(event):
    """Friendly one-liner for an activity event, with its detail if any."""
    base = _EVENT_LINES.get(event.verb, event.verb.title())
    if event.detail:
        return f"{base} · {event.detail}"
    return base