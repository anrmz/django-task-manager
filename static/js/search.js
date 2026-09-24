/* Task Manager · Command palette. ⌘K/"/Ctrl+K to open, type to search
   tasks/projects/tags, arrow keys to navigate, N for a new task. Actions run
   instantly (no fetch); typing searches with a subtle loading skeleton. */

(function () {
    var dialog = document.getElementById("paletteDialog");
    if (!dialog) return;

    var input = document.getElementById("paletteInput");
    var results = document.getElementById("paletteResults");

    var config = null;
    var script = document.getElementById("tm-config");
    if (script) {
        try { config = JSON.parse(script.textContent); } catch (e) { config = null; }
    }

    var NAV_ICONS = {
        "My Day": "sun", Inbox: "inbox", Upcoming: "calendar",
        "All Tasks": "list", Projects: "folder", Tags: "tag",
        Productivity: "chart", Settings: "settings",
    };
    var PRIO_ICONS = { high: "alert", medium: "clock", low: "clock" };

    var activeIndex = -1;
    var rows = [];
    var debounce = null;
    var lastQuery = "";

    function icon(name, size) {
        return TM.icon(name || "check-circle", size || 15);
    }

    function rowNode(label, sub, iconName, href, query) {
        var el = document.createElement("a");
        el.className = "palette__row";
        el.href = href || "#";
        el.innerHTML = icon(iconName) +
            '<span class="palette__row-label"></span>' +
            '<span class="palette__row-sub"></span>';
        var labelSpan = el.querySelector(".palette__row-label");
        labelSpan.textContent = label;
        if (query) {
            var idx = label.toLowerCase().indexOf(query.toLowerCase());
            if (idx >= 0) {
                labelSpan.innerHTML = label.slice(0, idx) +
                    "<mark>" + label.slice(idx, idx + query.length) + "</mark>" +
                    label.slice(idx + query.length);
            }
        }
        if (sub) el.querySelector(".palette__row-sub").textContent = sub;
        return el;
    }

    function groupLabel(text, count) {
        var el = document.createElement("div");
        el.className = "palette__group-label";
        el.innerHTML = "<span>" + text + "</span>";
        if (count !== undefined) {
            el.insertAdjacentHTML("beforeend", '<span class="count">' + count + "</span>");
        }
        return el;
    }

    function emptyState(text) {
        var el = document.createElement("div");
        el.className = "palette__empty";
        el.textContent = text;
        return el;
    }

    function skeleton() {
        var wrap = document.createElement("div");
        wrap.className = "palette__skeleton";
        for (var i = 0; i < 3; i++) {
            var row = document.createElement("div");
            row.className = "palette__skeleton-row";
            wrap.appendChild(row);
        }
        return wrap;
    }

    function actionRow(label, sub, iconName, run) {
        var el = document.createElement("button");
        el.type = "button";
        el.className = "palette__row palette__row--action";
        el.innerHTML = icon(iconName) +
            '<span class="palette__row-label"></span>' +
            '<span class="palette__row-sub"></span>';
        el.querySelector(".palette__row-label").textContent = label;
        el.querySelector(".palette__row-sub").textContent = sub || "";
        el.addEventListener("click", function () {
            dialog.close();
            run();
        });
        return el;
    }

    function render(payload, q) {
        results.textContent = "";
        results.removeAttribute("aria-busy");
        rows = [];
        activeIndex = -1;
        var groups = [];

        var actions = [
            { label: "New task", sub: "Open the quick capture", icon: "plus", run: function () { if (TM.openQuickAdd) TM.openQuickAdd(); } },
            { label: "Toggle theme", sub: "Light / dark / system", icon: "appearance", run: function () { if (TM.toggleTheme) TM.toggleTheme(); } },
            { label: "Keyboard shortcuts", sub: "See every shortcut", icon: "keyboard", run: function () { openShortcuts(); } },
        ];
        if (document.getElementById("onboardingDialog")) {
            actions.push({
                label: "Start tour", sub: "Replay the welcome tour", icon: "sparkles",
                run: function () { if (TM.startTour) TM.startTour(); },
            });
        }
        groups.push({
            type: "actions",
            title: "Actions",
            items: actions,
        });

        var nav = (config && config.nav) || [];
        groups.push({ type: "nav", title: "Go to", items: nav });

        if (payload) {
            groups.push({
                type: "tasks",
                title: "Tasks",
                items: payload.tasks.map(function (t) {
                    return {
                        label: t.title,
                        sub: [t.project, t.due ? "Due " + t.due : null].filter(Boolean).join(" · "),
                        href: t.url,
                        icon: PRIO_ICONS[t.priority] || "circle",
                    };
                }),
            });
            groups.push({
                type: "projects",
                title: "Projects",
                items: payload.projects.map(function (p) {
                    return { label: p.name, href: p.url, icon: "folder" };
                }),
            });
            groups.push({
                type: "tags",
                title: "Tags",
                items: payload.tags.map(function (t) {
                    return { label: "#" + t, icon: "tag" };
                }),
            });
        }

        var any = false;
        groups.forEach(function (group) {
            if (!group.items.length) return;
            if (group.type === "actions") {
                results.appendChild(groupLabel("Actions"));
                group.items.forEach(function (item) {
                    var el = actionRow(item.label, item.sub, item.icon, item.run);
                    results.appendChild(el);
                    rows.push(el);
                });
                return;
            }
            any = true;
            results.appendChild(groupLabel(group.title, group.items.length));
            group.items.forEach(function (item) {
                var href = item.href;
                if (group.type === "tags") {
                    href = "/tasks/?tag=" + encodeURIComponent(item.label.replace(/^#/, ""));
                }
                var el = rowNode(item.label, item.sub, item.icon, href, q);
                el.addEventListener("click", function () { dialog.close(); });
                results.appendChild(el);
                rows.push(el);
            });
        });

        if (!any) results.appendChild(emptyState("Nothing yet — keep typing, or press N to add a new task."));
    }

    function renderLoading() {
        results.textContent = "";
        rows = [];
        activeIndex = -1;
        results.setAttribute("aria-busy", "true");
        results.appendChild(skeleton());
    }

    function fetchResults(q) {
        if (!config || !config.paletteUrl) return Promise.resolve(null);
        return fetch(config.paletteUrl + "?q=" + encodeURIComponent(q), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (res) { return res.ok ? res.json() : null; })
            .catch(function () { return null; });
    }

    function onInput() {
        var q = input.value.trim();
        lastQuery = q;
        window.clearTimeout(debounce);
        if (!q) { render(null); return; }
        renderLoading();
        debounce = window.setTimeout(function () {
            fetchResults(q).then(function (payload) { render(payload, q); });
        }, 160);
    }

    // -------------------------------------------------------------
    // Keyboard shortcuts dialog
    // -------------------------------------------------------------

    var shortcuts = document.getElementById("shortcutsDialog");
    var SHORTCUTS = [
        ["Ctrl/⌘ K", "Open the command palette"],
        ["N", "New task"],
        ["/", "Search from anywhere"],
        ["Esc", "Close dialogs / clear search"],
        ["↑/↓", "Move through palette results"],
        ["Enter", "Open the selected result"],
        ["d", "Toggle dark mode"],
    ];

    function renderShortcuts() {
        var list = shortcuts.querySelector("[data-shortcuts-list]");
        if (!list) return;
        list.textContent = "";
        SHORTCUTS.forEach(function (pair) {
            var el = document.createElement("li");
            el.innerHTML = "<kbd>" + pair[0] + "</kbd><span>" + pair[1] + "</span>";
            list.appendChild(el);
        });
    }

    function openShortcuts() {
        renderShortcuts();
        shortcuts.showModal();
        var closeBtn = shortcuts.querySelector("[data-close-shortcuts]");
        if (closeBtn) window.setTimeout(function () { closeBtn.focus(); }, 40);
    }

    document.addEventListener("click", function (ev) {
        if (ev.target.closest("[data-close-shortcuts]")) {
            shortcuts.close();
            return;
        }
        if (ev.target === shortcuts) shortcuts.close();
    });

    // -------------------------------------------------------------

    function open() {
        if (dialog.open) {
            input.focus();
            return;
        }
        lastQuery = "";
        input.value = "";
        render(null);
        dialog.showModal();
        window.setTimeout(function () { input.focus(); }, 40);
    }
    function close() {
        if (dialog.open) dialog.close();
    }

    document.addEventListener("click", function (ev) {
        if (ev.target.closest(".js-palette-open")) {
            ev.preventDefault();
            open();
            return;
        }
        if (ev.target === dialog) close();
    });

    input.addEventListener("input", onInput);

    function move(step) {
        if (!rows.length) return;
        activeIndex = (activeIndex + step + rows.length) % rows.length;
        rows.forEach(function (el, i) {
            el.classList.toggle("is-active", i === activeIndex);
            if (i === activeIndex) el.scrollIntoView({ block: "nearest" });
        });
    }

    dialog.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowDown") { ev.preventDefault(); move(1); }
        else if (ev.key === "ArrowUp") { ev.preventDefault(); move(-1); }
        else if (ev.key === "Enter") {
            var row = rows[activeIndex] || rows[0];
            if (row) { ev.preventDefault(); row.click(); }
        } else if (ev.key === "Escape") {
            if (input.value) {
                ev.preventDefault();
                input.value = "";
                onInput();
            } else {
                ev.preventDefault();
                dialog.close();
            }
        }
    });

    function typingInField(ev) {
        var t = ev.target;
        if (t.isContentEditable) return true;
        return /INPUT|TEXTAREA|SELECT/.test(t.tagName);
    }

    document.addEventListener("keydown", function (ev) {
        var k = ev.key;
        var anyDialogOpen = document.querySelector("dialog[open]");
        if ((ev.metaKey || ev.ctrlKey) && k.toLowerCase() === "k") {
            ev.preventDefault();
            open();
            return;
        }
        if (k === "/" && !typingInField(ev) && !anyDialogOpen) {
            ev.preventDefault();
            open();
            return;
        }
        if ((k === "n" || k === "N") && !typingInField(ev) && !anyDialogOpen) {
            ev.preventDefault();
            close();
            if (TM.openQuickAdd) TM.openQuickAdd();
        }
        // d toggles the theme from anywhere (unless typing).
        if ((k === "d" || k === "D") && !typingInField(ev) && !anyDialogOpen) {
            ev.preventDefault();
            if (TM.toggleTheme) TM.toggleTheme();
        }
    });
})();