"""Daily motivational quotes.

Small enough to live in source: a single rotation of short, public-domain and
widely-attributed lines with authors, selected deterministically by the date so
everyone sees the same quote on the same day (predictable, cache-friendly, and
never dependent on a network). The index is ``date.toordinal() % len(QUOTES)``
so it walks the calendar forward one quote per day and is identical across
servers and timezones for the same local date.
"""

from django.utils import timezone

QUOTES = [
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("You do not have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("A journey of a thousand miles begins with a single step.", "Lao Tzu"),
    ("Focus on being productive instead of busy.", "Tim Ferriss"),
    ("The way to get started is to quit talking and begin doing.", "Walt Disney"),
    ("Simple can be harder than complex: you have to work hard to get your thinking clean to make it simple.", "Steve Jobs"),
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("The future depends on what you do today.", "Mahatma Gandhi"),
    ("Do the hard jobs first. The easy jobs will take care of themselves.", "Dale Carnegie"),
    ("Time isn't the main thing. It's the only thing.", "Miles Davis"),
    ("You miss 100% of the shots you don't take.", "Wayne Gretzky"),
    ("The best way out is always through.", "Robert Frost"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    ("He who has a why to live can bear almost any how.", "Friedrich Nietzsche"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("Don't watch the clock; do what it does. Keep going.", "Sam Levenson"),
    ("The most effective way to do it is to do it.", "Amelia Earhart"),
    ("Whatever you are, be a good one.", "Abraham Lincoln"),
    ("Quality is not an act, it is a habit.", "Aristotle"),
    ("Small deeds done are better than great deeds planned.", "Peter Marshall"),
    ("If you want to make good use of your time, you've got to know what's most important, then give it all you've got.", "Lee Iacocca"),
    ("One of the secrets of productivity is having a really clear ritual for starting your day.", "Benjamin P. Hardy"),
    ("Either you run the day, or the day runs you.", "Jim Rohn"),
    ("Every accomplishment starts with the decision to try.", "John F. Kennedy"),
    ("Action is the foundational key to all success.", "Pablo Picasso"),
]


def quote_for(day=None):
    """Return ``(text, author)`` for the given local date.

    ``None`` (the default) means today. The selection is pure: the same date
    always maps to the same quote, on every server and every run.
    """
    day = day if day is not None else timezone.localdate()
    return QUOTES[day.toordinal() % len(QUOTES)]