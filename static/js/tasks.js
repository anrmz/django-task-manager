/* Task Manager · Task completion + trash.
   The checkbox and the delete button are the primary interactions: POST async,
   update the UI in place, and offer an Undo action instead of a hard reload. */

(function () {
    var RELOAD_DELAY = 2600;   // My Day aggregate re-sync, but cancellable.
    var DELETE_NAV_DELAY = 1800;

    function rowFor(form) {
        return form.closest("[data-task-row]");
    }

    function markDone(form, done) {
        var row = rowFor(form);
        if (row) row.classList.toggle("is-completed", done);
        var toggle = form.querySelector(".task__toggle");
        if (toggle) toggle.classList.toggle("is-done", done);
        var input = form.querySelector(".task__toggle-input");
        if (input) input.checked = done;
    }

    function needsReload() {
        // My Day renders aggregate counts/progress that must re-sync.
        return document.querySelector(".progress-card") !== null;
    }

    function navCounter(name) {
        var el = document.querySelector('[data-nav-count="' + name + '"]');
        return el;
    }

    function setCount(name, value) {
        var el = navCounter(name);
        if (!el) return;
        el.textContent = value;
        el.hidden = value === 0;
    }

    function updateCounts(counts) {
        if (!counts) return;
        if (typeof counts.inbox === "number") setCount("inbox", counts.inbox);
        if (typeof counts.upcoming === "number") setCount("upcoming", counts.upcoming);
        if (typeof counts.overdue === "number") setCount("overdue", counts.overdue);
        if (typeof counts.completed === "number") setCount("completed", counts.completed);
    }

    TM.updateCounts = updateCounts;

    function post(url, body) {
        return fetch(url, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: body,
            credentials: "same-origin",
        }).then(function (res) {
            if (!res.ok) throw new Error("Request failed");
            return res.json();
        });
    }

    // ------------------------------------------------------------------
    // Completing / reopening a task
    // ------------------------------------------------------------------

    // A bare checkbox never submits a form on its own, so a toggle must be
    // turned into an explicit requestSubmit(). That fires the "submit" event
    // the handler below is listening for.
    document.addEventListener("change", function (ev) {
        var input = ev.target.closest("[data-task-toggle] .task__toggle-input");
        if (!input) return;
        var form = input.closest("[data-task-toggle]");
        if (!form) return;
        if (form.dataset.busy === "1") {
            // In flight: undo the visual change and ignore the second click.
            input.checked = !input.checked;
            return;
        }
        if (form.requestSubmit) form.requestSubmit();
        else form.submit();
    });

    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-task-toggle]");
        if (!form) return;
        ev.preventDefault();
        if (form.dataset.busy === "1") return;

        var input = form.querySelector(".task__toggle-input");
        var done = !input.checked;

        form.dataset.busy = "1";
        input.disabled = true;

        post(form.action, new FormData(form))
            .then(function (data) {
                var completed = data.status === "completed";
                markDone(form, completed);
                updateCounts(data.counts);
                var reloadTimer = null;
                if (needsReload()) {
                    reloadTimer = window.setTimeout(function () {
                        window.location.reload();
                    }, RELOAD_DELAY);
                }
                TM.toast(completed ? "Task completed." : "Task reopened.", "success", 6000, {
                    label: "Undo",
                    onClick: function () {
                        if (reloadTimer) window.clearTimeout(reloadTimer);
                        form.dataset.busy = "1";
                        input.disabled = true;
                        post(form.action, new FormData(form))
                            .then(function (data2) {
                                markDone(form, !completed);
                                updateCounts(data2.counts);
                                TM.toast("Undone.", "info", 2400);
                            })
                            .catch(function () { TM.toast("Couldn't undo — reloading.", "error"); setTimeout(function () { window.location.reload(); }, 900); })
                            .finally(function () {
                                delete form.dataset.busy;
                                input.disabled = false;
                            });
                    },
                });
            })
            .catch(function () {
                markDone(form, !done);
                TM.toast("Couldn't update the task — try again.", "error");
            })
            .finally(function () {
                delete form.dataset.busy;
                input.disabled = false;
            });
    });

    // ------------------------------------------------------------------
    // Moving a task to trash (reversible) — from the detail or the confirm
    // page the row_anchor isn't needed; we just toast + follow "next".
    // ------------------------------------------------------------------

    function bumpTrash(delta) {
        var el = navCounter("trash");
        if (!el) return;
        var current = parseInt(el.textContent || "0", 10);
        var next = Math.max(0, current + delta);
        el.textContent = next;
        el.hidden = next === 0;
    }

    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-task-delete]");
        if (!form) return;
        ev.preventDefault();
        if (form.dataset.busy === "1") return;
        form.dataset.busy = "1";

        var nextUrl = form.getAttribute("data-next") || "/my-day/";
        var restoreUrl = form.getAttribute("data-restore-url");
        var taskTitle = form.getAttribute("data-title") || "Task";
        var navTimer = null;

        post(form.action, new FormData(form))
            .then(function (data) {
                bumpTrash(1);
                var cancelled = false;
                TM.toast('"' + (data.title || taskTitle) + '" moved to trash.', "info", 4000, {
                    label: "Undo",
                    onClick: function () {
                        cancelled = true;
                        if (navTimer) { window.clearTimeout(navTimer); navTimer = null; }
                        if (!restoreUrl) { TM.toast("Couldn't restore.", "error"); return; }
                        post(restoreUrl, new FormData(form))
                            .catch(function () { return null; })
                            .then(function (res) {
                                if (!res) { TM.toast("Couldn't restore.", "error"); window.location.reload(); return; }
                                bumpTrash(-1);
                                TM.toast("Task restored.", "success", 3000);
                                window.location.reload();
                            });
                    },
                });
                if (!cancelled) {
                    navTimer = window.setTimeout(function () {
                        window.location.href = nextUrl;
                    }, DELETE_NAV_DELAY);
                }
            })
            .catch(function () {
                TM.toast("Couldn't move the task to trash — try again.", "error");
            })
            .finally(function () {
                delete form.dataset.busy;
            });
    });
