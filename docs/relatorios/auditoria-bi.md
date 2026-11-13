# Auditoria BI dos relatórios SAARI

Data: 2026-11-11. Perfil `.codex/agents/bi.toml` e `AGENTS.md` lidos integralmente. Auditoria estática anterior à implementação; referências de linhas correspondem à versão inspecionada. Nenhum banco, credencial ou `.env` acessado. As fórmulas são responsabilidade da auditoria de dados; as recomendações abaixo não as redefinem.

## Inventário individual: 50 painéis

BH significa barras horizontais; CM, colunas mensais cronológicas. Contagens devem partir de zero e usar intervalos inteiros. Percentuais usam escala 0–100; p.p. preservam sinal. A ordem indicada deve ser entregue pelo produtor. Todas as sugestões mantêm Apache ECharts e os tokens marrom/bege/dourado existentes.

| Página | Painel | Apresentação recomendada e observação |
|---|---|---|
| Geral | Pedidos por mês | CM em BRL; contratação, não pagamento. |
| Geral | OS abertas por mês | CM de contagem. |
| Geral | Situação das OS abertas no período | BH por status em ordem estável. |
| Projetos | Distribuição documental | BH por status; incluir universo aplicável e não aplicável na explicação. |
| Projetos | Pendências por obra | BH decrescente, contagem. |
| Projetos | Alterações por disciplina | BH decrescente, contagem. |
| Projetos | Alterações registradas por mês | CM de contagem. |
| Projetos | Menor conclusão documental por obra | BH percentual crescente; apresentar base amostral. |
| Projetos | Pendências documentais críticas | BH decrescente; explicar critério textual de criticidade. |
| Projetos | Pendências por grupo | BH decrescente, contagem. |
| Obras | Situação das FVS | BH por status. |
| Obras | FVS por obra | BH decrescente, contagem. |
| Obras | FVS emitidas por mês | CM de contagem. |
| Obras | Vistorias por situação | BH por status. |
| Obras | Movimentações de estoque por tipo | BH de registros, não quantidade física ou custo. |
| Obras | Não conformidades por item de verificação | BH de itens NC, não taxa por serviço. |
| Obras | Não conformidade por empresa executora | BH percentual decrescente; numerador e denominador visíveis no detalhe. |
| Obras | FVS por empresa executora | BH de contagem, complementar à taxa. |
| Obras | Saídas de materiais mais frequentes | BH de frequência de registros, não volume consumido. |
| Obras | Ocorrências cautelares por manifestação | BH decrescente, contagem. |
| Obras | Diários por obra | BH decrescente, contagem. |
| Suprimentos | Pedidos por mês | CM em BRL. |
| Suprimentos | Situação dos pedidos | BH por status. |
| Suprimentos | Compras por obra | BH em BRL decrescente. |
| Suprimentos | Compras por fornecedor | BH em BRL decrescente; identidade do fornecedor não deve depender do nome. |
| Suprimentos | Etapas dos processos | BH na ordem do fluxo; não tratar como funil de conversão. |
| Suprimentos | Tempo médio por etapa | BH em dias, ordem do fluxo; indicar amostra por etapa e ausência. |
| Suprimentos | Fornecedores com pedidos abertos atrasados | BH percentual, acompanhada de atrasados/total; explicitar mínimo de três pedidos. |
| Suprimentos | Decisões de aprovação | BH por decisão, contagem. |
| Suprimentos | Compras por responsável | BH de pedidos; explicitar que não é valor monetário. |
| Planejamento | Avanço executado por obra | BH percentual; comparação agrupada previsto/executado por obra e projeto quando produzida pelo backend. |
| Planejamento | Desvio físico por obra | BH divergentes em p.p., zero explícito, sinal preservado. |
| Planejamento | Situação dos marcos | BH em ordem semântica. |
| Planejamento | Contratações pendentes vencidas por obra | BH decrescente, contagem. |
| Planejamento | Suprimentos programados por categoria | BH decrescente, contagem. |
| Financeiro | Previsão financeira por mês | CM em BRL. |
| Financeiro | Pagamentos efetivados por mês | CM em BRL, mesmos períodos e escala quando comparados. |
| Financeiro | Previsões por nível de certeza | BH em BRL, ordem explícita. |
| Pós-Obra | Abertura de OS por mês | CM de contagem. |
| Pós-Obra | OS por situação | BH por status. |
| Pós-Obra | Tipos de problema | BH de contagem por tipo. |
| Pós-Obra | OS por empreendimento | BH decrescente. |
| Pós-Obra | Prioridade dos chamados | BH na ordem de criticidade. |
| Pós-Obra | Resolução informada pelo cliente | BH por resposta; consolidar duplicação abaixo. |
| Pós-Obra | Notas médias da pesquisa | Pontos horizontais em escala 1–5; informar amostra e ausência. |
| Pós-Obra | OS por 100 unidades (obras atuais) | BH em OS/100 unidades, sem teto de 100; excluir históricos sem base conforme regra validada. |
| Pós-Obra | Custo de materiais por tipo de problema | BH em BRL; não equivale a custo total. |
| Pós-Obra | Tipos de problema mais frequentes | BH por categoria; renomear para distinguir do agrupamento por tipo. |
| Pós-Obra | OS por responsável | BH de contagem. |
| Pós-Obra | Resolução declarada pelo cliente | Duplicação da resolução informada; remover duplicata conforme plano técnico. |

