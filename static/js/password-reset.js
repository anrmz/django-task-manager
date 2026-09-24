/* Task Manager · password-reset flow
   Enables the resend button after the server-side cooldown and keeps the
   verify button disabled until exactly 6 digits are entered. Pure
   enhancement — server enforces everything anyway. */

(function () {
    "use strict";

    // --- 6-digit entry: auto-enable + paste a full code ---------------------
    var codeInput = document.getElementById("id_code");
    var verifyBtn = document.getElementById("verifyBtn");

    if (codeInput) {
        var refresh = function () {
            var ready = /^\d{6}$/.test(codeInput.value.trim());
            if (verifyBtn) verifyBtn.disabled = !ready;
        };
        codeInput.addEventListener("input", refresh);
        refresh();
        if (typeof codeInput.focus === "function") codeInput.focus();
    }

    // --- resend cooldown -----------------------------------------------------
    var timer = document.getElementById("resendTimer");
    var resendBtn = document.getElementById("resendBtn");

    function enableResend() {
        if (resendBtn) resendBtn.disabled = false;
        if (timer) timer.hidden = true;
    }

    if (resendBtn && timer && timer.dataset.wait) {
        var remaining = parseInt(timer.dataset.wait, 10) || 0;
        var render = function () {
            timer.textContent = "Resend available in " + remaining + "s";
            if (remaining <= 0) {
                enableResend();
                window.clearInterval(interval);
            }
            remaining -= 1;
        };
        render();
        var interval = window.setInterval(render, 1000);
    } else if (resendBtn) {
        resendBtn.disabled = false;
    }
})();