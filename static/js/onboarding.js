/* Task Manager · First-run onboarding tour.
   Guides new users lazily through the workspace with a spotlight step card
   (native <dialog>). Progress is server-side: finishing/skipping POSTs to
   the onboarding_complete endpoint so the tour never re-appears until the user
   explicitly restarts it from Settings or the command palette.

   Exposes TM.startTour (also used by palette action) and TM.hasTour. */

window.TM = window.TM || {};

(function () {
    var dialog = document.getElementById("onboardingDialog");
    if (!dialog) return;

    var spotlight = dialog.querySelector(".tour__spotlight");
    var media = dialog.querySelector("[data-tour-media]");
    var title = dialog.querySelector("[data-tour-title]");
    var body = dialog.querySelector("[data-tour-body]");
    var hint = dialog.querySelector("[data-tour-hint]");
    var stepLabel = dialog.querySelector("[data-tour-step-label]");
    var points = Array.prototype.slice.call(dialog.querySelectorAll("[data-tour-points] span"));
    var nextBtn = dialog.querySelector("[data-tour-next]");
    var prevBtn = dialog.querySelector("[data-tour-prev]");
    var finishBtn = dialog.querySelector("[data-tour-finish]");

    if (!spotlight || !title || !body) return;

    var ART = {
        welcome: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<circle class="tour-art__soft" cx="12" cy="12" r="3.6"/>' +
            '<path d="M12 2v1.6M12 20.4V22M4.6 4.6l1.1 1.1M18.3 18.3l1.1 1.1M2 12h1.6M20.4 12H22M4.6 19.4l1.1-1.1M18.3 5.7l1.1-1.1"/>' +
            '<circle cx="18.5" cy="5.5" r="1.15"/>' +
            '<circle cx="20.6" cy="9" r="0.8"/></svg>',
        add: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<circle class="tour-art__soft" cx="12" cy="12" r="9.5"/>' +
            '<path d="M9 5.5 6.5 3H3v3.5L5.5 9M15 5.5 17.5 3H21v3.5L18.5 9M15 18.5 17.5 21H21v-3.5L18.5 15M9 18.5 6.5 21H3v-3.5L5.5 15"/>' +
            '<path d="M12 10v4M10 12h4"/></svg>',
        palette: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<circle class="tour-art__soft" cx="11" cy="11" r="7.5"/>' +
            '<path d="m21 21-4.2-4.2"/>' +
            '<rect x="6.5" y="8.5" width="9" height="5" rx="1.4"/></svg>',
        nav: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<rect x="3" y="4" width="7" height="16" rx="1.8"/>' +
            '<rect class="tour-art__soft" x="13" y="4" width="8" height="16" rx="1.8"/>' +
            '<path d="M5.5 8.5h2M5.5 12h2M5.5 15.5h2M15 9.5h4M15 13h4"/></svg>',
        theme: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<circle class="tour-art__soft" cx="9" cy="12" r="4"/>' +
            '<path d="M9 3.5v1.5M9 19v1.5M3.2 6.2l1 1M13.8 16.8l1 1M4 12H2.5M16 12h-2.5"/>' +
            '<path d="M16.6 5.5a5 5 0 0 0 0 10 4.2 4.2 0 0 1 0-10Z"/></svg>',
        done: '<svg class="tour-art" viewBox="0 0 24 24" aria-hidden="true">' +
            '<path d="M5 3h14v4.2a7 7 0 0 1-14 0Z"/>' +
            '<path class="tour-art__soft" d="M5 6H2.6v1a4.6 4.6 0 0 0 4.4 4.5M19 6h2.4v1a4.6 4.6 0 0 1-4.4 4.5"/>' +
            '<path d="M12 13v3.5M8.5 21h7M10 17.5h4V21h-4Z"/></svg>',
    };

    var STEPS = [
        { target: null, art: "welcome", title: "Welcome to Task Manager",
            body: "Plan your day, capture ideas and watch progress grow. This 30-second tour shows you the essentials." },
        { target: "[data-onboard='add-task']", art: "add", title: "Capture anything, fast",
            body: "Use the Add task button \u2014 or press N \u2014 to create a task and set a due date without leaving the page." },
        { target: "[data-onboard='palette']", art: "palette", title: "Search with one key",
            body: "Press Ctrl+K to jump to any task, project or tag, and run commands like the theme toggle." },
        { target: "[data-onboard='nav']", art: "nav", title: "Your day, organised",
            body: "My Day, Inbox and Upcoming keep you focused on what matters. Projects and tags group everything else." },
        { target: "[data-onboard='theme']", art: "theme", title: "Make it yours",
            body: "Switch between light, dark and system appearance \u2014 the whole app follows instantly." },
        { target: null, art: "done", title: "You\u2019re ready",
            body: "Add a task, check it off, then visit Productivity to watch your streaks and trends grow. Enjoy!" },
    ];

    var index = 0;

    function place() {
        var step = STEPS[index];
        var centered = !step.target;
        var target = centered ? null : document.querySelector(step.target);

        if (target) {
            var rect = target.getBoundingClientRect();
            var card = dialog.querySelector(".tour__card");
            var vw = window.innerWidth;
            var vh = window.innerHeight;
            var cardW = card ? card.offsetWidth : 360;
            var cardH = card ? card.offsetHeight : 240;
            var gap = 18;

            dialog.style.setProperty("--spot-x", rect.left + "px");
            dialog.style.setProperty("--spot-y", rect.top + "px");
            dialog.style.setProperty("--spot-w", rect.width + "px");
            dialog.style.setProperty("--spot-h", rect.height + "px");

            var mirror = vw < 900 || rect.right + gap + cardW > vw;
            dialog.classList.toggle("tour--mirror", mirror);
            dialog.classList.remove("tour--centered");
            spotlight.hidden = false;

            var top = Math.min(rect.top, vh - cardH - 16);
            if (top < 10) top = 10;
            // Desktop: pin the card near its target. Mobile: the stylesheet
            // turns the card into a pinned bottom sheet, so leave top unset.
            if (vw > 720) card.style.top = top + "px";
            else if (card.style.top) card.style.top = "";
        } else {
            spotlight.hidden = true;
            dialog.classList.add("tour--centered");
            var reset = dialog.querySelector(".tour__card");
            if (reset) reset.style.top = "";
        }
    }

    function render() {
        var step = STEPS[index];
        var total = STEPS.length;

        stepLabel.textContent = "Step " + (index + 1) + " of " + total;
        title.textContent = step.title;
        body.textContent = step.body;
        hint.hidden = index !== total - 1;
        media.innerHTML = ART[step.art] || "";

        points.forEach(function (p, i) {
            p.classList.toggle("is-active", i === index);
        });

        prevBtn.hidden = index === 0;
        nextBtn.hidden = index === total - 1;
        finishBtn.hidden = index !== total - 1;

        place();
        window.setTimeout(function () {
            (index === 0 ? nextBtn : index === total - 1 ? finishBtn : nextBtn).focus();
        }, 60);
    }

    function next() {
        if (index < STEPS.length - 1) {
            index += 1;
            render();
        } else {
            complete();
        }
    }
    function prev() {
        if (index > 0) {
            index -= 1;
            render();
        }
    }

    function complete() {
        var url = dialog.getAttribute("data-complete-url");
        try {
            fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": dialog.getAttribute("data-csrf") || "",
                },
            });
        } catch (e) { /* non-fatal */ }
        dialog.close();
    }

    function open() {
        index = 0;
        render();
        if (!dialog.open) dialog.showModal();
    }

    nextBtn.addEventListener("click", next);
    prevBtn.addEventListener("click", prev);
    finishBtn.addEventListener("click", complete);
    dialog.querySelector("[data-tour-skip]").addEventListener("click", complete);

    dialog.addEventListener("cancel", function (ev) {
        ev.preventDefault();
        complete();
    });
    dialog.addEventListener("close", function () {
        window.setTimeout(function () { nextBtn.focus(); }, 0);
    });

    dialog.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowRight") { ev.preventDefault(); next(); }
        else if (ev.key === "ArrowLeft") { ev.preventDefault(); prev(); }
        else if (ev.key === "Enter" && !ev.target.closest("button")) {
            ev.preventDefault();
            (index === STEPS.length - 1 ? complete : next)();
        }
    });

    window.addEventListener("resize", function () {
        if (dialog.open) place();
    });

    window.TM.hasTour = true;
    window.TM.startTour = open;

    // First-run: let the page paint before the spotlight appears.
    window.setTimeout(function () {
        if (document.hidden) return;
        open();
    }, 650);
})();