Fontes do inventário: `relatorios/views/painel.py:212`, `:228`, `:250`, `:273`, `:297`; `relatorios/services/analises.py:55`, `:86`, `:152`, `:204`; `relatorios/services/estrategicos.py:102`, `:133`, `:163`, `:219`. Contagens por página: 3 + 7 + 11 + 9 + 5 + 3 + 12 = 50. Esta é a linha de base auditada; a remoção de duplicação e os novos indicadores previstos podem alterar a contagem final.

## Achados e prioridades

### P0: interpretação e integração

- Contrato original infere temporalidade pela presença de `raw` (`views/painel.py:99`), extrai números do texto da tabela (`templates/relatorios/painel.html:543`), decide rosca por título/quantidade (`:555`) e escolhe linha conforme quantidade de observações (`:559`). Substituir pelas propriedades explícitas do contrato aprovado.
- Três painéis não chegam ao ECharts: dias (`analises.py:126`), fornecedores com texto n/d (`:142`) e notas x/5 (`:180`) são rejeitados pelo parser (`painel.html:361`, `:547`). Uma única ausência também impede o gráfico inteiro. Transportar número e texto separadamente.
- As captions metodológicas existem nos serviços, mas o cabeçalho só renderiza título (`painel.html:219`). Exibir detalhe curto expansível conforme plano, incluindo unidade, base, período e exclusões.
- `_ranking_panel` força as séries financeiras a ranking (`views/painel.py:323`, `:328`); corrigir a orientação e a natureza temporal explicitamente.
- `_ranking` usa módulo na largura (`estrategicos.py:29`); fallback CSS cresce só à direita (`painel.html:261`), ocultando visualmente o sinal. A impressão oculta todos os fallbacks (`:47`), inclusive os gráficos que não ativam ECharts. Exigir representação fiel ou tabela impressa.
- ECharts declarado na versão 6.1.0 via CDN (`painel.html:291`), inicializado em canvas (`:519`). O atributo contém literalmente `https\://`; corrigir e verificar carregamento. A versão efetivamente carregada não foi confirmada em navegador nesta auditoria.

### P1: escalas, tempo e comparação

- Eixos genéricos não identificam BRL, %, p.p., dias ou OS/100 (`painel.html:453`, `:475`, `:485`). Tooltips atuais mostram texto, mas não universo ou base amostral. Unidades precisam ser coerentes entre eixo, tabela e tooltip.
- `_series` conserva meses existentes e últimos 12 registros (`views/painel.py:92`); meses ausentes ficam comprimidos. Construir calendário explícito e distinguir mês sem eventos de mês sem cobertura. Linha suavizada com área (`painel.html:455`) sugere continuidade não demonstrada; evitar suavização e interpolação de lacunas.
- Limites 8, 10 e 12 são silenciosos (`views/painel.py:72`; `analises.py:48`, `:66`, `:142`, `:186`; `estrategicos.py:27`). Informar recorte e ordenação no detalhe, inclusive na exportação. Não converter top N em composição do total.
- Planejamento seleciona por obra/projeto, mas rótulo vinculado usa só obra (`estrategicos.py:68`, `:97`). Identificar ambos para evitar rótulos iguais e alinhamento incorreto.
- A visão geral originalmente mantém OS consolidadas sob filtro de obra (`views/painel.py:215`). Após correção prevista no plano, o detalhe precisa refletir os vínculos reais e informar exclusões; não presumir universos iguais entre módulos.
- Altura fixa 245–325 px e truncamento de rótulos (`painel.html:45`, `:47`, `:487`) precisam de validação com 12 categorias, nomes longos e celular. Não resolver ocultando categorias silenciosamente.

### P2: redundância e acessibilidade

- Resolução informada e declarada usam o mesmo agrupamento (`views/painel.py:302`; `analises.py:209`). Tipo e categoria de problema têm nomes insuficientemente distintos.
- Há tabela alternativa, foco visível, ARIA, resize e observador de tema; a descrição ARIA usa apenas título (`painel.html:425`). Descrição deve incluir unidade, contexto e acesso à tabela. Não foi validada navegação real por teclado ou leitor de tela.
- Preservar tokens da página (`painel.html:13`, `:35`) e herança de `layouts/base.html` (`:1`). Diferenciar séries também por rótulo/símbolo/traço; contraste escuro e tooltips dependem de verificação visual posterior.

