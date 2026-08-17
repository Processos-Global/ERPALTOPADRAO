(() => {
    "use strict";

    const doc = document;
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
        if (event.defaultPrevented || event.button > 0) return false;
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return false;
        if (link.target === "_blank" || link.hasAttribute("download")) return false;
        if (!link.href || link.href.startsWith("javascript:")) return false;

        let current;
        let destination;
        try {
            current = new URL(window.location.href);
            destination = new URL(link.href, window.location.origin);
        } catch (_) { return false; }

        if (destination.origin !== current.origin) return false;
        if (destination.href === current.href) return false;
        if (destination.pathname === current.pathname && destination.search === current.search && destination.hash) return false;
        return true;
    }

    function initPageTransitions() {
        const transitionLayer = qs(".page-transition");
        const transitionMark = qs(".page-transition__mark");
        let navigating = false;
        let activeAnimation = null;

        const resetTransition = () => {
            navigating = false;
            body.classList.remove("is-transitioning");

            if (activeAnimation) {
                try { activeAnimation.cancel(); } catch (_) {}
                activeAnimation = null;
            }

            if (transitionLayer) {
                transitionLayer.getAnimations().forEach(animation => animation.cancel());
                transitionLayer.style.transition = "none";
                transitionLayer.style.transform = "translate3d(0, 104%, 0)";
                transitionLayer.style.pointerEvents = "none";
            }

            if (transitionMark) {
                transitionMark.getAnimations().forEach(animation => animation.cancel());
                transitionMark.style.opacity = "0";
                transitionMark.style.transform = "translateY(20px) scale(.92)";
            }
        };

        // Garante estado limpo inclusive ao voltar pelo histórico/BFCache.
        resetTransition();

        doc.addEventListener("click", event => {
            const link = event.target.closest("a[data-transition-link]");
            if (!link || !isNavigableTransition(event, link) || navigating) return;

            event.preventDefault();
            navigating = true;

            const destination = link.href;
            const go = () => {
                window.location.assign(destination);
            };

            if (!transitionLayer || typeof transitionLayer.animate !== "function") {
                body.classList.add("is-transitioning");
                window.setTimeout(go, 1050);
                return;
            }

            // Cancela qualquer animação/estado herdado da navegação anterior.
            transitionLayer.getAnimations().forEach(animation => animation.cancel());
            transitionLayer.style.transition = "none";
            transitionLayer.style.transform = "translate3d(0, 104%, 0)";
            transitionLayer.style.pointerEvents = "all";

            if (transitionMark) {
                transitionMark.getAnimations().forEach(animation => animation.cancel());
                transitionMark.style.opacity = "0";
                transitionMark.style.transform = "translateY(20px) scale(.92)";
            }

            // Força o browser a registrar 104% como quadro inicial antes de animar.
            void transitionLayer.offsetHeight;
            body.classList.add("is-transitioning");

            activeAnimation = transitionLayer.animate(
                [
                    { transform: "translate3d(0, 104%, 0)" },
                    { transform: "translate3d(0, 0, 0)" }
                ],
                {
                    duration: 1150,
                    easing: "cubic-bezier(.22, .78, .18, 1)",
                    fill: "forwards"
                }
            );

            if (transitionMark) {
                transitionMark.animate(
                    [
                        { opacity: 0, transform: "translateY(20px) scale(.92)" },
                        { opacity: 1, transform: "translateY(0) scale(1)" }
                    ],
                    {
                        duration: 650,
                        delay: 300,
                        easing: "cubic-bezier(.16, 1, .3, 1)",
                        fill: "forwards"
                    }
                );
            }

            let navigated = false;
            const finishNavigation = () => {
                if (navigated) return;
                navigated = true;
                window.setTimeout(go, 260);
            };

            activeAnimation.finished.then(finishNavigation).catch(() => {
                if (navigating) window.setTimeout(go, 1200);
            });

            // Fallback apenas para browsers com comportamento anormal da Web Animations API.
            window.setTimeout(() => {
                if (!navigated && navigating) finishNavigation();
            }, 1450);
        });

        window.addEventListener("pageshow", resetTransition);
        window.addEventListener("pagehide", () => body.classList.remove("sidebar-mobile-open"));
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
        qsa("form").forEach(form => {
            form.addEventListener("submit", () => {
                const submit = qs('button[type="submit"], input[type="submit"], [data-login-submit]', form);
                if (!submit || submit.dataset.noLoading !== undefined) return;

                submit.classList.add("is-submitting");
                if (submit.matches("button")) submit.setAttribute("aria-busy", "true");
            });
        });

        const loginForm = qs("[data-login-form]");
        const loginSubmit = qs("[data-login-submit]");
        loginForm?.addEventListener("submit", () => loginSubmit?.classList.add("is-loading"));
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
