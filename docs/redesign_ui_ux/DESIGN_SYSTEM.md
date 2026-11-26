# Design System SAARI

[saari-tokens.css](../../static/css/saari-tokens.css) define marca, superfícies, tipografia, espaçamento, bordas, foco, movimento, estados semânticos, séries de gráficos e variáveis de integração com Bootstrap. O ERP usa Django Templates e CSS/JavaScript nativos. O layout global não carrega um pacote Bootstrap.

| Família | Uso |
| --- | --- |
| `--saari-brand-*` | Cores fixas da identidade |
| `--saari-primary`, `--saari-on-primary`, `--saari-accent` | Ação principal e links |
| `--saari-bg`, `--saari-surface`, `--saari-surface-elevated` | Fundo, cards e elementos sobrepostos |
| `--saari-input-bg`, `--saari-control-border`, `--saari-focus-ring` | Estado de campos e controles |
| `--saari-success`, `--saari-warning`, `--saari-danger`, `--saari-info` | Estados com sentido no fluxo e com rótulo textual |
| `--saari-series-planned`, `--saari-series-actual` | Séries de previsto e realizado |

[saari-components.css](../../static/css/saari-components.css) define cabeçalho, painel, ações, filtros, tabelas, paginação, estados vazios, carregamento e foco. [saari-shell.css](../../static/css/saari-shell.css) define menu, barra, busca, notificações e perfil. [saari-legacy.css](../../static/css/saari-legacy.css) adapta componentes anteriores que ainda têm seletores específicos dos módulos.

As bibliotecas existentes de gráficos continuam com a forma de carregamento dos seus módulos. O novo dropdown é JavaScript nativo e aproveita catálogos e mecanismos assíncronos existentes.
