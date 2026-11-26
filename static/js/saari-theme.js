(() => {
    "use strict";

    const root = document.documentElement;
    const key = "saari-theme";
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    const choices = document.querySelectorAll("[data-saari-theme-picker]");
    const meta = document.querySelector('meta[name="theme-color"]');

    function apply(preference) {
        if (!["light", "dark", "auto"].includes(preference)) preference = "auto";
        const theme = preference === "auto" ? (system.matches ? "dark" : "light") : preference;
        const changed = root.dataset.theme !== theme;
        root.dataset.themePreference = preference;
        root.dataset.theme = root.dataset.bsTheme = theme;
        if (meta) meta.content = theme === "dark" ? "#1b1917" : "#453330";
        choices.forEach(choice => { choice.value = preference; });
        if (changed) document.dispatchEvent(new CustomEvent("saari:themechange", { detail: { theme, preference } }));
    }

    apply(root.dataset.themePreference);
    choices.forEach(choice => choice.addEventListener("change", () => {
        try { localStorage.setItem(key, choice.value); } catch (_) {}
        apply(choice.value);
    }));
    system.addEventListener("change", () => {
        if (root.dataset.themePreference === "auto") apply("auto");
    });
    window.addEventListener("storage", event => {
        if (event.key === key || event.key === null) apply(event.newValue);
    });
    window.addEventListener("pageshow", event => {
        if (!event.persisted) return;
        try { apply(localStorage.getItem(key) || root.dataset.themePreference); } catch (_) {}
    });
})();
