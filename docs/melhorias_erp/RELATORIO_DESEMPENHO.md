# Desempenho

Dados sintéticos em SQLite em memória, com a mesma massa antes e depois. Cada requisição mediu a view e a renderização Django com usuário autenticado via RequestFactory. Tempo de rede, navegador e MySQL não integram os resultados.

| Tela e cenário | SQL antes → depois | Mediana antes → depois | HTML antes → depois | Ganho de tempo |
| --- | ---: | ---: | ---: | ---: |
| Compras, processos sem filtro SLA | 5 → 6 | 795,2 → 113,6 ms | 115.952 → 115.952 B | 85,7% |
| Compras, filtro de processos atrasados | 5 → 6 | 557,7 → 122,0 ms | 115.977 → 115.977 B | 78,1% |
| Compras, dashboard com filtro de obra | 5 → 15 | 445,6 → 134,6 ms | 466.524 → 466.524 B | 69,8% |
| Diário, primeira página filtrada por obra e data | 6 → 7 | 87,2 → 14,7 ms | 256.391 → 110.493 B | 83,1% |
| Ficha Técnica, consulta inicial com 20 ambientes e 1.000 itens | 7 → 6 | 160,4 → 8,9 ms | 322.574 → 102.782 B | 94,5% |
| Cronograma Físico, visão geral | 10 → 6 | 24,10 → 5,57 ms | 406.136 → 141.938 B | 76,9% |
| Cronograma de Suprimentos, listagem | 13 → 5 | 84,65 → 26,80 ms | 695.051 → 440.806 B | 68,3% |

- Compras utilizou 2.000 processos, 4.000 passagens, 2.000 pedidos e cinco amostras após aquecimento. A consulta adicional é a contagem da paginação. A classificação de SLA ainda percorre as projeções necessárias para preservar a regra de dias úteis.
- No dashboard de Compras, a massa foi distribuída em todos os estados dos processos. As consultas adicionais selecionam IDs limitados por estado e evitam carregar todos os processos para compor o Kanban.
- Diário utilizou 301 registros da mesma obra e cinco amostras após aquecimento. A quantidade de diários materializados para a resposta caiu de 300 para 30. A consulta adicional é a contagem da paginação.
- A consulta da Ficha Técnica usou 20 ambientes com 50 itens cada e cinco amostras após aquecimento. A abertura agrega os itens por ambiente e adia a consulta das 1.000 linhas até a abertura dos respectivos detalhes.
- Cronograma Físico utilizou quatro semanas com 100 atividades por semana. Suprimentos utilizou 50 itens com um processo, uma cotação, uma solicitação e um pedido por item. Cada cenário teve sete amostras após aquecimento. As medições do Planejamento comparam a abertura inicial de cada painel.
- Ficha Técnica, Vistorias e Projetos receberam regressões específicas de consulta e renderização. O teste da tela de pavimentos registrou duas consultas diretas à tabela de itens antes da mudança e uma consulta de contagem depois.

O benchmark compara a base `94dc49c` à árvore de trabalho. As medições abrangem cenários específicos e não estabelecem o cumprimento geral das metas de latência.

No SQLite, `EXPLAIN QUERY PLAN` confirma o índice `obras_diario_obra_dt_idx` para obra e data no Diário e `proj_alt_obra_data_idx` para o filtro por obra em Projetos. A ordenação final de Projetos por ID usa estrutura temporária como desempate. Os planos de execução do MySQL ainda precisam ser medidos com o volume de homologação.

## Medições complementares

| Cenário SQLite | SQL antes → depois | Mediana antes → depois | HTML antes → depois |
| --- | ---: | ---: | ---: |
| Ficha Técnica, edição de 21 itens com 1.001 materiais ativos | 15 → 14 | 616,80 → 43,78 ms | 1.317.686 → 191.177 B |
| Cadastros, lista filtrada com 1.000 materiais ativos | 2 → 3 | 258,28 → 29,14 ms | 426.454 → 101.830 B |
| Pós-Obra, consultas de contagem no painel | 3 → 1 | — | — |

A Ficha Técnica foi medida com `RequestFactory`, usuário sintético, uma obra e um ambiente, em sete respostas após aquecimento por cenário. O comparativo isolou a seleção de materiais, reaplicando o parcial anterior e sua consulta de catálogo sobre o mesmo backend e a mesma massa. O HTML da página passou a depender dos materiais vinculados aos itens. A busca do catálogo acontece em páginas de 20 registros.

Cadastros usou sete amostras após aquecimento, com a mesma view e template, comparando o corte anterior de 1.000 linhas à paginação atual de 30. A consulta adicional conta os registros no recorte filtrado. O mesmo padrão foi aplicado às listas de fornecedores e de mão de obra.
