document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;

    const sidebarToggle = document.querySelector(
        "[data-sidebar-toggle]"
    );

    const mobileCloseButton = document.querySelector(
        "[data-sidebar-mobile-close]"
    );

    const sidebarBackdrop = document.querySelector(
        "[data-sidebar-backdrop]"
    );

    const transitionLinks = document.querySelectorAll(
        "a[data-transition-link]"
    );

    const passwordToggle = document.querySelector(
        "[data-password-toggle]"
    );

    const passwordInput = document.querySelector(
        "[data-password-input]"
    );

    const loginForm = document.querySelector(
        "[data-login-form]"
    );

    const loginSubmit = document.querySelector(
        "[data-login-submit]"
    );

    const messageCloseButtons = document.querySelectorAll(
        "[data-message-close]"
    );

    const desktopBreakpoint = 1024;

    const isDesktop = () => {
        return window.innerWidth > desktopBreakpoint;
    };

    const closeMobileSidebar = () => {
        body.classList.remove("sidebar-mobile-open");
    };

    const restoreSidebarState = () => {
        if (!isDesktop()) {
            body.classList.remove("sidebar-collapsed");
            return;
        }

        const collapsed = localStorage.getItem(
            "erpSidebarCollapsed"
        );

        body.classList.toggle(
            "sidebar-collapsed",
            collapsed === "true"
        );
    };

    restoreSidebarState();

    sidebarToggle?.addEventListener("click", () => {
        if (isDesktop()) {
            body.classList.toggle("sidebar-collapsed");

            localStorage.setItem(
                "erpSidebarCollapsed",
                body.classList.contains("sidebar-collapsed")
            );

            return;
        }

        body.classList.toggle("sidebar-mobile-open");
    });

    mobileCloseButton?.addEventListener(
        "click",
        closeMobileSidebar
    );

    sidebarBackdrop?.addEventListener(
        "click",
        closeMobileSidebar
    );

    window.addEventListener("resize", () => {
        if (isDesktop()) {
            closeMobileSidebar();
            restoreSidebarState();
        } else {
            body.classList.remove("sidebar-collapsed");
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMobileSidebar();
        }
    });

    transitionLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            if (
                event.ctrlKey ||
                event.metaKey ||
                event.shiftKey ||
                event.altKey ||
                link.target === "_blank"
            ) {
                return;
            }

            const destination = link.href;

            if (!destination) {
                return;
            }

            const currentUrl = new URL(
                window.location.href
            );

            const destinationUrl = new URL(
                destination,
                window.location.origin
            );

            if (
                destinationUrl.origin !== currentUrl.origin ||
                destinationUrl.href === currentUrl.href
            ) {
                return;
            }

            event.preventDefault();

            body.classList.add("is-transitioning");

            window.setTimeout(() => {
                window.location.href = destination;
            }, 580);
        });
    });

    if (passwordToggle && passwordInput) {
        passwordToggle.addEventListener("click", () => {
            const showPassword =
                passwordInput.type === "password";

            passwordInput.type = showPassword
                ? "text"
                : "password";

            passwordToggle.classList.toggle(
                "is-visible",
                showPassword
            );

            passwordToggle.setAttribute(
                "aria-label",
                showPassword
                    ? "Ocultar senha"
                    : "Exibir senha"
            );
        });
    }

    loginForm?.addEventListener("submit", () => {
        loginSubmit?.classList.add("is-loading");
    });

    messageCloseButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const message = button.closest(".message");

            if (!message) {
                return;
            }

            message.style.opacity = "0";
            message.style.transform = "translateY(-8px)";

            window.setTimeout(() => {
                message.remove();
            }, 280);
        });
    });

    window.addEventListener("pageshow", () => {
        body.classList.remove("is-transitioning");
    });
});