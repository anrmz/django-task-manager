/* Task Manager · Theme. Preferences persist in localStorage; the FOUC-free
   base inline snippet reads them first, this module wires the UI. */

(function () {
    var KEY = "taskmanager.theme";

    function current() {
        try { return window.localStorage.getItem(KEY) || "system"; } catch (e) { return "system"; }
    }
    function save(pref) {
        try { window.localStorage.setItem(KEY, pref); } catch (e) {}
    }
    function isDarkPref(pref) {
        return pref === "dark" || (pref === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    }
    function syncChoices(pref) {
        document.querySelectorAll(".js-theme-choice").forEach(function (btn) {
            var active = btn.getAttribute("data-theme-pref") === pref;
            btn.classList.toggle("is-active", active);
            btn.setAttribute("aria-checked", active ? "true" : "false");
        });
    }
    function apply(pref) {
        var root = document.documentElement;
        var dark = isDarkPref(pref);
        root.setAttribute("data-theme", dark ? "dark" : "light");
        root.setAttribute("data-theme-pref", pref);
        var meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.setAttribute("content", dark ? "#0b0b0d" : "#f7f7f8");
        syncChoices(pref);
    }

    var media = window.matchMedia("(prefers-color-scheme: dark)");
    function watchSystem() {
        if (current() === "system") apply("system");
    }
    if (media.addEventListener) media.addEventListener("change", watchSystem);
    else if (media.addListener) media.addListener(watchSystem);

    TM.toggleTheme = function () {
        // cycle light -> dark -> system
        var order = ["light", "dark", "system"];
        var now = current();
        var next = order[(order.indexOf(now) + 1) % order.length];
        save(next);
        apply(next);
    };

    document.addEventListener("click", function (ev) {
        var choice = ev.target.closest(".js-theme-choice");
        if (!choice) return;
        var pref = choice.getAttribute("data-theme-pref");
        save(pref);
        apply(pref);
    });

    apply(current());
})();