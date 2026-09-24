/* Task Manager · Navigation — dropdowns, mobile drawer. */

(function () {
    function closeDropdowns(except) {
        document.querySelectorAll(".js-dropdown-menu").forEach(function (menu) {
            if (menu !== except) menu.classList.add("hidden");
        });
    }

    function openMobileDrawer() {
        document.body.classList.add("drawer-open");
    }
    function closeMobileDrawer() {
        document.body.classList.remove("drawer-open");
    }

    document.addEventListener("click", function (ev) {
        // Dropdown menus.
        var trigger = ev.target.closest(".js-dropdown-btn");
        if (trigger) {
            var root = trigger.closest(".js-dropdown");
            var menu = root && root.querySelector(".js-dropdown-menu");
            if (menu) {
                var wasOpen = !menu.classList.contains("hidden");
                closeDropdowns(menu);
                if (!wasOpen) menu.classList.remove("hidden");
            }
            return;
        }

        // Drawer.
        var drawerOpen = ev.target.closest("[data-drawer-open]");
        var drawerClose = ev.target.closest("[data-drawer-close]");
        if (drawerOpen) { openMobileDrawer(); return; }
        if (drawerClose) { closeMobileDrawer(); return; }

        if (!ev.target.closest(".js-dropdown")) closeDropdowns();
    });

    function readDrawer() {
        if (window.innerWidth > 720 && document.body.classList.contains("drawer-open")) {
            closeMobileDrawer();
        }
    }
    window.addEventListener("resize", readDrawer);

    document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") {
            closeDropdowns();
            closeMobileDrawer();
        }
    });
})();