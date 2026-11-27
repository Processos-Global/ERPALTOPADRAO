(() => {
    "use strict";
    const workerUrl = document.currentScript?.dataset.workerUrl;
    const wrap = document.querySelector("[data-pwa-install-wrap]");
    const button = document.querySelector("[data-pwa-install]");
    const dialog = document.querySelector("[data-pwa-dialog]");
    const instructions = document.querySelector("[data-pwa-instructions]");
    const standalone = window.matchMedia("(display-mode: standalone)");
    const installed = () => standalone.matches || navigator.standalone === true;
    let promptEvent = null;
    let installedHere = false;
    const update = () => {
        if (wrap) wrap.hidden = !window.isSecureContext || installed() || installedHere;
    };
    window.addEventListener("beforeinstallprompt", event => {
        // Leave browser-native installation UI untouched on pages without our button.
        if (!button) return;
        event.preventDefault();
        promptEvent = event;
        update();
    });
    window.addEventListener("appinstalled", () => {
        installedHere = true;
        promptEvent = null;
        update();
    });
    standalone.addEventListener?.("change", update);
    update();
    if (window.isSecureContext && "serviceWorker" in navigator && workerUrl) {
        navigator.serviceWorker.register(workerUrl, {scope: "/"}).catch(error => {
            console.warn("SAARI PWA: Service Worker nao registrado", error);
        });
    }
    function showInstructions() {
        const appleMobile = /iPad|iPhone|iPod/i.test(navigator.userAgent) ||
            (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
        const message = appleMobile
            ? "No Safari, toque em Compartilhar, escolha Adicionar a Tela de Inicio e confirme a abertura como app, se a opcao aparecer."
            : "Abra o menu do navegador e procure Instalar aplicativo ou Adicionar a tela inicial. Se a opcao nao aparecer, verifique a compatibilidade do navegador.";
        if (dialog?.showModal && instructions) {
            instructions.textContent = message;
            if (!dialog.open) dialog.showModal();
        } else {
            window.alert(message);
        }
    }
    dialog?.querySelector("[data-pwa-close]")?.addEventListener("click", () => dialog.close());
    button?.addEventListener("click", async () => {
        if (!promptEvent) { showInstructions(); return; }
        const event = promptEvent;
        promptEvent = null;
        try {
            await event.prompt();
            const result = await event.userChoice;
            if (result?.outcome === "accepted") { installedHere = true; update(); }
        } catch (_) { showInstructions(); }
    });
})();
