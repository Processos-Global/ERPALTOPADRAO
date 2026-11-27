(() => {
    "use strict";
    const favorites = document.querySelector("[data-mobile-favorites]");
    const command = document.querySelector("[data-command-open]");
    const profileButton = document.querySelector("[data-mobile-profile]");
    const profile = document.querySelector(".saari-profile");
    const summary = profile?.querySelector("summary");
    if (favorites && command) {
        favorites.addEventListener("click", () => command.click());
    } else if (favorites) favorites.disabled = true;
    if (profileButton && profile && summary) {
        const sync = () => profileButton.setAttribute("aria-expanded", String(profile.open));
        profile.addEventListener("toggle", sync);
        profileButton.addEventListener("click", event => {
            // Existing document handler closes the profile for outside clicks.
            event.stopPropagation();
            summary.click();
            sync();
            if (profile.open) summary.focus({preventScroll: true});
        });
        sync();
    } else if (profileButton) profileButton.disabled = true;
})();
