(() => {
    const materialSelector = 'select[name="material"], select[name$="-material"]';
    const unavailable = 'Estoque temporariamente indisponível.';
    const batchSize = 200;

    function materialId(status) {
        if (status.dataset.estoqueMaterial) return status.dataset.estoqueMaterial;

        const row = status.closest('[data-estoque-item]');
        if (!row || row.querySelector('input[name$="-DELETE"]:checked')) return '';
        return row.querySelector(materialSelector)?.value || '';
    }

    function stockLabel(balance, valueOnly) {
        if (typeof balance?.saldo !== 'string' || typeof balance.unidade !== 'string') return unavailable;
        const parts = /^(-?\d+)(?:\.(\d+))?$/.exec(balance.saldo);
        if (!parts) return unavailable;

        const [, integer, decimal = ''] = parts;
        // Formata a representação decimal sem converter o saldo para ponto flutuante.
        const digits = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        const number = /[1-9]/.test(decimal) ? `${digits},${decimal.padEnd(4, '0')}` : digits;
        const total = balance.unidade ? `${number} ${balance.unidade}` : number;
        return valueOnly ? total : `Estoque atual da obra: ${total}`;
    }

    function setupStock(root) {
        const workSelect = root.querySelector('select[name="obra"]');
        let timer;
        let controller;

        async function load(obra, targets, signal) {
            const ids = [...targets.keys()];
            for (let start = 0; start < ids.length && !signal.aborted; start += batchSize) {
                const batch = ids.slice(start, start + batchSize);
                const url = new URL(root.dataset.estoqueUrl, window.location.href);
                url.searchParams.set('obra', obra);
                batch.forEach(id => url.searchParams.append('material', id));

                let balances;
                try {
                    const response = await fetch(url, {
                        cache: 'no-store',
                        headers: {Accept: 'application/json'},
                        signal,
                    });
                    if (!response.ok) throw new Error('Consulta de estoque indisponível.');
                    balances = (await response.json()).saldos;
                } catch {
                    // A consulta é independente do preenchimento e envio da compra.
                }

                if (signal.aborted) return;
                for (const id of batch) {
                    for (const status of targets.get(id)) {
                        status.textContent = stockLabel(balances?.[id], status.hasAttribute('data-estoque-apenas-valor'));
                    }
                }
            }
        }

        function schedule() {
            clearTimeout(timer);
            controller?.abort();
            const obra = workSelect?.value || root.dataset.estoqueObra;
            const targets = new Map();

            for (const status of root.querySelectorAll('[data-estoque-saldo]')) {
                const id = materialId(status);
                status.textContent = '';
                if (!id || !obra) continue;
                status.textContent = 'Consultando estoque…';
                if (!targets.has(id)) targets.set(id, []);
                targets.get(id).push(status);
            }

            if (!targets.size) return;
            controller = new AbortController();
            const signal = controller.signal;
            timer = setTimeout(() => load(obra, targets, signal), 180);
        }

        root.addEventListener('change', event => {
            if (event.target === workSelect || event.target.matches(materialSelector)) schedule();
        });
        root.addEventListener('click', event => {
            if (event.target.closest('[data-estoque-atualizar]')) schedule();
        });
        root.addEventListener('compras:itens-alterados', schedule);
        root.addEventListener('toggle', event => {
            if (event.target.open && event.target.hasAttribute('data-estoque-recarregar')) schedule();
        }, true);
        schedule();
    }

    document.querySelectorAll('[data-estoque-url]').forEach(setupStock);
})();
