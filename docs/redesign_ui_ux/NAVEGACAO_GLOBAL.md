# Navegação global

O menu, o painel inicial e o índice da busca consomem os mesmos destinos. O Django resolve nomes de rota e monta os links com a autorização existente. A busca lê os links do menu no DOM e faz correspondência local por rótulo, termos relacionados e módulo, sem distinguir caixa ou acentos. `Ctrl+K` e `Command+K` abrem a busca. Setas percorrem resultados. Enter abre a opção e Esc fecha o diálogo.

No desktop, o menu recolhido mantém ícones com rótulo apresentado ao apontar ou focar. A barra pode ser expandida para abrir submenus. Em telas estreitas, o menu é um painel com fechamento por Escape e devolução de foco ao botão. A seção ativa é aberta com o destino correspondente destacado.

Favoritos e recentes são IDs de rotas estáticas válidas, filtrados novamente pelo menu a cada abertura. As chaves de armazenamento local são separadas por conta, inclusive para o estado dos submenus. Detalhes de registro e consultas de filtro ficam fora desse armazenamento.

Em fluxos de lista e detalhe, o link de retorno é validado pelo nome da rota de lista e o Django reconstitui sua consulta. Filtros repetidos e paginação são preservados. A posição de rolagem é mantida pelo histórico do navegador quando disponível. As telas com links contextuais de filtros usam as rotas e permissões do módulo de destino.

Entre módulos, a Ficha Técnica abre o relatório de Grandes Fornecedores da mesma obra, o título financeiro aponta para o pedido de origem quando vinculado e a lista de pedidos abre o compromisso filtrado no Financeiro. O Diário mantém seus links para Concretagens da mesma obra e data.

O Portal do Cliente tem seu próprio conjunto de rotas. Operações internas, notificações do ERP e resultados de busca internos ficam restritos ao espaço interno.
