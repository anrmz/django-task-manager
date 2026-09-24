/* Task Manager · Task editor (premium capture surface).
   One primary capture flow everywhere: title first, deterministic smart-parse
   fills due/priority/tags, everything parsed stays visible & revertible, and
   nothing is ever claimed to be AI. On success the row is inserted in place. */

(function () {
    var dialog = document.getElementById("quickAddDialog");
    if (!dialog) return;

    var form = dialog.querySelector("[data-quick-add-form]");
    if (!form) return;

    var title = dialog.querySelector("#qa-title");
    var errorBox = dialog.querySelector("[data-qa-error]");
    var dateInput = dialog.querySelector("#qa-due");
    var timeInput = dialog.querySelector("#qa-time");
    var priorityValue = dialog.querySelector("[data-priority-value]");
    var priorityBtns = dialog.querySelectorAll("[data-priority]");
    var dueBtns = dialog.querySelectorAll("[data-due-quick]");
    var projectInput = dialog.querySelector("[data-project-input]");
    var projectValue = dialog.querySelector("[data-project-value]");
    var tagsInput = dialog.querySelector("[data-tags-input]");
    var tagsValue = dialog.querySelector("[data-tags-value]");
    var tagsChips = dialog.querySelector("[data-tags-chips]");
    var moreToggle = dialog.querySelector("[data-more-toggle]");
    var moreBody = dialog.querySelector("[data-more-body]");
    var parseChips = dialog.querySelector("[data-parse-chips]");
    var eyebrow = dialog.querySelector("[data-editor-context]");
    var submitBtn = dialog.querySelector("[data-editor-submit]");

    var pendingNav = null;

    // ---- User-intent flags: smart parse never overrides explicit choices ----
    var userPickedDate = false;
    var userPickedTime = false;
    var userPickedPriority = false;

    // ---- Date helpers (all local — never UTC) -------------------------------

    function pad(n) { return n < 10 ? "0" + n : "" + n; }
    function iso(date) {
        return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
    }
    function today() {
        var d = new Date();
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }
    function addDays(date, n) {
        var d = new Date(date);
        d.setDate(d.getDate() + n);
        return d;
    }
    function parseISO(value) {
        if (!value) return null;
        var parts = String(value).split("-").map(Number);
        return new Date(parts[0], parts[1] - 1, parts[2]);
    }
    var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    function dateLabel(date) {
        var now = today();
        if (iso(date) === iso(now)) return "Today";
        if (iso(date) === iso(addDays(now, 1))) return "Tomorrow";
        var label = DAYS[date.getDay()] + ", " + MONTHS[date.getMonth()] + " " + date.getDate();
        if (date.getFullYear() !== now.getFullYear()) label += " " + date.getFullYear();
        return label;
    }
    function timeLabel(hhmm) {
        if (!hhmm) return "";
        var parts = hhmm.split(":");
        var h = parseInt(parts[0], 10);
        var m = parseInt(parts[1] || "0", 10);
        var ampm = h >= 12 ? "PM" : "AM";
        var h12 = h % 12 || 12;
        return h12 + (m ? ":" + pad(m) : "") + " " + ampm;
    }

    // ---- Chips -------------------------------------------------------------

    function chipHTML(type, label) {
        return (
            '<span class="parsed-chip parsed-chip--' + type + '">' +
            '<span> ' + label + '</span>' +
            '<button type="button" class="parsed-chip__remove" aria-label="Remove ' + type + '" data-chip-remove>&#215;</button>' +
            "</span>"
        );
    }

    function addParseChip(type, label, undo) {
        if (!parseChips) return;
        parseChips.classList.remove("hidden");
        var el = document.createElement("span");
        el.innerHTML = chipHTML(type, label);
        el.classList.add("parsed-chip");
        var frag = el.firstElementChild;
        var btn = frag.querySelector("[data-chip-remove]");
        btn.addEventListener("click", function () {
            undo();
            frag.remove();
            if (!parseChips.querySelector(".parsed-chip")) parseChips.classList.add("hidden");
        });
        parseChips.appendChild(frag);
    }

    function setPriority(prio, fromUser) {
        priorityValue.value = prio;
        priorityBtns.forEach(function (b) {
            var active = b.getAttribute("data-priority") === prio;
            b.classList.toggle("is-active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
        });
        if (fromUser) userPickedPriority = true;
    }

    function setDate(date, fromUser) {
        dateInput.value = date ? iso(date) : "";
        dateInput.classList.toggle("is-set", !!date);
        syncDueSegments();
        if (fromUser) userPickedDate = true;
    }

    function setTime(hhmm, fromUser) {
        timeInput.value = hhmm || "";
        timeInput.classList.toggle("is-set", !!hhmm);
        if (fromUser) userPickedTime = true;
    }

    function syncDueSegments() {
        var value = dateInput.value;
        var none = !value;
        var isToday = value === iso(today());
        var isTomorrow = value === iso(addDays(today(), 1));
        dueBtns.forEach(function (b) {
            var key = b.getAttribute("data-due-quick");
            var active = (key === "none" && none) || (key === "today" && isToday) || (key === "tomorrow" && isTomorrow);
            b.classList.toggle("is-active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
        });
    }

    // ---- Tags ---------------------------------------------------------------

    function tagNames() {
        var out = [];
        tagsChips.querySelectorAll(".editor__tag").forEach(function (chip) {
            var n = chip.getAttribute("data-tag");
            if (n && out.indexOf(n) === -1) out.push(n);
        });
        return out;
    }
    function persistTags() {
        tagsValue.value = tagNames().map(function (n) { return "#" + n; }).join(", ");
    }
    function addTag(name, fromParse) {
        name = String(name).replace(/^#/, "").trim();
        if (!name) return;
        if (tagNames().indexOf(name) !== -1) return;
        tagsChips.classList.remove("hidden");
        var chip = document.createElement("span");
        chip.className = "editor__tag";
        chip.setAttribute("data-tag", name);
        chip.innerHTML = "#" + name +
            '<button type="button" class="editor__tag__x" aria-label="Remove tag ' + name + '">' +
            '<svg class="icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>';
        chip.querySelector(".editor__tag__x").addEventListener("click", function () {
            chip.remove();
            if (!tagsChips.querySelector(".editor__tag")) tagsChips.classList.add("hidden");
            persistTags();
        });
        tagsChips.appendChild(chip);
        persistTags();
        if (fromParse && parseChips) {
            addParseChip("tag", "#" + name, function () {
                var chipEl = tagsChips.querySelector('[data-tag="' + name + '"]');
                if (chipEl) chipEl.remove();
                if (!tagsChips.querySelector(".editor__tag")) tagsChips.classList.add("hidden");
                persistTags();
            });
        }
        if (tagsInput) tagsInput.value = "";
    }

    // ---- Notes / tags datalist ----------------------------------------------

    var dl = dialog.querySelector("#editor-tags");
    if (dl) {
        try {
            var tmCfg = document.getElementById("tm-config");
            var tagsHint = tmCfg && JSON.parse(tmCfg.textContent).tagOptions;
            (tagsHint || []).forEach(function (t) {
                var opt = document.createElement("option");
                opt.value = t;
                dl.appendChild(opt);
            });
        } catch (e) { /* datalist suggestions are a nicety only */ }
    }

    // ---- Smart parse (deterministic, transparent) ----------------------------

    var WEEKS = { mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6, sun: 0 };
    var MONTH_NUMS = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11 };

    function nextWeekday(name, next) {
        var target = WEEKS[name.replace(/day$/, "").slice(0, 3)];
        var offset = (target - today().getDay() + 7) % 7;
        var d = addDays(today(), offset);
        if (next) {
            d = (offset === 0) ? addDays(d, 7) : addDays(d, 0);
        }
        return d;
    }

    function smartParse() {
        var raw = title.value;
        if (!raw.trim()) return false;

        var appliedAny = false;
        var work = raw;

        // 1. Tags: every #name (or #name.name) becomes a tag chip.
        var tagRe = /#([\w][\w.-]*)/g;
        var m;
        var firstTagIdx = -1;
        while ((m = tagRe.exec(raw))) {
            if (firstTagIdx === -1) firstTagIdx = m.index;
            addTag(m[1], true);
            appliedAny = appliedAny || true;
        }
        work = work.replace(/#[\w][\w.-]*/g, " ");
        tagRe.lastIndex = 0;

        // 2. Priority: "high/low/medium priority" phrases only.
        var prioRe = /\b(high|low|medium)\s+priority\b/i;
        var pm = raw.match(prioRe);
        if (pm && !userPickedPriority) {
            var priorPrio = priorityValue.value;
            setPriority(pm[1].toLowerCase());
            work = work.replace(prioRe, " ");
            addParseChip("prio", pm[1].toLowerCase() + " priority", function () {
                setPriority(priorPrio);
            });
            appliedAny = true;
        }

        // 3. Time: "5pm", "5:30pm", "17:30".
        var t12 = /\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b/i;
        var t24 = /\b(\d{1,2}):(\d{2})\b/;
        var m12 = !userPickedTime && !timeInput.value ? work.match(t12) : null;
        var m24 = !m12 && !userPickedTime && !timeInput.value ? work.match(t24) : null;
        if ((m12 || m24) && !userPickedDate) {
            var hh, mm;
            if (m12) {
                var h12 = parseInt(m12[1], 10);
                var isPM = /pm$/i.test(m12[3]);
                hh = (h12 % 12) + (isPM ? 12 : 0);
                mm = parseInt(m12[2] || "0", 10);
            } else {
                hh = parseInt(m24[1], 10);
                mm = parseInt(m24[2], 10);
            }
            var hhmm = pad(hh) + ":" + pad(mm);
            var priorDate = dateInput.value;
            var priorTime = timeInput.value;
            setTime(hhmm);
            if (!dateInput.value) setDate(today());
            addParseChip("time", timeLabel(hhmm), function () {
                setTime(priorTime);
                setDate(priorDate ? parseISO(priorDate) : null);
            });
            appliedAny = true;
        }

        // 4. Dates: words first, then month-name, then ISO.
        if (!dateInput.value && !userPickedDate) {
            var priorDate = dateInput.value;
            var dateMatch = null;

            var word = work.match(/\b(today|tomorrow|tonight)\b/i);
            if (word) {
                var d = /\btomorrow\b/i.test(word[0]) ? addDays(today(), 1) : today();
                dateMatch = d;
            }
            if (!dateMatch) {
                var nw = work.match(/\bnext\s+week\b/i);
                if (nw) dateMatch = addDays(today(), 7);
            }
            if (!dateMatch) {
                var wd = work.match(/\b(next\s+)?(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b/i);
                if (wd) dateMatch = nextWeekday(wd[2].toLowerCase(), /\bnext\b/i.test(wd[1] || ""));
            }
            if (!dateMatch) {
                var md = work.match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b/i) ||
                          work.match(/\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\b/i);
                if (md) {
                    var monthPart, dayPart;
                    if (/^[a-z]/.test(md[1])) { monthPart = md[1]; dayPart = md[2]; }
                    else { monthPart = md[2]; dayPart = md[1]; }
                    var mIdx = MONTH_NUMS[monthPart.toLowerCase().slice(0, 3)];
                    var day = parseInt(dayPart, 10);
                    var candidate = new Date(today().getFullYear(), mIdx, day);
                    if (candidate < today()) candidate = new Date(today().getFullYear() + 1, mIdx, day);
                    dateMatch = candidate;
                }
            }
            if (!dateMatch) {
                var isoM = work.match(/\b(20\d{2})-(\d{1,2})-(\d{1,2})\b/);
                if (isoM) {
                    var c2 = new Date(parseInt(isoM[1], 10), parseInt(isoM[2], 10) - 1, parseInt(isoM[3], 10));
                    if (!isNaN(c2.getTime())) dateMatch = c2;
                }
            }

            if (dateMatch) {
                setDate(dateMatch);
                addParseChip("date", dateLabel(dateMatch), function () {
                    setDate(parseISO(priorDate));
                });
                appliedAny = true;
            }
        }

        if (appliedAny) {
            parseChips.classList.remove("hidden");
            return true;
        }
        return false;
    }

    // ---- Open / close ---------------------------------------------------------

    function resetEditor() {
        form.reset();
        if (errorBox) errorBox.classList.add("hidden");
        if (parseChips) parseChips.classList.add("hidden");
        if (tagsChips) tagsChips.classList.add("hidden");
        title.value = "";
        setPriority("medium");
        setDate(null);
        setTime(null);
        if (projectInput) projectInput.value = "";
        if (projectValue) projectValue.value = "";
        if (moreToggle) moreToggle.setAttribute("aria-expanded", "false");
        if (moreBody) moreBody.classList.add("hidden");
        userPickedDate = userPickedTime = userPickedPriority = false;
        if (eyebrow) {
            eyebrow.setAttribute("data-editor-context", "");
            eyebrow.lastElementChild.textContent = "Quick add";
        }
    }

    function prefillFromOpener(btn) {
        if (!btn) return;
        var due = btn.getAttribute("data-quick-add-due");
        var project = btn.getAttribute("data-quick-add-project");
        var label = "Quick add";
        if (due === "today") {
            setDate(today(), true);
            label = "Quick add · My Day";
        }
        if (project) {
            var opt = projectValue.querySelector('option[value="' + project + '"]');
            if (opt) {
                projectValue.value = project;
                projectInput.value = opt.textContent;
                label = "Quick add · " + opt.textContent;
            }
        }
        if (eyebrow) {
            eyebrow.setAttribute("data-editor-context", label !== "Quick add" ? "context" : "");
            eyebrow.lastElementChild.textContent = label;
        }
    }

    function open(opener) {
        if (dialog.open) {
            var already = title;
            if (already) already.focus();
            return;
        }
        resetEditor();
        prefillFromOpener(opener);
        dialog.showModal();
        window.setTimeout(function () { title.focus(); }, 40);
    }

    function close() {
        if (!dialog.open) return;
        if (pendingNav) { window.clearTimeout(pendingNav); pendingNav = null; }
        dialog.close();
    }

    dialog.addEventListener("close", resetEditor);

    TM.openQuickAdd = open;
    TM.closeQuickAdd = close;

    // ---- Global openers / closers --------------------------------------------

    document.addEventListener("click", function (ev) {
        var opener = ev.target.closest(".js-quick-add-open");
        if (opener) {
            ev.preventDefault();
            open(opener);
            return;
        }
        if (ev.target.closest("[data-close-quick-add]") || ev.target === dialog) {
            ev.preventDefault();
            close();
        }
    });

    // ---- Control wiring --------------------------------------------------------

    priorityBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            setPriority(btn.getAttribute("data-priority"), true);
        });
    });

    dueBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            var key = btn.getAttribute("data-due-quick");
            if (key === "none") setDate(null, true);
            if (key === "today") setDate(today(), true);
            if (key === "tomorrow") setDate(addDays(today(), 1), true);
        });
    });

    dateInput.addEventListener("change", function () {
        userPickedDate = true;
        dateInput.classList.toggle("is-set", !!dateInput.value);
        syncDueSegments();
    });
    timeInput.addEventListener("change", function () {
        userPickedTime = true;
        timeInput.classList.toggle("is-set", !!timeInput.value);
    });

    // Project: keep the hidden select in sync with the text input.
    function syncProject() {
        var name = projectInput.value.trim();
        if (!name) { projectValue.value = ""; return; }
        var match = null;
        projectValue.querySelectorAll("option").forEach(function (opt) {
            if (opt.textContent.toLowerCase() === name.toLowerCase()) match = opt;
        });
        projectValue.value = match ? match.value : "";
    }
    projectInput.addEventListener("change", syncProject);
    projectInput.addEventListener("blur", syncProject);
    projectInput.addEventListener("input", function () {
        projectInput.dataset.userTyping = "1";
    });

    // Tags: Enter appends a chip.
    tagsInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            addTag(tagsInput.value);
        }
    });
    tagsInput.addEventListener("blur", function () {
        if (tagsInput.value.trim()) addTag(tagsInput.value);
    });

    if (moreToggle && moreBody) {
        moreToggle.addEventListener("click", function () {
            var openNow = moreBody.classList.toggle("hidden");
            moreToggle.setAttribute("aria-expanded", openNow ? "false" : "true");
        });
    }

    // ---- Submission ------------------------------------------------------------

    function showError(msg) {
        if (!errorBox) return;
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

    form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var trimmed = (title.value || "").trim();
        if (!trimmed) {
            showError("Give the task a title.");
            title.focus();
            return;
        }
        showError("");

        submitBtn.disabled = true;
        var submitLabel = submitBtn.querySelector("span") || submitBtn;
        var submitText = submitLabel.textContent;
        submitLabel.textContent = "Creating…";

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
                    close();
                    TM.toast('Task "' + data.task.title + '" created.', "success");
                }
            })
            .catch(function (err) {
                var payload = err && err.errors ? JSON.parse(err.errors) : null;
                var first = payload && payload.title && payload.title[0] && payload.title[0].message;
                showError(first || (payload && payload.__all__ && payload.__all__[0] && payload.__all__[0].message) || null);
                if (!first) TM.toast("Couldn't create the task.", "error");
            })
            .finally(function () {
                submitBtn.disabled = false;
                submitLabel.textContent = submitText;
            });
    });

    // Enter in the title smart-parses; hold again (or nothing todo) submits.
    title.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
            if (ev.metaKey || ev.ctrlKey) return; // handled by form submit below? not needed
            ev.preventDefault();
            var parsed = smartParse();
            if (!parsed) {
                if (form.requestSubmit) form.requestSubmit();
                else form.submit();
            }
        }
    });

    // Ctrl/Cmd+Enter anywhere submits.
    form.addEventListener("keydown", function (ev) {
        if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") {
            ev.preventDefault();
            if (form.requestSubmit) form.requestSubmit();
            else form.submit();
        }
    });
})();