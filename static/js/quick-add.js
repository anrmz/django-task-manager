/* Task Manager · Quick add modal. One primary capture surface everywhere.
   On success the returned row is prepended in place (no reload) wherever the
   task belongs; only pages whose aggregates depend on the change reload. */

(function () {
    var dialog = document.getElementById("quickAddDialog");
    if (!dialog) return;

    var form = dialog.querySelector("[data-quick-add-form]");
    var details = dialog.querySelector("[data-qa-details]");
    var errorBox = dialog.querySelector("[data-qa-error]");
    var toggleBtn = dialog.querySelector("[data-qa-toggle]");
    var pendingNav = null;

    function open() {
        if (dialog.open) {
            var already = form.querySelector("#qa-title");
            if (already) already.focus();
            return;
        }
        form.reset();
        errorBox.classList.add("hidden");
        dialog.showModal();
        var title = form.querySelector("#qa-title");
        if (title) window.setTimeout(function () { title.focus(); }, 40);
    }
    function close() {
        if (!dialog.open) return;
        // Collapse the optional section so the next open starts fresh.
        if (details) details.classList.add("hidden");
        if (toggleBtn) {
            toggleBtn.setAttribute("aria-expanded", "false");
            toggleBtn.textContent = "More details";
        }
        dialog.close();
    }

    TM.openQuickAdd = open;
    TM.closeQuickAdd = close;

    // Openers: header button, mobile FAB, empty states, My Day hero.
    document.addEventListener("click", function (ev) {
        if (ev.target.closest(".js-quick-add-open")) {
            ev.preventDefault();
            open();
        }
    });

    // Closers inside the sheet + clicking the scrim.
    document.addEventListener("click", function (ev) {
        if (ev.target.closest("[data-close-quick-add]")) {
            ev.preventDefault();
            close();
            return;
        }
        if (ev.target === dialog) close();
    });

    // Progressive disclosure for the optional fields.
    if (toggleBtn && details) {
        toggleBtn.addEventListener("click", function () {
            var isNowHidden = details.classList.toggle("hidden");
            var expanded = !isNowHidden;
            toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
            toggleBtn.textContent = expanded ? "Fewer details" : "More details";
        });
    }

    function showError(msg) {
        errorBox.textContent = msg || "";
        errorBox.classList.toggle("hidden", !msg);
    }

    function flashRow(row) {
        row.classList.add("is-new");
        window.setTimeout(function () { row.classList.remove("is-new"); }, 1400);
    }

    function insertRow(data, place) {
        var bucket = null;
        if (place.indexOf("insert:") === 0) bucket = place.split(":")[1];

        var target = null;
        if (bucket) {
            var section = document.querySelector('.list-section[data-bucket="' + bucket + '"]');
            if (section) target = section.querySelector("[data-task-list]");
        }
        if (!target) target = document.querySelector("[data-task-list]");

        if (target) {
            target.insertAdjacentHTML("afterbegin", data.html);
            var row = target.firstElementChild;
            flashRow(row);
            // Dismiss the empty-state if this was the first task.
            var page = target.closest(".app-content");
            if (page) {
                var empty = page.querySelector(".empty-state");
                if (empty) empty.remove();
            }
            close();
            TM.toast('Task "' + data.task.title + '" created.', "success");
            return true;
        }
        return false;
    }

    function softReload(data, place) {
        close();
        TM.toast('Task "' + data.task.title + '" created.', "success");
        pendingNav = window.setTimeout(function () {
            window.location.reload();
        }, 700);
    }

    // Submit via fetch so the sheet never leaves the page; fall back to a
    // plain POST if anything unexpected throws.
    form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var title = (form.querySelector("#qa-title").value || "").trim();
        if (!title) {
            showError("Give the task a title.");
            return;
        }
        showError("");

        var btn = form.querySelector('[type="submit"]');
        btn.disabled = true;

        fetch(form.action, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: new FormData(form),
            credentials: "same-origin",
        })
            .then(function (res) {
                return res.text().then(function (text) {
                    var data;
                    try { data = JSON.parse(text); } catch (e) { throw new Error("bad-response"); }
                    if (!res.ok) throw data;
                    return data;
                });
            })
            .then(function (data) {
                if (TM.updateCounts) TM.updateCounts(data.counts);
                var place = data.place || "toast";
                if (place === "insert" || place.indexOf("insert:") === 0) {
                    if (!insertRow(data, place)) softReload(data, place);
                } else if (place === "reload") {
                    softReload(data, place);
                } else {
                    // Page doesn't list tasks; just confirm quietly.
                    close();
                    TM.toast('Task "' + data.task.title + '" created.', "success");
                }
            })
            .catch(function (err) {
                var data = err && err.errors ? JSON.parse(err.errors) : null;
                var first = data && data.title && data.title[0] && data.title[0].message;
                showError(first || data && data.__all__ && data.__all__[0] && data.__all__[0].message || null);
                if (!first) TM.toast("Couldn't create the task.", "error");
            })
            .finally(function () { btn.disabled = false; });
    });
})();