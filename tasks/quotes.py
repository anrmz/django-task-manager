"""Daily motivational quotes.

Small enough to live in source: a single rotation of short, widely-attributed
lines with authors, curated toward focus, discipline, consistency, deep work,
execution and calm. Selection has two layers:

* ``quote_for(day)`` is pure and deterministic — the same local date always
  maps to the same quote (cache-friendly, no network, stable across servers).
  The index is ``date.toordinal() % len(QUOTES)`` so it walks forward one
  quote per day.

* ``rotating_quote(request, day)`` guarantees the *session* sees a different
  quote on every page refresh. It keeps a short recall of previously served
  quote indices (a handful, stored as plain integers in the session — no
  personal data) and picks from the remainder, so the same quote can never
  appear twice in a row. If the session is unavailable it falls back to the
  deterministic daily quote for graceful degradation.
"""

import random

from django.utils import timezone

# How many previously-shown quotes the session remembers so they are excluded
# from the next pick. Big enough to reliably avoid repeats, small enough that
# the collection never feels exhausted.
_RECALL = 6

# All attributions are intentionally safe: public-domain or widely-accepted
# authors. Attribution was deliberately NOT invented for any line.
QUOTES = [
    # --- Execution ----------------------------------------------------------
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("You do not have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("A journey of a thousand miles begins with a single step.", "Lao Tzu"),
    ("The way to get started is to quit talking and begin doing.", "Walt Disney"),
    ("Action is the foundational key to all success.", "Pablo Picasso"),
    ("Do what you can, with what you have, where you are.", "Theodore Roosevelt"),
    ("Small deeds done are better than great deeds planned.", "Peter Marshall"),
    ("Great things are done by a series of small things brought together.", "Vincent van Gogh"),
    # --- Focus / deep work --------------------------------------------------
    ("Focus on being productive instead of busy.", "Tim Ferriss"),
    ("Simple can be harder than complex: you have to work hard to get your thinking clean to make it simple.", "Steve Jobs"),
    ("The successful warrior is the average man, with laser-like focus.", "Bruce Lee"),
    ("One of the secrets of productivity is having a really clear ritual for starting your day.", "Benjamin P. Hardy"),
    ("The most effective way to do it is to do it.", "Amelia Earhart"),
    ("Waste no more time arguing about what a good man should be. Be one.", "Marcus Aurelius"),
    # --- Discipline / consistency -------------------------------------------
    ("Quality is not an act, it is a habit.", "Aristotle"),
    ("Don't watch the clock; do what it does. Keep going.", "Sam Levenson"),
    ("Energy and persistence conquer all things.", "Benjamin Franklin"),
    ("Do the hard jobs first. The easy jobs will take care of themselves.", "Dale Carnegie"),
    ("The impediment to action advances action. What stands in the way becomes the way.", "Marcus Aurelius"),
    ("It's not that I'm so smart, it's just that I stay with problems longer.", "Albert Einstein"),
    # --- Time / priorities --------------------------------------------------
    ("Time isn't the main thing. It's the only thing.", "Miles Davis"),
    ("It is not that we have a short time to live, but that we waste a lot of it.", "Seneca"),
    ("Begin at once to live, and count each separate day as a separate life.", "Seneca"),
    ("How we spend our days is, of course, how we spend our lives.", "Annie Dillard"),
    ("Time you enjoy wasting is not wasted time.", "Marthe Troly-Curtin"),
    ("Either you run the day, or the day runs you.", "Jim Rohn"),
    ("What gets measured gets managed.", "Peter Drucker"),
    ("Half our life is spent trying to find something to do with the time we have rushed through life trying to save.", "Will Rogers"),
    # --- Progress / resilience ----------------------------------------------
    ("It always seems impossible until it's done.", "Nelson Mandela"),
    ("Start where you are. Use what you have. Do what you can.", "Arthur Ashe"),
    ("Every accomplishment starts with the decision to try.", "John F. Kennedy"),
    ("The future depends on what you do today.", "Mahatma Gandhi"),
    ("Every moment is a fresh beginning.", "T. S. Eliot"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    # --- Craft / meaning ----------------------------------------------------
    ("Whatever you are, be a good one.", "Abraham Lincoln"),
    ("He who has a why to live can bear almost any how.", "Friedrich Nietzsche"),
    ("The best way out is always through.", "Robert Frost"),
]


def _slot(day):
    """Deterministic collection index for a local date."""
    return day.toordinal() % len(QUOTES)


def quote_for(day=None):
    """Return ``(text, author)`` for the given local date.

    ``None`` (the default) means today. The selection is pure: the same date
    always maps to the same quote, on every server and every run.
    """
    day = day if day is not None else timezone.localdate()
    return QUOTES[_slot(day)]


def rotating_quote(request, day=None):
    """Return ``(text, author)`` for ``request``, rotated per session.

    Every call is guaranteed to differ from the last few quotes already shown
    to this session, so each refresh of My Day serves a new quote with no
    immediate repetition. Only short integer indices touch ``request.session``;
    nothing personal is stored. If the session is unavailable (or serialising
    fails), it safely falls back to the deterministic quote for the day.
    """
    day = day if day is not None else timezone.localdate()
    fallback = _slot(day)

    recall = []
    try:
        raw = request.session.get("quote_recall") or []
        recall = [int(i) for i in raw if isinstance(i, int) or str(i).lstrip("-").isdigit()]
    except Exception:
        recall = []
    recall = [i for i in recall if 0 <= i < len(QUOTES)][-_RECALL:]

    candidates = [i for i in range(len(QUOTES)) if i not in recall] or [fallback]
    chosen = random.choice(candidates)

    try:
        request.session["quote_recall"] = (recall + [chosen])[-_RECALL:]
    except Exception:
        pass

    return QUOTES[chosen]