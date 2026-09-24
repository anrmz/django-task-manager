/* Task Manager · Task detail page.
   Subtask add/toggle/remove via async fetch, plus inline priority/due
   editing that posts to the patch endpoint without leaving the page. */

(function () {
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
    // Subtask progress + rows
    // ------------------------------------------------------------------

    function progressEls() {
        return {
            chip: document.querySelector("[data-subtask-progress]"),
            bar: document.querySelector("[data-subtask-progressbar] .subtask__progress-fill"),
            empty: document.querySelector(".subtask-empty"),
        };
    }

    function setProgress(done, total) {
        var els = progressEls();
        if (!els.chip && !els.bar) return;
        var pct = total ? Math.round((done / total) * 100) : 0;
        if (els.chip) els.chip.textContent = done + "/" + total;
        if (els.bar) els.bar.style.width = pct + "%";
        if (els.bar) els.bar.closest("[data-subtask-progressbar]").classList.toggle("is-full", total > 0 && done === total);
    }

    // Add: the server returns the rendered row; insert and clear the box.
    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-subtask-add]");
        if (!form) return;
        ev.preventDefault();
        var input = form.querySelector("input[name=title]");
        var title = (input.value || "").trim();
        if (!title) return;
        var btn = form.querySelector('[type="submit"]');
        btn.disabled = true;

        post(form.action, new FormData(form))
            .then(function (data) {
                var list = document.querySelector("[data-subtask-list]");
                if (list) {
                    list.insertAdjacentHTML("beforeend", data.html);
                }
                var empty = document.querySelector(".subtask-empty");
                if (empty) empty.remove();
                setProgress(data.done, data.total);
                input.value = "";
                input.focus();
            })
            .catch(function () {
                TM.toast("Couldn't add the subtask — try again.", "error");
            })
            .finally(function () { btn.disabled = false; });
    });

    function subtaskRow(form) {
        return form.closest("[data-subtask-row]");
    }

    function markSubtask(li, done) {
        var check = li.querySelector(".subtask__check");
        if (check) {
            check.classList.toggle("is-done", done);
            var icon = check.querySelector(".icon");
            if (done && !icon) check.insertAdjacentHTML("afterbegin", TM.icon("check", 12));
            if (!done && icon) icon.remove();
        }
        var title = li.querySelector(".subtask__title");
        if (title) title.classList.toggle("is-done", done);
    }

    // Toggle: flip the check state, then sync progress numbers.
    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-subtask-toggle]");
        if (!form) return;
        ev.preventDefault();
        var li = subtaskRow(form);
        var check = form.querySelector(".subtask__check");
        var newDone = !check.classList.contains("is-done");
        form.dataset.busy = "1";

        post(form.action, new FormData(form))
            .then(function (data) {
                markSubtask(li, data.done);
                setProgress(data.done_count, data.total);
            })
            .catch(function () {
                TM.toast("Couldn't update the subtask — try again.", "error");
            })
            .finally(function () { delete form.dataset.busy; });
    });

    // Remove: delete the row (server also re-renders progress).
    document.addEventListener("submit", function (ev) {
        var form = ev.target.closest("[data-subtask-delete]");
        if (!form) return;
        ev.preventDefault();
        var li = subtaskRow(form);

        post(form.action, new FormData(form))
            .then(function (data) {
                li.remove();
                setProgress(data.done, data.total);
            })
            .catch(function () {
                TM.toast("Couldn't remove the subtask — try again.", "error");
            });
    });

    // ------------------------------------------------------------------
    // Inline priority / due date
    // ------------------------------------------------------------------

    function flashSaved(dd) {
        var mark = dd.querySelector(".inline-saved");
        if (mark) return; // already showing
        mark = document.createElement("span");
        mark.className = "inline-saved";
        mark.textContent = "Saved";
        dd.appendChild(mark);
        window.setTimeout(function () { mark.remove(); }, 1600);
    }

    function patchUrl() {
        var pkEl = document.querySelector("[data-task-pk]");
        return "/tasks/" + (pkEl ? pkEl.dataset.taskPk : "") + "/patch/";
    }

    document.addEventListener("change", function (ev) {
        var dd = ev.target.closest("[data-inline-field=priority]");
        if (!dd) return;
        var select = ev.target;
        var previous = select.value;

        var body = new FormData();
        body.append("field", "priority");
        body.append("value", select.value);

        post(patchUrl(), body)
            .then(function () { flashSaved(dd); })
            .catch(function () { select.value = previous; TM.toast("Couldn't update priority.", "error"); });
    });

    document.addEventListener("change", function (ev) {
        var dd = ev.target.closest("[data-inline-field=due_date]");
        if (!dd) return;
        var input = ev.target;
        var previous = input.value;

        var body = new FormData();
        body.append("field", "due_date");
        body.append("value", input.value);

        post(patchUrl(), body)
            .then(function () { flashSaved(dd); })
            .catch(function () { input.value = previous; TM.toast("Couldn't update the due date.", "error"); });
    });

    // Due time: may imply "today" server-side, so reflect the resulting date.
    document.addEventListener("change", function (ev) {
        var dd = ev.target.closest("[data-inline-field=due_time]");
        if (!dd) return;
        var input = ev.target;
        var previous = input.value;

        var body = new FormData();
        body.append("field", "due_time");
        body.append("value", input.value);

        post(patchUrl(), body)
            .then(function (data) {
                flashSaved(dd);
                var dateInput = document.querySelector("[data-inline-field=due_date] input[type=date]");
                if (dateInput && data.due) {
                    dateInput.value = data.due;
                    dateInput.classList.toggle("is-overdue", new Date(data.due + "T00:00:00") < new Date());
                }
            })
            .catch(function () {
                input.value = previous;
                TM.toast("Couldn't update the due time.", "error");
            });
    });
})();