## Revisão do contrato simplificado aprovado

Referência normativa: [plano-tecnico.md](plano-tecnico.md), seção Contrato de apresentação. Esta revisão utiliza o contrato existente, sem impor novo esquema extenso.

- Manter `title`, `caption`, `rows`, `kind`; cada linha oferece `label`, `value` textual, `raw` numérico ou null e `width` apenas para fallback. O cliente não deve calcular fórmulas de indicadores nem recuperar números de `value`.
- `chart.type`, `orientation`, `unit`, `precision`, `min`, `max`, `sort`, `negative` e `allowed_types` devem ser definidos pelo produtor. Ausência de metadado obrigatório deve preservar a tabela e gerar diagnóstico de desenvolvimento; não inferir pelo título ou pelo número de linhas.
- `sort=source` preserva a ordem semântica já produzida. Em `chronological`, o backend entrega a ordem cronológica correta; não ordenar `MM/AAAA` lexicograficamente. Nunca ordenar uma série sem aplicar a mesma permutação a todas as outras.
- `series: [{name, values}]` deve ter comprimento idêntico a `rows`; cada índice representa a mesma obra/projeto ou período. Nomes de séries precisam ser estáveis e inequívocos. `null` numa série não remove a categoria das demais. Validar comprimentos e valores finitos antes de renderizar.
- Previsto/executado físico: barras agrupadas, não empilhadas; mesma escala 0–100, legenda explícita, tooltip e tabela exibindo ambas as séries. Rótulo identifica obra/projeto. O desvio em p.p. continua sendo produzido no backend e apresentado separadamente; não deduzi-lo no navegador.
- Previsão/pagamento financeiro: se comparados, alinhar calendário, moeda e escala, mas manter a distinção de população/data. Não calcular erro histórico nem somar as séries. Calendário ausente não autoriza preencher com zero sem cobertura verificada.
- `raw=null` significa ausência, nunca zero. Mostrar traço e explicação no texto, lacuna no gráfico e nenhuma ligação sobre a lacuna em linhas. Um painel parcialmente nulo continua mostrando observações válidas; painel todo nulo apresenta ausência. Zero observado deve permanecer zero.
- `negative=true` autoriza o sinal, não força converter valores em módulo. P.p. usa referência de zero e escala que inclua todos os valores. Quando `negative=false`, valor negativo recebido deve ser sinalizado como inconsistência, não truncado silenciosamente. Fallback também deve preservar sinal ou apresentar tabela.
- `allowed_types` deve conter somente modos semanticamente válidos: categorias nominais usam bar; notas podem usar scatter; séries temporais podem permitir bar/line. Não oferecer linha para ranking de fornecedores/status nem mudar orientação temporal ao alternar modo. O contrato aprovado não inclui pie: retirar a seleção heurística de rosca, sem necessidade de ampliar o contrato nesta etapa.
- Escalas: count inicia em zero e usa intervalos inteiros; percent usa 0–100; score usa 1–5 com pontos, evitando barras com origem truncada; percentage_point inclui zero e sinal; rate OS/100 não tem teto artificial; currency usa precisão 2 no tooltip/tabela, com unidade e eventual abreviação explicitadas no eixo; days parte de zero. Não ocultar valores fora dos limites: sinalizar inconsistência para validação de dados.
- `precision` controla exibição, não arredondamento prematuro de comparação. Tooltips de múltiplas séries devem mostrar todas as observações daquele índice, não apenas `params[0]`. A tabela alternativa e exportação precisam preservar a mesma comparação para acessibilidade.
- Metodologia, amostra, limites de top N e filtros podem permanecer em `caption`/texto existente, em detalhe expansível. Não é necessário criar o contrato extenso originalmente sugerido para garantir essas informações.

## Evidências e limitações de validação

Executados comandos de leitura `Get-Content -Encoding UTF8`, pesquisas `rg` de painéis, versão ECharts e estilos, e `git status --short`. Na auditoria inicial, Git apresentou apenas `.codex/`, `AGENTS.md` e `relatorios.zip` não rastreados. Uma pesquisa `rg relatorios/tests*` falhou por glob inválido no Windows; não constitui teste da aplicação.

Não foram executados testes Django, consultas ao banco, navegador, validação de CDN, contraste ou screenshots. Nenhuma alegação de cálculo validado com dados reais ou funcionamento visual em runtime é feita. Este arquivo registra recomendações e fatos do código anterior; a implementação e seus testes devem ser revisados separadamente, com dados sintéticos identificados e banco isolado conforme plano.
