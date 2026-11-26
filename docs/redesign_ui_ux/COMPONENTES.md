# Componentes reutilizáveis

| Componente | Como usar |
| --- | --- |
| Cabeçalho | `components/page_header.html` recebe `heading` e, quando necessário, `context_text` ou `action_url` e `action_label`. Controles específicos podem ficar no cabeçalho próprio do módulo. |
| Navegação | `components/erp_sidebar_navigation.html`, `erp_breadcrumbs.html` e `erp_search.html` usam os destinos preparados pelo Django. O bloco `breadcrumbs` permite usar o percurso completo em telas de detalhe. |
| Tema | `components/theme_init.html` é carregado no head. `components/theme_picker.html` é o seletor compartilhado. |
| Dropdown pesquisável | `select[data-searchable]` preserva o select nativo para envio e validação. Campo de busca no painel, acentos, setas, seleção, retorno de foco e estado sem resultados. Catálogos assíncronos continuam sob o controlador que já carrega os dados. |
| Tabelas e filtros | `.saari-table-scroll` limita rolagem horizontal à tabela. Classes existentes de Financeiro, Compras, Obras, Cadastros e Pós-Obra consomem tokens semânticos e mantêm parâmetros das listagens. `.saari-money` é o alinhamento tabular compartilhado. |
| Feedback | Erros críticos ficam visíveis através do bloco de mensagens ou junto ao campo. Ações menores podem usar carregamento local no botão. Downloads mantêm navegação nativa. |
| Painéis e caixas de diálogo | Painéis compartilham superfície, contorno e raio. A busca global e a confirmação de saída usam diálogos nativos e foco restaurado. |
