(() => {
    'use strict';

    const seletor = '.fin-page select, select[data-searchable], select[data-force-search]';
    const preparados = new WeakSet();
    let sequencia = 0;
    let aberto = null;

    function criar(tag, classe) {
        const elemento = document.createElement(tag);
        elemento.className = classe;
        return elemento;
    }

    const painel = criar('div', 'fin-searchable__panel');
    painel.id = 'saari-opcoes-select';
    painel.hidden = true;
    painel.setAttribute('role', 'dialog');

    const busca = document.createElement('input');
    busca.type = 'search';
    busca.placeholder = 'Pesquisar opções';
    busca.setAttribute('role', 'combobox');
    busca.setAttribute('aria-autocomplete', 'list');
    busca.setAttribute('aria-expanded', 'false');
    busca.setAttribute('aria-controls', 'saari-lista-select');

    const lista = criar('div', 'fin-searchable__options');
    lista.id = 'saari-lista-select';
    lista.setAttribute('role', 'listbox');
    const status = criar('small', 'fin-searchable__status');
    status.setAttribute('role', 'status');
    painel.append(busca, lista, status);

    function normalizar(texto) {
        return texto.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
    }

    function posicionar() {
        if (!aberto) return;
        const retangulo = aberto.botao.getBoundingClientRect();
        const margem = 8;
        const topo = window.visualViewport?.offsetTop ?? 0;
        const fim = topo + (window.visualViewport?.height ?? window.innerHeight);
        if (retangulo.bottom < topo || retangulo.top > fim || !aberto.botao.getClientRects().length) {
            fechar();
            return;
        }
        const largura = Math.min(Math.max(220, retangulo.width), window.innerWidth - 2 * margem);
        const abaixo = fim - retangulo.bottom - margem;
        const acima = retangulo.top - topo - margem;
        const usarAcima = abaixo < 180 && acima > abaixo;
        painel.style.width = `${largura}px`;
        painel.style.maxHeight = `${Math.max(100, Math.min(310, usarAcima ? acima : abaixo))}px`;
        painel.style.left = `${Math.max(margem, Math.min(retangulo.left, window.innerWidth - largura - margem))}px`;
        painel.style.top = usarAcima ? 'auto' : `${retangulo.bottom + 4}px`;
        painel.style.bottom = usarAcima ? `${window.innerHeight - retangulo.top + 4}px` : 'auto';
    }

    function fechar(restaurarFoco = false) {
        if (!aberto) return;
        const { botao } = aberto;
        aberto = null;
        painel.hidden = true;
        botao.setAttribute('aria-expanded', 'false');
        busca.setAttribute('aria-expanded', 'false');
        busca.removeAttribute('aria-activedescendant');
        if (restaurarFoco) botao.focus();
    }

    function destacar(indice, rolar = false) {
        const items = lista.children;
        items[aberto.indice]?.classList.remove('is-highlighted');
        aberto.indice = indice;
        const item = items[indice];
        if (!item) {
            busca.removeAttribute('aria-activedescendant');
            return;
        }
        item.classList.add('is-highlighted');
        busca.setAttribute('aria-activedescendant', item.id);
        if (rolar) item.scrollIntoView({ block: 'nearest' });
    }

    function filtrar() {
        if (!aberto) return;
        const termo = normalizar(busca.value);
        const { select } = aberto;
        aberto.visiveis = aberto.opcoes.filter(({ texto }) => texto.includes(termo));
        const itens = aberto.visiveis.map(({ opcao }, indice) => {
            const item = criar('div', 'fin-searchable__option');
            item.id = `saari-select-opcao-${indice}`;
            item.setAttribute('role', 'option');
            item.setAttribute('aria-selected', String(opcao.selected));
            item.dataset.indice = indice;
            item.textContent = opcao.label;
            return item;
        });
        lista.replaceChildren(...itens);
        status.textContent = itens.length ? '' : 'Nenhum resultado';
        lista.scrollTop = 0;
        destacar(aberto.visiveis.findIndex(({ opcao }) => opcao.index === select.selectedIndex));
    }

    function escolher(indice) {
        const { select, visiveis } = aberto;
        const escolha = visiveis[indice]?.opcao;
        if (!escolha) return;
        const anterior = select.selectedIndex;
        select.selectedIndex = escolha.index;
        fechar(true);
        if (select.selectedIndex !== anterior) select.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function abrir(campo) {
        fechar();
        aberto = {
            ...campo,
            opcoes: Array.from(campo.select.options)
                .filter(opcao => !opcao.disabled && !opcao.hidden && !opcao.parentElement.disabled && (!campo.select.required || opcao.value))
                .map(opcao => ({ opcao, texto: normalizar(opcao.label) })),
            visiveis: [],
            indice: -1,
        };
        const recipiente = campo.select.closest('dialog, .modal, [aria-modal="true"]') || document.body;
        recipiente.append(painel);
        painel.hidden = false;
        painel.setAttribute('aria-label', campo.nome);
        lista.setAttribute('aria-label', campo.nome);
        campo.botao.setAttribute('aria-expanded', 'true');
        busca.setAttribute('aria-expanded', 'true');
        busca.setAttribute('aria-label', `Pesquisar ${campo.nome.toLowerCase()}`);
        busca.value = '';
        filtrar();
        posicionar();
        if (aberto) busca.focus();
    }

    function preparar(select) {
        if (preparados.has(select) || select.disabled || select.multiple || !select.getClientRects().length ||
            select.matches('[data-no-search], [data-fin-catalogo], .select2-hidden-accessible') ||
            select.closest('.fin-combobox, .saari-obras-panel, .fin-searchable')) return;
        const explicito = select.matches('[data-searchable], [data-force-search]');
        if (!explicito && (select.options.length < 5 || select.options.length > 750)) return;

        preparados.add(select);
        const label = select.labels[0];
        const nome = select.getAttribute('aria-label') || Array.from(label?.childNodes || [])
            .filter(node => !['SELECT', 'INPUT', 'BUTTON'].includes(node.nodeName)).map(node => node.textContent).join('').trim()
            || 'Opções';
        const container = criar('div', 'fin-searchable');
        select.before(container);
        container.append(select);

        const botao = criar('button', 'fin-searchable__button');
        if (select.closest('.fin-page')) botao.classList.add('fin-control');
        botao.type = 'button';
        botao.id = `saari-select-gatilho-${++sequencia}`;
        botao.setAttribute('aria-haspopup', 'dialog');
        botao.setAttribute('aria-controls', painel.id);
        botao.setAttribute('aria-expanded', 'false');
        const texto = document.createElement('span');
        const chevron = document.createElement('span');
        chevron.setAttribute('aria-hidden', 'true');
        chevron.textContent = '⌄';
        botao.append(texto, chevron);

        const erro = criar('small', 'fin-searchable__error');
        erro.id = `${botao.id}-erro`;
        erro.setAttribute('aria-live', 'polite');
        botao.setAttribute('aria-describedby', [select.getAttribute('aria-describedby'), erro.id].filter(Boolean).join(' '));

        function sincronizar() {
            texto.textContent = select.selectedOptions[0]?.label || 'Selecionar';
            botao.setAttribute('aria-label', `${nome}. ${texto.textContent}`);
            botao.disabled = select.matches(':disabled');
            if (select.validity.valid) {
                botao.removeAttribute('aria-invalid');
                erro.textContent = '';
            }
        }

        select.tabIndex = -1;
        select.classList.add('fin-searchable__native');
        select.setAttribute('aria-hidden', 'true');
        if (label) label.htmlFor = botao.id;
        container.append(botao, erro);
        botao.addEventListener('click', () => {
            if (aberto?.botao === botao) fechar(true);
            else abrir({ select, botao, nome });
        });
        select.addEventListener('change', sincronizar);
        select.form?.addEventListener('reset', () => setTimeout(sincronizar, 0));
        select.addEventListener('invalid', event => {
            event.preventDefault();
            botao.setAttribute('aria-invalid', 'true');
            erro.textContent = select.validationMessage;
            if (!select.form || select.form.querySelector(':invalid') === select) botao.focus();
        });
        new MutationObserver(sincronizar).observe(select, { attributes: true, attributeFilter: ['disabled'], childList: true });
        sincronizar();
        return botao;
    }

    busca.addEventListener('input', filtrar);
    busca.addEventListener('keydown', event => {
        if (!aberto) return;
        if (event.key === 'Enter') {
            event.preventDefault();
            escolher(Math.max(0, aberto.indice));
        }
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            const incremento = event.key === 'ArrowDown' ? 1 : -1;
            destacar(Math.min(aberto.visiveis.length - 1, Math.max(0, aberto.indice + incremento)), true);
        }
    });
    lista.addEventListener('pointerdown', event => {
        if (event.pointerType === 'mouse') event.preventDefault();
    });
    lista.addEventListener('click', event => {
        const item = event.target.closest('[data-indice]');
        if (aberto && item) escolher(Number(item.dataset.indice));
    });

    document.addEventListener('keydown', event => {
        if (aberto && event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            fechar(true);
        }
    }, true);
    function fecharAoSair(event) {
        if (aberto && !painel.contains(event.target) && !aberto.botao.contains(event.target)) fechar();
    }
    document.addEventListener('pointerdown', fecharAoSair);
    document.addEventListener('focusin', event => {
        fecharAoSair(event);
        if (event.target.matches(seletor)) preparar(event.target)?.focus();
    });
    window.addEventListener('resize', posicionar);
    window.addEventListener('scroll', posicionar, true);
    window.visualViewport?.addEventListener('resize', posicionar);
    document.addEventListener('toggle', event => {
        if (event.target.open) event.target.querySelectorAll(seletor).forEach(preparar);
    }, true);
    document.addEventListener('shown.bs.modal', event => event.target.querySelectorAll(seletor).forEach(preparar));
    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll(seletor).forEach(preparar));
})();
