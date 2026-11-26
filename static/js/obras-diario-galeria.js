(() => {
    function acompanharMiniatura(link) {
        const imagem = link.querySelector('img');
        const estado = link.querySelector('[data-diario-foto-estado]');

        function carregar() {
            imagem.hidden = false;
            estado.hidden = true;
        }

        function indisponivel() {
            imagem.hidden = true;
            estado.textContent = 'Fotografia indisponível.';
            estado.hidden = false;
        }

        imagem.addEventListener('load', carregar);
        imagem.addEventListener('error', indisponivel);
        if (imagem.complete) {
            if (imagem.naturalWidth) carregar();
            else indisponivel();
        } else {
            estado.textContent = 'Carregando fotografia…';
            estado.hidden = false;
        }
    }

    function montarGaleria(galeria) {
        const fotos = [...galeria.querySelectorAll('[data-diario-foto]')];
        const dialogo = galeria.querySelector('[data-diario-dialogo]');
        fotos.forEach(acompanharMiniatura);
        if (!dialogo?.showModal || !fotos.length) return;

        const quadro = dialogo.querySelector('[data-diario-ampliacao-foto]');
        const estado = dialogo.querySelector('[data-diario-ampliacao-estado]');
        const nome = dialogo.querySelector('[data-diario-ampliacao-nome]');
        const posicao = dialogo.querySelector('[data-diario-ampliacao-posicao]');
        const anterior = dialogo.querySelector('[data-diario-ampliacao-anterior]');
        const proxima = dialogo.querySelector('[data-diario-ampliacao-proxima]');
        const baixar = dialogo.querySelector('[data-diario-ampliacao-baixar]');
        let atual = 0;
        let disparador;
        let imagem;

        function removerImagem() {
            imagem?.remove();
            imagem?.removeAttribute('src');
            imagem = null;
        }

        function mostrar(indice) {
            atual = (indice + fotos.length) % fotos.length;
            const foto = fotos[atual];
            removerImagem();
            estado.hidden = false;
            estado.textContent = 'Carregando fotografia…';
            nome.textContent = foto.dataset.diarioNome;
            posicao.textContent = `${atual + 1} de ${fotos.length}`;
            baixar.href = foto.dataset.diarioOriginal;

            const novaImagem = new Image();
            imagem = novaImagem;
            novaImagem.alt = foto.dataset.diarioNome;
            novaImagem.hidden = true;
            novaImagem.addEventListener('load', () => {
                if (imagem !== novaImagem) return;
                novaImagem.hidden = false;
                estado.hidden = true;
            }, {once: true});
            novaImagem.addEventListener('error', () => {
                if (imagem !== novaImagem) return;
                estado.textContent = 'Fotografia indisponível.';
            }, {once: true});
            quadro.append(novaImagem);
            novaImagem.src = foto.href;
        }

        fotos.forEach((foto, indice) => {
            foto.addEventListener('click', evento => {
                if (evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
                evento.preventDefault();
                disparador = foto;
                dialogo.showModal();
                mostrar(indice);
            });
        });
        anterior.hidden = proxima.hidden = fotos.length === 1;
        anterior.addEventListener('click', () => mostrar(atual - 1));
        proxima.addEventListener('click', () => mostrar(atual + 1));
        dialogo.addEventListener('keydown', evento => {
            if (evento.key === 'Escape') {
                evento.preventDefault();
                dialogo.close();
            } else if (fotos.length > 1 && ['ArrowLeft', 'ArrowRight'].includes(evento.key)) {
                evento.preventDefault();
                mostrar(atual + (evento.key === 'ArrowLeft' ? -1 : 1));
            }
        });
        dialogo.addEventListener('click', evento => {
            if (evento.target === dialogo) dialogo.close();
        });
        dialogo.addEventListener('close', () => {
            removerImagem();
            disparador?.focus();
        });
    }

    document.querySelectorAll('[data-diario-galeria]').forEach(montarGaleria);
})();
