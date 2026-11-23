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
        let resizeTimer = null;

        const closeMobile = () => body.classList.remove("sidebar-mobile-open");

        const syncSidebarState = () => {
            if (!isDesktop()) {
                body.classList.remove("sidebar-collapsed");
                body.classList.remove("sidebar-is-collapsed");
                return;
            }

            const collapsed = safeStorage.get("erpSidebarCollapsed") === "true";
            body.classList.toggle("sidebar-collapsed", collapsed);
            body.classList.toggle("sidebar-is-collapsed", collapsed);
        };

        syncSidebarState();

        toggle?.addEventListener("click", () => {
            body.classList.add("is-resizing-sidebar");
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(() => body.classList.remove("is-resizing-sidebar"), 360);

            if (isDesktop()) {
                const next = !body.classList.contains("sidebar-collapsed");
                body.classList.toggle("sidebar-collapsed", next);
                body.classList.toggle("sidebar-is-collapsed", next);
                safeStorage.set("erpSidebarCollapsed", String(next));
            } else {
                body.classList.toggle("sidebar-mobile-open");
            }
        });

        mobileClose?.addEventListener("click", closeMobile);
        backdrop?.addEventListener("click", closeMobile);

        window.addEventListener("resize", rafThrottle(() => {
            if (isDesktop()) closeMobile();
            syncSidebarState();
        }), { passive: true });

        doc.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeMobile();
        });

        // Mantém compatibilidade com CSS/template que inferem o estado pela largura.
        if (sidebar && "ResizeObserver" in window) {
            const observer = new ResizeObserver(entries => {
                const width = entries[0]?.contentRect?.width || 0;
                if (isDesktop() && width) body.classList.toggle("sidebar-is-collapsed", width <= 120);
            });
            observer.observe(sidebar);
        }
    }

    function isNavigableTransition(event, link) {
        if (event.defaultPrevented || event.button !== 0) return false;
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return false;
        if (link.target && link.target.toLowerCase() !== "_self") return false;
        if (link.matches("[download], [data-download]")) return false;

        const current = new URL(window.location.href);
        let destination;
        try {
            destination = new URL(link.href, current);
        } catch (_) {
            return false;
        }
        if (destination.origin !== current.origin || !["http:", "https:"].includes(destination.protocol)) {
            return false;
        }
        return destination.pathname !== current.pathname || destination.search !== current.search;
    }

    function initPageTransitions() {
        const layer = qs("[data-page-transition]");
        const mark = layer && qs(".page-transition__mark", layer);
        let cover = null;
        let logo = null;

        function reset() {
            cover?.cancel();
            logo?.cancel();
            cover = null;
            logo = null;
        }

        doc.addEventListener("click", event => {
            const link = event.target.closest("a[href][data-transition-link]");
            if (!link || !isNavigableTransition(event, link)) return;
            if (reduceMotion.matches || !layer?.animate) return;

            event.preventDefault();
            reset();
            const animation = layer.animate(
                [
                    { transform: "translateY(100%)" },
                    { transform: "translateY(0)" }
                ],
                { duration: 240, easing: "cubic-bezier(.22, .78, .18, 1)", fill: "forwards" }
            );
            cover = animation;
            logo = mark?.animate(
                [{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "translateY(0)" }],
                { duration: 160, delay: 80, fill: "forwards" }
            );
            animation.finished.then(() => {
                if (cover !== animation) return;
                reset();
                window.location.assign(link.href);
            }, () => {});
        });

        window.addEventListener("pageshow", reset);
        window.addEventListener("pagehide", () => {
            reset();
            body.classList.remove("sidebar-mobile-open");
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
            wave.style.left = `${event.clientX - rect.left}px`;
            wave.style.top = `${event.clientY - rect.top}px`;
            target.classList.add("ui-wave-host");
            target.appendChild(wave);
            wave.addEventListener("animationend", () => wave.remove(), { once: true });
        }, { passive: true });
    }

    function initReveal() {
        if (reduceMotion.matches || !("IntersectionObserver" in window)) return;

        const selectors = [
            ".dashboard-heading",
            ".modules__header",
            ".module-card",
            ".pc-card",
            ".pc-filterbar"
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
            input.focus({ preventScroll: true });
            try { input.setSelectionRange(input.value.length, input.value.length); } catch (_) {}
        });
    }

    function initSubmittingStates() {
        const active = new Set();

        function reset() {
            active.forEach(submit => {
                submit.classList.remove("is-submitting", "is-loading");
                submit.removeAttribute("aria-busy");
            });
            active.clear();
        }

        doc.addEventListener("submit", event => {
            const form = event.target;
            const submit = event.submitter || qs("[data-login-submit]", form);
            if (!submit || submit.matches("[data-no-loading], [data-download]")) return;
            if (form.matches("[data-no-loading], [data-download]")) return;

            const method = submit.getAttribute("formmethod") ?? form.method;
            const target = submit.getAttribute("formtarget") ?? form.target;
            if (method.toLowerCase() !== "post" || (target && target.toLowerCase() !== "_self")) return;

            const action = submit.hasAttribute("formaction") ? submit.formAction : form.action;
            // O POST de emissão redireciona para o arquivo ou para a página com mensagens.
            if (nativeDownloadAction && new URL(action, doc.baseURI).pathname === nativeDownloadAction) return;

            queueMicrotask(() => {
                if (event.defaultPrevented) return;
                active.add(submit);
                submit.classList.add("is-submitting");
                if (submit.matches("button")) submit.setAttribute("aria-busy", "true");
                if (submit.matches("[data-login-submit]")) submit.classList.add("is-loading");
            });
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
        initPageTransitions();
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
