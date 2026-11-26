(() => {
    "use strict";

    const doc = document;
    const nativeDownloadAction = doc.currentScript?.dataset.nativeDownloadAction;
    const body = doc.body;
    const root = doc.documentElement;
    const desktopBreakpoint = 1024;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");

    const qs = (selector, scope = doc) => scope.querySelector(selector);
    const qsa = (selector, scope = doc) => Array.from(scope.querySelectorAll(selector));
    const isDesktop = () => window.innerWidth > desktopBreakpoint;

    const safeStorage = {
        get(key) {
            try { return window.localStorage.getItem(key); } catch (_) { return null; }
        },
        set(key, value) {
            try { window.localStorage.setItem(key, value); } catch (_) {}
        }
    };

    function rafThrottle(callback) {
        let queued = false;
        return (...args) => {
            if (queued) return;
            queued = true;
            window.requestAnimationFrame(() => {
                queued = false;
                callback(...args);
            });
        };
    }

    function initSidebar() {
        const sidebar = qs("[data-sidebar]") || qs("#appSidebar");
        const toggle = qs("[data-sidebar-toggle]");
        const mobileClose = qs("[data-sidebar-mobile-close]");
        const backdrop = qs("[data-sidebar-backdrop]");
        const content = qs(".app-content");
        if (!sidebar || !toggle) return;
        const sidebarKey = `saari-nav:${body.dataset.navAccount || "local"}:sidebar`;
        let desktopCollapsed = safeStorage.get(sidebarKey) === "true";

        const syncSidebarState = () => {
            const desktop = isDesktop();
            if (desktop) body.classList.remove("sidebar-mobile-open");
            const mobileOpen = body.classList.contains("sidebar-mobile-open");
            const collapsed = desktop && desktopCollapsed;
            body.classList.toggle("sidebar-collapsed", collapsed);
            body.classList.toggle("sidebar-is-collapsed", collapsed);
            sidebar.inert = !desktop && !mobileOpen;
            if (content) content.inert = mobileOpen;
            toggle.setAttribute("aria-expanded", String(desktop ? !collapsed : mobileOpen));
        };

        function closeMobile(restoreFocus = false) {
            if (!body.classList.contains("sidebar-mobile-open")) return;
            body.classList.remove("sidebar-mobile-open");
            syncSidebarState();
            if (restoreFocus) toggle.focus({ preventScroll: true });
        }

        syncSidebarState();
        toggle.addEventListener("click", () => {
            if (isDesktop()) {
                desktopCollapsed = !desktopCollapsed;
                safeStorage.set(sidebarKey, String(desktopCollapsed));
                syncSidebarState();
                return;
            }
            body.classList.add("sidebar-mobile-open");
            syncSidebarState();
            mobileClose?.focus({ preventScroll: true });
        });

        mobileClose?.addEventListener("click", () => closeMobile(true));
        backdrop?.addEventListener("click", () => closeMobile(true));
        window.addEventListener("resize", rafThrottle(syncSidebarState), { passive: true });
        window.addEventListener("pagehide", () => closeMobile());
        window.addEventListener("pageshow", syncSidebarState);

        doc.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && !event.defaultPrevented) closeMobile(true);
        });
    }

    function initPressFeedback() {
        if (reduceMotion.matches) return;

        const selector = "button, .pc-btn, .sidebar-link, .sidebar-sublink, .module-card:not(.module-card--disabled), [data-ui-press]";
        doc.addEventListener("pointerdown", event => {
            if (event.pointerType === "mouse" && event.button !== 0) return;
            const target = event.target.closest(selector);
            if (!target || target.matches("input, select, textarea")) return;

            const rect = target.getBoundingClientRect();
            const wave = doc.createElement("span");
            wave.className = "ui-press-wave";
            wave.style.setProperty("--press-x", `${event.clientX - rect.left}px`);
            wave.style.setProperty("--press-y", `${event.clientY - rect.top}px`);
            if (window.getComputedStyle(target).position === "static") {
                target.classList.add("ui-wave-host");
            }
            target.appendChild(wave);
            wave.addEventListener("animationend", () => {
                wave.remove();
                if (!qs(".ui-press-wave", target)) target.classList.remove("ui-wave-host");
            }, { once: true });
        }, { passive: true });
    }

    function initReveal() {
        if (reduceMotion.matches || !("IntersectionObserver" in window)) return;

        const selectors = [
            ".dashboard-heading",
            ".modules__header",
            ".module-card"
        ].join(",");

        const items = qsa(selectors).filter(el => !el.closest("[hidden]"));
        items.forEach((el, index) => {
            el.dataset.uiReveal = "";
            el.style.setProperty("--ui-delay", `${Math.min(index % 8, 7) * 34}ms`);
        });

        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-ui-visible");
                observer.unobserve(entry.target);
            });
        }, { threshold: .08, rootMargin: "0px 0px -28px 0px" });

        items.forEach(el => observer.observe(el));
    }

    function initCardSpotlight() {
        if (!finePointer.matches || reduceMotion.matches) return;

        qsa(".module-card:not(.module-card--disabled)").forEach(card => {
            card.addEventListener("pointermove", rafThrottle(event => {
                const rect = card.getBoundingClientRect();
                const x = ((event.clientX - rect.left) / rect.width) * 100;
                const y = ((event.clientY - rect.top) / rect.height) * 100;
                card.style.setProperty("--mx", `${x}%`);
                card.style.setProperty("--my", `${y}%`);
            }), { passive: true });
        });
    }

    function initPasswordToggle() {
        const toggle = qs("[data-password-toggle]");
        const input = qs("[data-password-input]");
        if (!toggle || !input) return;

        toggle.addEventListener("click", () => {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            toggle.classList.toggle("is-visible", show);
            toggle.setAttribute("aria-label", show ? "Ocultar senha" : "Exibir senha");
        });
    }

    function initSubmittingStates() {
        const active = new Map();

        function resetButton(submit) {
            window.clearTimeout(active.get(submit));
            active.delete(submit);
            submit.classList.remove("is-submitting", "is-loading");
            submit.removeAttribute("aria-busy");
        }

        function reset() {
            for (const submit of active.keys()) resetButton(submit);
        }

        doc.addEventListener("submit", event => {
            const form = event.target;
            const submit = event.submitter || qs("[data-login-submit]", form);
            if (!submit || submit.matches("[data-no-loading], [data-download]")) return;
            if (form.matches("[data-no-loading], [data-download]")) return;

            const method = (submit.getAttribute("formmethod") ?? form.method).toLowerCase();
            const target = submit.getAttribute("formtarget") ?? form.target;
            const localFilter = method === "get" && form.matches("[data-local-submit-loading]");
            if ((method !== "post" && !localFilter) || (target && target.toLowerCase() !== "_self")) return;

            const action = submit.hasAttribute("formaction") ? submit.formAction : form.action;
            // O POST de emissão redireciona para o arquivo ou para a página com mensagens.
            if (nativeDownloadAction && new URL(action, doc.baseURI).pathname === nativeDownloadAction) return;

            queueMicrotask(() => {
                if (event.defaultPrevented) return;
                window.clearTimeout(active.get(submit));
                // Cancelamentos nativos sem pagehide podem deixar o documento aberto.
                const timeout = window.setTimeout(() => resetButton(submit), localFilter ? 4000 : 12000);
                active.set(submit, timeout);
                submit.classList.add("is-submitting");
                submit.setAttribute("aria-busy", "true");
                if (submit.matches("[data-login-submit]")) submit.classList.add("is-loading");
            });
        });

        doc.addEventListener("keydown", event => {
            if (event.key === "Escape" && !event.defaultPrevented) reset();
        });
        window.addEventListener("pagehide", reset);
        window.addEventListener("pageshow", reset);
    }

    function dismissMessage(message) {
        if (!message || message.classList.contains("is-leaving")) return;
        const h = message.getBoundingClientRect().height;
        message.style.maxHeight = `${h}px`;
        // força layout para permitir a transição de max-height
        void message.offsetHeight;
        message.classList.add("is-leaving");
        window.setTimeout(() => message.remove(), reduceMotion.matches ? 20 : 290);
    }

    function initMessages() {
        doc.addEventListener("click", event => {
            const button = event.target.closest("[data-message-close]");
            if (!button) return;
            dismissMessage(button.closest(".message"));
        });
    }

    function initKeyboardModality() {
        const markKeyboard = event => {
            if (event.key === "Tab") {
                root.classList.add("using-keyboard");
                doc.removeEventListener("keydown", markKeyboard);
            }
        };
        doc.addEventListener("keydown", markKeyboard);
        doc.addEventListener("pointerdown", () => root.classList.remove("using-keyboard"), { passive: true });
    }

    function init() {
        body.classList.add("ui-enhanced");
        initSidebar();
        initPressFeedback();
        initReveal();
        initCardSpotlight();
        initPasswordToggle();
        initSubmittingStates();
        initMessages();
        initKeyboardModality();
    }

    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", init, { once: true });
    else init();
})();
