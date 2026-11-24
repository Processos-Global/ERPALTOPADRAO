(() => {
  function init(field) {
    const dropdown = field.querySelector('details');
    const summary = dropdown.querySelector('summary');
    const search = dropdown.querySelector('input[type="search"]');
    const results = dropdown.querySelector('ul');
    const status = dropdown.querySelector('[role="status"]');
    const more = dropdown.querySelector('[data-material-mais]');
    const selected = field.querySelector('input[name="material"]');
    let request;
    let debounce;
    let page = 1;

    function choose(id, label) {
      selected.value = id;
      summary.querySelector('[data-material-label]').textContent = label;
      dropdown.open = false;
      summary.focus();
    }

    async function load(targetPage) {
      request?.abort();
      const controller = new AbortController();
      request = controller;
      const url = new URL(field.dataset.materialUrl, document.baseURI);
      url.searchParams.set('q', search.value.trim());
      url.searchParams.set('pagina', targetPage);
      status.textContent = 'Buscando materiais…';
      more.disabled = true;
      try {
        const response = await fetch(url, {signal: controller.signal});
        if (!response.ok) throw new Error('Falha na consulta');
        const data = await response.json();
        if (controller.signal.aborted) return;
        for (const material of data.resultados) {
          const item = document.createElement('li');
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = material.texto;
          button.addEventListener('click', () => choose(material.id, material.texto));
          item.append(button);
          results.append(item);
        }
        page = targetPage;
        more.hidden = !data.mais;
        status.textContent = results.childElementCount ? '' : 'Nenhum material encontrado.';
      } catch (error) {
        if (!controller.signal.aborted) {
          status.textContent = 'Não foi possível buscar materiais.';
          more.hidden = false;
          more.textContent = 'Tentar novamente';
          more.dataset.retry = targetPage;
        }
      } finally {
        if (request === controller) more.disabled = false;
      }
    }

    function prepareSearch() {
      clearTimeout(debounce);
      request?.abort();
      results.replaceChildren();
      more.hidden = true;
      more.textContent = 'Carregar mais';
      delete more.dataset.retry;
    }

    dropdown.addEventListener('toggle', () => {
      prepareSearch();
      if (!dropdown.open) return;
      search.value = '';
      search.focus();
      load(1);
    });
    search.addEventListener('input', () => {
      prepareSearch();
      debounce = setTimeout(() => load(1), 250);
    });
    search.addEventListener('keydown', event => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      results.querySelector('button')?.click();
    });
    dropdown.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || !dropdown.open) return;
      dropdown.open = false;
      summary.focus();
    });
    const clear = dropdown.querySelector('[data-material-limpar]');
    clear.addEventListener('click', () => choose('', clear.textContent));
    more.addEventListener('click', () => {
      const target = Number(more.dataset.retry) || page + 1;
      more.textContent = 'Carregar mais';
      delete more.dataset.retry;
      load(target);
    });
  }
  document.querySelectorAll('[data-material-url]').forEach(init);
  document.addEventListener('pointerdown', event => {
    for (const dropdown of document.querySelectorAll('[data-material-url] details[open]')) {
      if (!dropdown.contains(event.target)) dropdown.open = false;
    }
  });
})();
