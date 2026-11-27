"use strict";
// Initial version: no Cache Storage, no queued writes and no background sync.
// Only normal same-origin top-level GET navigations get an offline fallback.
self.addEventListener("fetch", event => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== "GET" || request.mode !== "navigate" ||
        request.destination !== "document" || url.origin !== self.location.origin ||
        url.pathname.startsWith("/media/") || url.pathname.startsWith("/static/") ||
        url.pathname.startsWith("/admin/")) return;
    event.respondWith(fetch(request).catch(() => new Response(`<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SAARI ERP - Sem conexao</title></head>
<body style="font:16px system-ui;background:#f5f2ed;color:#453330;padding:2rem;max-width:32rem;margin:auto">
<h1>SAARI ERP</h1><h2>Sem conexao com o servidor</h2><p>Verifique sua internet e tente acessar novamente. Nenhum dado offline foi carregado.</p><p><a href="/">Voltar ao inicio</a></p></body></html>`, {
        status: 503,
        headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}
    })));
});
