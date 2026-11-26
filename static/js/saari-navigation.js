(() => {
    "use strict";

    const account = document.body.dataset.navAccount;
    const key = name => `saari-nav:${account}:${name}`;
    const read = (name, fallback) => {
        try { return account ? JSON.parse(localStorage.getItem(key(name))) ?? fallback : fallback; }
        catch (_) { return fallback; }
    };
    const save = (name, value) => {
        if (!account) return;
        try { localStorage.setItem(key(name), JSON.stringify(value)); } catch (_) {}
    };

    document.querySelectorAll("[data-nav-submenu]").forEach(toggle => {
        const group = toggle.closest("[data-nav-group]");
        const panel = document.getElementById(toggle.getAttribute("aria-controls"));
        const name = `submenu:${group.dataset.navGroup}`;
        function setExpanded(expanded) {
            group.classList.toggle("is-open", expanded);
            panel.inert = !expanded;
            toggle.setAttribute("aria-expanded", String(expanded));
        }
        setExpanded(group.hasAttribute("data-group-active") || read(name, false) === true);
        toggle.addEventListener("click", () => {
            const expanded = toggle.getAttribute("aria-expanded") !== "true";
            save(name, expanded);
            setExpanded(expanded);
        });
    });

    const nav = document.querySelector(".saari-sidebar-nav");
    if (nav) {
        const tooltip = document.createElement("span");
        tooltip.className = "saari-compact-tooltip";
        tooltip.hidden = true;
        tooltip.setAttribute("aria-hidden", "true");
        document.body.append(tooltip);
        function showTooltip(event) {
            if (!document.body.classList.contains("sidebar-is-collapsed")) return;
            const bounds = event.currentTarget.getBoundingClientRect();
            tooltip.textContent = event.currentTarget.getAttribute("aria-label");
            tooltip.style.left = `${bounds.right + 13}px`;
            tooltip.style.top = `${bounds.top + 4}px`;
            tooltip.hidden = false;
        }
        const hideTooltip = () => { tooltip.hidden = true; };
        nav.querySelectorAll(".sidebar-link").forEach(link => {
            link.addEventListener("mouseenter", showTooltip);
            link.addEventListener("focus", showTooltip);
            link.addEventListener("mouseleave", hideTooltip);
            link.addEventListener("blur", hideTooltip);
        });
        nav.addEventListener("scroll", hideTooltip, { passive: true });
        window.addEventListener("resize", hideTooltip);
    }

    const notification = document.querySelector("[data-notification-center]");
    const notificationToggle = notification?.querySelector("[data-notification-toggle]");
    const notificationPanel = notification?.querySelector("[data-notification-panel]");
    const profile = document.querySelector(".saari-profile");
    const logout = document.querySelector("[data-logout-dialog]");
    const logoutForm = document.querySelector("[data-logout-form]");

    function setNotifications(open, restore = false) {
        if (!notificationToggle || !notificationPanel) return;
        notificationToggle.setAttribute("aria-expanded", String(open));
        notificationPanel.hidden = !open;
        if (restore) notificationToggle.focus();
    }

    notificationToggle?.addEventListener("click", () => {
        setNotifications(notificationPanel.hidden);
    });
    document.addEventListener("click", event => {
        if (logout?.contains(event.target)) return;
        if (!notification?.contains(event.target)) setNotifications(false);
        if (profile?.open && !profile.contains(event.target)) profile.open = false;
    });
    document.addEventListener("keydown", event => {
        if (event.key !== "Escape") return;
        if (notificationPanel && !notificationPanel.hidden) {
            setNotifications(false, notification.contains(document.activeElement));
        }
        if (profile?.open && profile.contains(document.activeElement)) {
            profile.open = false;
            profile.querySelector("summary").focus();
        }
    });
    logoutForm?.addEventListener("submit", event => {
        if (!logout?.showModal) return;
        event.preventDefault();
        logout.showModal();
    });
    logout?.querySelector("[data-logout-cancel]")?.addEventListener("click", () => logout.close());
    logout?.querySelector("[data-logout-confirm]")?.addEventListener("click", () => logoutForm.submit());

    const dialog = document.querySelector("[data-command-dialog]");
    const trigger = document.querySelector("[data-command-open]");
    if (!nav || !dialog?.showModal || !trigger) return;

    const input = dialog.querySelector("input");
    const results = dialog.querySelector("[data-command-results]");
    const status = dialog.querySelector("[data-command-status]");
    const normalize = value => value.normalize("NFD").replace(/\p{Mark}/gu, "").toLocaleLowerCase("pt-BR");
    const routes = Array.from(nav.querySelectorAll("[data-nav-link]"), link => {
        const label = link.dataset.searchLabel || link.getAttribute("aria-label");
        const group = link.closest("[data-nav-group]")?.dataset.groupLabel || "Geral";
        return {
            id: link.dataset.navLink, href: link.href, label, group,
            terms: normalize(`${label} ${group} ${link.dataset.searchTerms || ""}`),
            current: link.getAttribute("aria-current") === "page",
        };
    });
    const index = new Map(routes.map(route => [route.id, route]));
    function storedIds(name) {
        const stored = read(name, []);
        return Array.isArray(stored) ? [...new Set(stored)].filter(id => index.has(id)) : [];
    }
    let favorites = storedIds("favorites");
    let recent = storedIds("recent");
    const current = routes.find(route => route.current && route.id !== "core:index");
    if (current) {
        recent = [current.id, ...recent.filter(id => id !== current.id)].slice(0, 6);
        save("recent", recent);
    }

    function routeLink(route) {
        const link = document.createElement("a");
        link.href = route.href;
        link.textContent = route.label;
        link.dataset.commandLink = route.id;
        return link;
    }

    function routeRow(route, update) {
        const row = document.createElement("li");
        row.className = "saari-route-row";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "saari-icon-button";
        button.dataset.favorite = route.id;
        button.setAttribute("aria-label", `Favorito: ${route.label}`);
        button.setAttribute("aria-pressed", String(favorites.includes(route.id)));
        const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        icon.setAttribute("class", "icon");
        icon.setAttribute("aria-hidden", "true");
        const use = document.createElementNS(icon.namespaceURI, "use");
        use.setAttribute("href", "#icon-star");
        icon.append(use);
        button.append(icon);
        button.addEventListener("click", () => {
            favorites = favorites.includes(route.id)
                ? favorites.filter(id => id !== route.id)
                : [...favorites, route.id];
            save("favorites", favorites);
            update();
        });
        row.append(routeLink(route), button);
        return row;
    }

    function renderQuick() {
        const section = document.querySelector("[data-erp-quick]");
        if (!section) return;
        for (const [name, ids] of [["favorites", favorites], ["recent", recent]]) {
            const list = section.querySelector(`[data-quick-${name}]`);
            list.replaceChildren(...ids.map(id => routeRow(index.get(id), () => {
                renderQuick();
                const next = Array.from(list.querySelectorAll("[data-favorite]")).find(el => el.dataset.favorite === id);
                (next || list.querySelector("a") || trigger).focus();
            })));
            list.parentElement.hidden = ids.length === 0;
        }
        section.hidden = favorites.length === 0 && recent.length === 0;
    }
    renderQuick();

    function renderResults() {
        const terms = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
        const filtered = routes.filter(route => terms.every(term => route.terms.includes(term)));
        const grouped = new Map();
        if (!terms.length) {
            if (favorites.length) grouped.set("Favoritos", favorites.map(id => index.get(id)));
            if (recent.length) grouped.set("Recentes", recent.filter(id => !favorites.includes(id)).map(id => index.get(id)));
        }
        const quick = terms.length ? [] : [...favorites, ...recent];
        for (const route of filtered) {
            if (quick.includes(route.id)) continue;
            if (!grouped.has(route.group)) grouped.set(route.group, []);
            grouped.get(route.group).push(route);
        }
        results.replaceChildren();
        for (const [group, entries] of grouped) {
            if (!entries.length) continue;
            const heading = document.createElement("h2");
            heading.textContent = group;
            const list = document.createElement("ul");
            list.append(...entries.map(route => routeRow(route, () => {
                renderResults();
                renderQuick();
                const next = Array.from(results.querySelectorAll("[data-favorite]")).find(el => el.dataset.favorite === route.id);
                (next || input).focus();
            })));
            results.append(heading, list);
        }
        if (!filtered.length) {
            const empty = document.createElement("p");
            empty.className = "saari-command__empty";
            empty.textContent = "Nenhuma funcionalidade encontrada.";
            results.append(empty);
        }
        status.textContent = filtered.length === 1 ? "1 funcionalidade" : `${filtered.length} funcionalidades`;
    }

    let origin;
    function open() {
        if (dialog.open || logout?.open) return;
        origin = document.activeElement;
        input.value = "";
        renderResults();
        dialog.showModal();
        input.focus();
    }

    trigger.addEventListener("click", open);
    input.addEventListener("input", renderResults);
    dialog.querySelector("[data-command-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => (origin instanceof HTMLElement ? origin : trigger).focus());
    document.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
            event.preventDefault();
            open();
        }
    });
    dialog.addEventListener("keydown", event => {
        const links = Array.from(results.querySelectorAll("[data-command-link]"));
        if (!links.length) return;
        if (event.key === "Enter" && event.target === input) {
            event.preventDefault();
            links[0].click();
        } else if (["ArrowDown", "ArrowUp"].includes(event.key)) {
            event.preventDefault();
            const current = links.indexOf(event.target.closest(".saari-route-row")?.querySelector("a"));
            if (event.key === "ArrowUp" && current === 0) input.focus();
            else links[current < 0 && event.key === "ArrowUp" ? links.length - 1
                : Math.min(links.length - 1, current + (event.key === "ArrowDown" ? 1 : -1))]?.focus();
        }
    });
})();
