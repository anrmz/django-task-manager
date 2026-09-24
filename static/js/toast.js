/* Task Manager · Toasts. Renders dismissable messages into #toastStack. */

(function () {
    var DEFAULT_DURATION = 3200;

    function iconFor(type) {
        if (type === "success") return "check-circle";
        if (type === "error") return "alert";
        return "info";
    }

    function create(msg, type, action) {
        var el = document.createElement("div");
        el.className = "toast toast--" + (type || "info");
        el.setAttribute("role", type === "error" ? "alert" : "status");
        el.innerHTML =
            TM.icon(iconFor(type), 16) +
            '<span class="toast__msg"></span>' +
            '<button type="button" class="toast__close" aria-label="Dismiss">' +
            TM.icon("x", 14) + "</button>";
        el.querySelector(".toast__msg").textContent = msg;

        if (action && action.label) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "toast__action";
            btn.textContent = action.label;
            btn.addEventListener("click", function () {
                // A single soft-dismiss so the undo is figured out once.
                dismiss(el);
                action.onClick();
            });
            el.appendChild(btn);
        }
        return el;
    }

    function dismiss(el) {
        if (!el || el.classList.contains("is-leaving")) return;
        el.classList.add("is-leaving");
        window.setTimeout(function () { el.remove(); }, 180);
    }

    TM.toast = function (msg, type, duration, action) {
        var stack = document.getElementById("toastStack");
        if (!stack) return;
        var el = create(msg, type || "info", action);
        stack.appendChild(el);
        el.querySelector(".toast__close").addEventListener("click", function () {
            dismiss(el);
        });
        window.setTimeout(function () { dismiss(el); }, duration || DEFAULT_DURATION);
    };

    // Server-rendered messages (Django) behave like everything else.
    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-server-toast]").forEach(function (el) {
            var close = el.querySelector(".toast__close");
            if (close) {
                close.addEventListener("click", function () { dismiss(el); });
            }
            window.setTimeout(function () { dismiss(el); }, DEFAULT_DURATION);
        });
    });
})();