// ------------------------------------------------------------------
    // Row actions popover: Task details / Edit / Set date / Move to trash
    // ------------------------------------------------------------------

    function pad2(n) { return n < 10 ? "0" + n : "" + n; }

    function dateTokenISO(token) {
        var now = new Date();
        var d = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (token === "tomorrow") d.setDate(d.getDate() + 1);
        if (token === "next-week") d.setDate(d.getDate() + 7);
        return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    }

    function parseISO(value) {
        var p = String(value).split("-").map(Number);
        return new Date(p[0], p[1] - 1, p[2]);
    }

    function closeRowMenus() {
        document.querySelectorAll(".js-row-menu").forEach(function (b) {
            b.setAttribute("aria-expanded", "false");
        });
        document.querySelectorAll(".row-menu").forEach(function (m) {
            m.classList.add("hidden");
        });
    }

    document.addEventListener("click", function (ev) {
        var trigger = ev.target.closest(".js-row-menu");
        if (trigger) {
            ev.preventDefault();
            var open = trigger.getAttribute("aria-expanded") === "true";
            closeRowMenus();
            if (!open) {
                trigger.setAttribute("aria-expanded", "true");
                var menu = trigger.nextElementSibling;
                if (menu) {
                    menu.classList.remove("hidden");
                    menu.classList.remove("is-up");
                    if (window.matchMedia("(max-width: 720px)").matches) {
                        var host = trigger.closest(".task__actions");
                        var spaceBelow = window.innerHeight - (host ? host.getBoundingClientRect().bottom : trigger.getBoundingClientRect().bottom);
                        if (menu.offsetHeight > spaceBelow) menu.classList.add("is-up");
                        window.requestAnimationFrame(function () {
                            menu.scrollIntoView({ block: "nearest", inline: "nearest" });
                        });
                    }
                }
            }
            return;
        }
        if (ev.target.closest(".row-menu")) return;
        closeRowMenus();
    });

    document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") closeRowMenus();
    });

    // Set date from the popover (inline patch, no reload).
    document.addEventListener("click", function (ev) {
        var btn = ev.target.closest("[data-row-patch]");
        if (!btn) return;
        ev.preventDefault();
        var row = btn.closest("[data-task-row]");
        if (!row) return;
        var pk = row.getAttribute("data-task-row");
        var field = btn.getAttribute("data-row-patch");
        var raw = btn.getAttribute("data-value") || "";
        var value = field === "due_date" && raw ? dateTokenISO(raw) : raw;

        var fd = new FormData();
        fd.append("field", field);
        fd.append("value", value);

        post("/tasks/" + pk + "/patch/", fd)
            .then(function () {
                closeRowMenus();
                renderDueChip(row, value);
                TM.toast("Due date updated.", "success", 2400);
            })
            .catch(function () {
                TM.toast("Couldn't update the date — try again.", "error");
            });
    });

    var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    function renderDueChip(row, value) {
        var wrap = row.querySelector("[data-row-due]");
        if (!value) {
            if (wrap) wrap.remove();
            return;
        }
        if (!wrap) return;

        var today = new Date();
        var start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        var d = parseISO(value);
        var diff = Math.round((d - start) / 86400000);
        var time = wrap.getAttribute("data-row-time");

        var cls = "chip task__due";
        var iconName = "calendar";
        var label;
        if (diff < 0) { cls += " chip--overdue"; iconName = "alert"; label = months2(d) + " " + d.getDate() + " \u00b7 Overdue"; }
        else if (diff === 0) { cls += " task__due--today"; label = "Today"; }
        else if (diff === 1) { label = "Tomorrow"; }
        else { label = months2(d) + " " + d.getDate(); }
        var label2 = label + (time ? " \u00b7 " + hhmm12(time) : "");

        wrap.className = cls;
        wrap.innerHTML = TM.icon(iconName, 13) + label2;
    }

    function months2(d) { return MONTHS[d.getMonth()]; }
    function hhmm12(hhmm) {
        if (!hhmm) return "";
        var p = hhmm.split(":");
        var h = parseInt(p[0], 10);
        var m = parseInt(p[1] || "0", 10);
        var ampm = h >= 12 ? "PM" : "AM";
        var h12 = h % 12 || 12;
        return h12 + (m ? ":" + pad2(m) : "") + " " + ampm;
    }

    // Move to trash straight from the row, with Undo.
    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-row-delete]");
        if (!form) return;
        ev.preventDefault();
        if (form.dataset.busy === "1") return;
        form.dataset.busy = "1";

        var row = form.closest("[data-task-row]");
        var titleEl = row && row.querySelector(".task__title");
        var title = (titleEl && titleEl.textContent.trim()) || "Task";
        var restoreUrl = form.action.replace(/\/delete\/$/, "/restore/");

        post(form.action, new FormData(form))
            .then(function () {
                closeRowMenus();
                bumpTrash(1);
                row.classList.add("is-removing");
                window.setTimeout(function () { row.remove(); }, 200);
                TM.toast('"' + title + '" moved to trash.', "info", 4000, {
                    label: "Undo",
                    onClick: function () {
                        var rest = new FormData();
                        post(restoreUrl, rest)
                            .then(function () {
                                bumpTrash(-1);
                                TM.toast("Task restored.", "success", 3000);
                                window.location.reload();
                            })
                            .catch(function () { TM.toast("Couldn't restore.", "error"); });
                    },
                });
            })
            .catch(function () {
                TM.toast("Couldn't move the task to trash — try again.", "error");
            })
            .finally(function () {
                delete form.dataset.busy;
            });
    });

    // ------------------------------------------------------------------
    // All Tasks filter toolbar: apply selects/checkbox instantly.
    // ------------------------------------------------------------------

    document.addEventListener("change", function (ev) {
        var form = ev.target.closest("[data-filter-form]");
        if (!form) return;
        var t = ev.target;
        var auto = t.tagName === "SELECT" || (t.tagName === "INPUT" && t.type === "checkbox");
        if (!auto) return;
        form.submit();
    });
})();