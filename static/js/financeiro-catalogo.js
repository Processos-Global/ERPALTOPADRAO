(function () {
    'use strict';

    function criarBotao(classe, texto) {
        const botao = document.createElement('button');
        botao.type = 'button';
        botao.className = classe;
        botao.textContent = texto;
        return botao;
    }

    function preparar(select) {
        const endpoint = select.closest('[data-fin-catalogo-url]')?.dataset.finCatalogoUrl;
        if (!endpoint || select.disabled || select.dataset.finCatalogoPronto) return;
        select.dataset.finCatalogoPronto = '1';

        const label = select.labels[0];
        const nome = label?.childNodes && [...label.childNodes]
            .filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join('').trim()
            || select.getAttribute('aria-label') || 'Opções';
        const vazio = select.options[0]?.value === '' ? select.options[0].textContent : 'Selecionar';
        const container = document.createElement('div');
        container.className = 'fin-searchable';
        select.before(container);
        container.append(select);

        const gatilho = criarBotao('fin-control fin-searchable__button', vazio);
        const campoId = select.id || `fin-catalogo-${select.name}`;
        select.id = `${campoId}-nativo`;
        select.tabIndex = -1;
        select.classList.add('fin-searchable__native');
        select.setAttribute('aria-hidden', 'true');
        gatilho.id = campoId;
        if (label) label.htmlFor = campoId;
        gatilho.setAttribute('aria-haspopup', 'dialog');
        gatilho.setAttribute('aria-expanded', 'false');
        gatilho.setAttribute('aria-controls', `${campoId}-opcoes`);
        if (select.getAttribute('aria-describedby')) {
            gatilho.setAttribute('aria-describedby', select.getAttribute('aria-describedby'));
        }
        const rotulo = document.createElement('span');
        const seta = document.createElement('span');
        seta.textContent = '⌄';
        seta.setAttribute('aria-hidden', 'true');
        gatilho.replaceChildren(rotulo, seta);
        container.append(gatilho);

        const selecionados = document.createElement('div');
        selecionados.className = 'fin-combobox__chips';
        if (select.multiple) container.append(selecionados);

        const painel = document.createElement('div');
        painel.id = `${campoId}-opcoes`;
        painel.className = 'fin-searchable__panel';
        painel.hidden = true;
        painel.setAttribute('role', 'dialog');
        painel.setAttribute('aria-label', nome);
        const busca = document.createElement('input');
        busca.type = 'search';
        busca.placeholder = 'Pesquisar';
        busca.setAttribute('aria-label', `Pesquisar ${nome.toLowerCase()}`);
        const status = document.createElement('small');
        status.className = 'fin-help';
        status.setAttribute('role', 'status');
        const opcoes = document.createElement('div');
        opcoes.className = 'fin-searchable__options';
        painel.append(busca, status, opcoes);
        document.body.append(painel);

        let comando;
        let atraso;

        function atualizar() {
            const atuais = [...select.selectedOptions].filter(opcao => opcao.value);
            const texto = select.multiple ? `Selecionar ${nome.toLowerCase()}` : atuais[0]?.textContent || vazio;
            rotulo.textContent = texto;
            gatilho.setAttribute('aria-label', `${nome}. ${texto}`);
            if (!select.multiple) return;
            selecionados.replaceChildren(...atuais.map(opcao => {
                const chip = criarBotao('fin-btn fin-btn--sm', `${opcao.textContent} ×`);
                chip.setAttribute('aria-label', `Remover ${opcao.textContent}`);
                chip.addEventListener('click', () => {
                    opcao.remove();
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    gatilho.focus();
                });
                return chip;
            }));
        }

        function posicionar() {
            if (painel.hidden) return;
            const area = gatilho.getBoundingClientRect();
            if (area.bottom < 0 || area.top > window.innerHeight) return fechar(false);
            const margem = 8;
            const largura = Math.min(Math.max(area.width, 210), window.innerWidth - margem * 2);
            const abaixo = window.innerHeight - area.bottom - margem;
            const acima = area.top - margem;
            const usarAcima = abaixo < 180 && acima > abaixo;
            painel.style.width = `${largura}px`;
            painel.style.minWidth = '0';
            painel.style.maxHeight = `${Math.max(100, Math.min(310, usarAcima ? acima : abaixo))}px`;
            painel.style.left = `${Math.max(margem, Math.min(area.left, window.innerWidth - largura - margem))}px`;
            painel.style.top = usarAcima ? 'auto' : `${area.bottom + 4}px`;
            painel.style.bottom = usarAcima ? `${window.innerHeight - area.top + 4}px` : 'auto';
        }

        function fechar(restaurarFoco) {
            clearTimeout(atraso);
            comando?.abort();
            painel.hidden = true;
            gatilho.setAttribute('aria-expanded', 'false');
            if (restaurarFoco) gatilho.focus();
        }

        function opcaoResultado({ id, texto }) {
            const botao = criarBotao('fin-searchable__option', texto);
            botao.addEventListener('click', () => {
                if (!select.multiple && select.value === String(id)) return fechar(true);
                if (!select.multiple) {
                    [...select.options].filter(opcao => opcao.value).forEach(opcao => opcao.remove());
                }
                const escolha = [...select.options].find(opcao => opcao.value === String(id));
                const opcao = escolha || new Option(texto, id);
                if (!escolha) select.add(opcao);
                opcao.selected = true;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                fechar(true);
            });
            return botao;
        }

        async function consultar() {
            comando?.abort();
            comando = new AbortController();
            const { signal } = comando;
            const url = new URL(endpoint, window.location.href);
            url.searchParams.set('tipo', select.dataset.finCatalogo);
            url.searchParams.set('q', busca.value.trim());
            opcoes.replaceChildren();
            status.textContent = 'Buscando…';
            try {
                const resposta = await fetch(url, { signal, headers: { Accept: 'application/json' } });
                if (!resposta.ok) throw new Error('Falha na consulta');
                const { resultados } = await resposta.json();
                if (signal.aborted || painel.hidden) return;
                const atuais = new Set([...select.selectedOptions].map(opcao => opcao.value));
                const disponiveis = resultados.filter(resultado => !select.multiple || !atuais.has(String(resultado.id)));
                opcoes.replaceChildren(...disponiveis.map(opcaoResultado));
                if (!select.required && !select.multiple && select.value) {
                    const limpar = criarBotao('fin-searchable__option', vazio);
                    limpar.addEventListener('click', () => {
                        select.value = '';
                        select.dispatchEvent(new Event('change', { bubbles: true }));
                        fechar(true);
                    });
                    opcoes.prepend(limpar);
                }
                status.textContent = disponiveis.length ? '' : 'Nenhum resultado';
            } catch (erro) {
                if (!signal.aborted) status.textContent = 'Não foi possível buscar. Tente novamente.';
            }
        }

        gatilho.addEventListener('click', () => {
            if (!painel.hidden) return fechar(false);
            const tema = getComputedStyle(gatilho);
            painel.style.setProperty('--fin-surface', tema.getPropertyValue('--fin-card'));
            painel.style.setProperty('--fin-text', tema.getPropertyValue('--fin-text'));
            painel.hidden = false;
            gatilho.setAttribute('aria-expanded', 'true');
            busca.value = '';
            posicionar();
            busca.focus();
            consultar();
        });
        busca.addEventListener('input', () => {
            clearTimeout(atraso);
            comando?.abort();
            opcoes.replaceChildren();
            atraso = setTimeout(consultar, 200);
        });
        painel.addEventListener('keydown', event => {
            if (event.key === 'Escape') fechar(true);
            if (event.target === busca && (event.key === 'Enter' || event.key === 'ArrowDown')) {
                event.preventDefault();
                const primeira = opcoes.querySelector('button');
                if (event.key === 'Enter') primeira?.click();
                else primeira?.focus();
            }
        });
        document.addEventListener('pointerdown', event => {
            if (!painel.hidden && !painel.contains(event.target) && !gatilho.contains(event.target)) fechar(false);
        });
        document.addEventListener('focusin', event => {
            if (!painel.hidden && !painel.contains(event.target) && !gatilho.contains(event.target)) fechar(false);
        });
        window.addEventListener('resize', posicionar);
        window.addEventListener('scroll', posicionar, true);
        select.addEventListener('change', atualizar);
        select.addEventListener('invalid', () => gatilho.focus());
        atualizar();
    }

    document.querySelectorAll('select[data-fin-catalogo]').forEach(preparar);
})();
