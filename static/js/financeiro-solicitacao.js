(function () {
    'use strict';

    const form = document.getElementById('titulo-form');
    if (!form) return;

    const botao = form.querySelector('[data-avulsa-submit]');
    let enviando = false;
    let consultandoBanco = false;
    let prazoEnvio;

    function atualizarBotao() {
        botao.disabled = enviando || consultandoBanco;
        botao.classList.toggle('is-submitting', enviando);
        if (enviando) botao.setAttribute('aria-busy', 'true');
        else botao.removeAttribute('aria-busy');
    }

    function restaurarEnvio() {
        clearTimeout(prazoEnvio);
        enviando = false;
        atualizarBotao();
    }

    form.addEventListener('submit', event => {
        if (event.defaultPrevented) return;
        if (enviando || consultandoBanco) {
            event.preventDefault();
            return;
        }
        enviando = true;
        atualizarBotao();
        prazoEnvio = setTimeout(restaurarEnvio, 12000);
    });
    form.addEventListener('invalid', event => {
        const secao = event.target.closest('details');
        if (secao) secao.open = true;
    }, true);
    window.addEventListener('pageshow', restaurarEnvio);

    const classificacao = form.elements.tipo_pagamento;
    const materiais = document.getElementById('bloco-materiais');
    if (materiais) {
        const blocoDescricao = document.getElementById('bloco-descricao');
        const campoDescricao = document.getElementById('campo-descricao-pagamento');
        const descricao = form.elements.descricao;
        const especificacao = form.elements.especificacao_pagamento;
        const label = form.querySelector('label[for="id_especificacao_pagamento"]');
        function atualizarClassificacao() {
            const tipo = classificacao.value;
            materiais.hidden = tipo !== 'MATERIAL';
            blocoDescricao.hidden = tipo === 'MATERIAL';
            campoDescricao.hidden = tipo === 'REEMBOLSO';
            descricao.required = tipo === 'OUTRO' || tipo === 'SERVICO';
            especificacao.required = tipo !== 'MATERIAL';
            label.textContent = tipo === 'REEMBOLSO' ? 'O que está sendo reembolsado' : 'O que está sendo pago';
        }
        classificacao.addEventListener('change', atualizarClassificacao);
        atualizarClassificacao();
    }

    const intervalo = document.getElementById('campo-intervalo-parcelas');
    if (intervalo) {
        const quantidade = form.elements.quantidade_parcelas;
        function atualizarIntervalo() {
            const parcelado = Number(quantidade.value) > 1;
            intervalo.hidden = !parcelado;
            form.elements.intervalo_dias.required = parcelado;
        }
        quantidade.addEventListener('input', atualizarIntervalo);
        atualizarIntervalo();
    }

    const fornecedor = form.elements.fornecedor;
    const secaoBanco = document.getElementById('secao-bancaria');
    if (!fornecedor || !secaoBanco) return;

    const status = document.getElementById('status-dados-bancarios');
    const camposBancarios = ['documento', 'banco', 'agencia', 'conta_corrente', 'operacao', 'pix', 'titular'];
    let consulta;
    fornecedor.addEventListener('change', async () => {
        consulta?.abort();
        consulta = new AbortController();
        const atual = consulta;
        const id = fornecedor.value;
        for (const campo of camposBancarios) form.elements[`beneficiario_${campo}`].value = '';
        if (!id) {
            consultandoBanco = false;
            atualizarBotao();
            status.textContent = '';
            return;
        }

        secaoBanco.open = true;
        consultandoBanco = true;
        atualizarBotao();
        status.textContent = 'Consultando dados do fornecedor…';
        const url = new URL(form.dataset.finCatalogoUrl, window.location.href);
        url.searchParams.set('tipo', 'dados_bancarios');
        url.searchParams.set('id', id);
        const prazo = setTimeout(() => atual.abort(), 8000);
        try {
            const resposta = await fetch(url, { signal: atual.signal, headers: { Accept: 'application/json' } });
            if (resposta.status === 404) {
                if (consulta === atual) status.textContent = 'Dados bancários indisponíveis no cadastro.';
                return;
            }
            if (!resposta.ok) throw new Error('Consulta indisponível');
            const dados = await resposta.json();
            if (consulta !== atual) return;
            for (const campo of camposBancarios) {
                const controle = form.elements[`beneficiario_${campo}`];
                if (!controle.value) controle.value = dados[campo] || '';
            }
            status.textContent = 'Confira os dados bancários antes de salvar.';
        } catch (erro) {
            if (consulta === atual) status.textContent = 'Não foi possível consultar o cadastro. Confira os dados antes de salvar.';
        } finally {
            clearTimeout(prazo);
            if (consulta === atual) {
                consultandoBanco = false;
                atualizarBotao();
            }
        }
    });
})();
