# Auditoria inicial do ERP SAARI

Base `94dc49c` em `main`, com árvore limpa antes do trabalho. Python 3.13.18 do ambiente virtual. O ambiente de testes existente usa SQLite em memória, mídia temporária e Drive desativado. O Django check passou e os 25 testes iniciais de Diário, Vistorias e Ficha Técnica passaram.

| Área | Implementação existente | Pendência observada |
| --- | --- | --- |
| Compras | Pedidos com paginação SQL, configuração de SLA e histórico de etapas | Lista materializa IDs antes de paginar, SLA carrega processos e passagens em lote, detalhe monta etapas ocultas |
| Almoxarifado | Reservas por necessidade, bloqueio por saldo e exceção auditada | Distinguir pedidos de uma necessidade dos pedidos de outro processo. Concorrência exige teste MySQL |
| Suprimentos | Histórico de compras carregado sob demanda | Painel materializa itens e computa cadeia comercial antes da busca, expandíveis já vêm renderizados |
| Cronograma Físico | Curva S, avanço mensal incremental e previsão a partir da medição | Painel prepara e instancia dados e gráficos ocultos |
| Vistorias | Resumo por obra, filtros, PDF e permissões com testes | Conferir a consistência de totais no detalhamento e na exportação |
| Diário | Semana selecionada pelo retrato importado, escopo da obra, seleção validada e histórico legado | Lista limitada a 300 diários com pré-carregamento das relações |
| Ficha Técnica | Consulta, exportação filtrada e integração com matriz de grandes fornecedores validadas | Conferir custo e volume de conteúdo das abas |
| Projetos e Pós-Obra | Histórico de checklist sob demanda, chamados paginados | Listagens específicas usam cortes fixos ou carregam conteúdo de etapas antecipadamente |
| Interface | Tema SAARI e navegação com seleção explícita de links de transição | Filtro GET sem indicação localizada em Suprimentos. A versão auditada não possui exportação nesse formulário |

Referências de implementação anterior em `docs/RELATORIO_IMPLEMENTACAO_SAARI.md`, `docs/RELATORIO_TECNICO_SAARI.md` e `docs/relatorios/`. A auditoria utiliza as skills locais de desempenho, testes, identidade visual e integração.

A sequência de trabalho segue a ordem do pedido. A medição deve comparar dados sintéticos iguais antes e depois e registrar SQL, tempo e volume do HTML. Mudanças de interface usam os tokens e componentes existentes, com escopo fora do Financeiro. A fonte da data em que o material é necessário deve ser comprovada antes de atribuir impacto no prazo da obra.

## Revisão de continuidade de 24/11/2026

O ponto de partida foi `94dc49c` em `main` com 54 arquivos rastreados modificados e os relatórios e parciais da entrega anterior na árvore de trabalho. A suíte inicial passou com 347 testes no Python 3.13.18, SQLite em memória e mídia temporária. O `check` inicial passou. Foram reaproveitadas a paginação e as abas sob demanda da rodada anterior.

- Na Ficha Técnica, a consulta já buscava materiais por página. Os formulários de detalhamento ainda repetiam o catálogo inteiro a cada item. A edição também perdia acesso ao material que já estava vinculado e foi desativado posteriormente.
- No Pós-Obra, o agrupamento do Kanban herdava a ordenação por data e ID. Um cenário com 31 ocorrências abertas reproduziu o total incorreto de 1. O painel executava três consultas independentes para contagens da mesma tabela.
- No Planejamento, a importação traz prazos de etapas comerciais, inclusive limite para contratação. A data de necessidade na obra tem semântica própria e requer fonte explícita por item.
