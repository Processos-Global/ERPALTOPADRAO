# Auditoria técnica dos indicadores SAARI ERP

Data: 2026-11-11. Escopo: diagnóstico estático das sete áreas de Relatórios, dos serviços de cálculo e dos models/fontes relacionados. Responsável: especialista dados, sob coordenação da sessão principal.

AGENTS.md e `.codex/agents/dados.toml` foram lidos integralmente. Não houve acesso ao banco, inicialização da aplicação, consulta a credenciais ou alteração de regras nesta auditoria. A confiança indicada abaixo avalia a implementação observada, não a qualidade dos registros reais. As referências descrevem o código na data da auditoria; linhas podem mudar após implementação.

## Decisões recomendadas para implementação

1. Economia negociada deve permanecer explicitamente **BRUTA**: diferença de preços unitários multiplicada pela quantidade adjudicada. Não inventar rateio de frete, desconto global ou economia líquida. Expor a cobertura dos itens comparáveis e as exclusões.
2. Saldo financeiro deve reutilizar a regra existente de `calcular_saldo_titulo`, respeitando pagamento integral e relação OneToOne. Não introduzir pagamento parcial como hipótese de negócio.
3. Aging “mais de N dias completos” deve comparar `criado_em < timezone.now() - timedelta(days=N)`, com um único instante de referência para N=30, 60 e 90. A igualdade exata a N dias não pertence ao grupo “mais de”.
4. Cobertura de pesquisa deve usar somente OS atualmente concluídas em ambos os conjuntos: OS concluídas com pesquisa / OS concluídas. Denominador zero significa indisponível, não 0%.

## Contratos comuns

- `relatorios/views/painel.py:32–61`: período inclusivo; DateTime usa intervalo local `[início 00h, dia seguinte ao fim 00h)`. Datas invertidas são trocadas; inválidas viram ausência de filtro.
- `relatorios/services/analises.py:21–25`: percentuais com uma casa; denominador zero retorna `—`; dias com uma casa. `relatorios/views/painel.py:64`: moeda com duas casas.
- `relatorios/views/painel.py:72–96`: rankings gerais limitados a oito categorias, sem “Outros”; séries limitadas aos últimos doze meses com registros. Gráficos truncados não necessariamente reconciliam com cartões totais.
- `relatorios/views/painel.py:83–91`: agrupamento mensal DateTime em UTC, enquanto filtro é local. Há risco de mês diferente para registros próximos à virada mensal; padronizar o contrato de fuso.
- A maioria dos números mostra situação atual de uma coorte criada no período, não posição histórica no fim do período.
- Formatação não documenta uma política financeira explícita de arredondamento. Preservar Decimal nos cálculos monetários; arredondar apenas na apresentação, conforme regra vigente do projeto.

## 1. Visão Geral

Objetivo: resumir volumes, situação documental, qualidade, compras, atendimento e avanço físico. Fonte: `relatorios/views/painel.py:183–215`.

| Indicador | Origem, fórmula e unidade | Período e filtros |
| --- | --- | --- |
| Obras em andamento | Contagem de Obra com status EM_ANDAMENTO | Global e atual; ignora período e obra selecionada |
| Itens documentais | Contagem de ChecklistProjetoResposta | Criação no período e obra |
| FVS abertas | Contagem de FVS, inclusive aprovadas | Data de abertura no período e obra |
| Valor dos pedidos | Soma de PedidoCompra.valor_total, R$ | Data do pedido, obra; exclui CANCELADO |
| OS abertas | Contagem de Chamado | Criação no período; não aplica obra |
| OS ainda não concluídas | Contagem excluindo CONCLUIDO/CANCELADO | Mesma coorte de OS |
| Conclusão documental | 100 × (FINALIZADO + RECEBIDO) / (total − NAO_SE_APLICA), % | Mesma coorte documental |
| Não conformidade das FVS | 100 × itens NC / itens C ou NC, % | Itens das FVS da coorte |
| Pedidos com entrega vencida | Não entregues com previsão atual < hoje; usa original se atual nula | Mesma coorte de pedidos |
| Destaques físicos | Até três primeiros cartões de Planejamento, quando há snapshot | Contrato de Planejamento abaixo |

Painéis: soma mensal de pedidos em R$; quantidade mensal de OS; quantidade por situação atual das OS.

Confiança: alta para contagens da coorte; limitada como visão de uma única obra. Melhorias: explicitar universos e renomear “FVS abertas” para “FVS emitidas”. A exclusão do filtro de obra para Pós-Obra está declarada na nota da página; o total global de obras também precisa ficar claro.

## 2. Projetos

Objetivo: acompanhar conclusão e pendências dos itens cadastrados. Fontes: `relatorios/views/painel.py:219–234`, `relatorios/services/analises.py:41–57`. Status e unicidade obra/item: `projetos/models/projetos.py:5–48`.

| Indicador | Fórmula / granularidade | Filtros e limitações |
| --- | --- | --- |
| Itens registrados | Contagem de respostas | Criação no período, obra |
| Finalizados / recebidos | Contagem FINALIZADO ou RECEBIDO | Mesma coorte |
| Conclusão aplicável | 100 × finalizados ou recebidos / itens diferentes de NAO_SE_APLICA | %, uma casa; vazio → — |
| Pendências registradas | Contagem excluindo FINALIZADO, RECEBIDO e NAO_SE_APLICA | Estado atual da coorte |
| Alterações de projeto | Contagem de AlteracaoProjeto | Criação no período, obra |
| Documentos críticos pendentes | Pendentes DOCUMENTAL com nome correspondente a ALVAR[AÁ], HABITE, CND, AVERBA ou CNO | Classificação por regex, não catálogo formal de criticidade |
| Pendências sem atualização há 30 dias | Pendentes com atualizado_em anterior à meia-noite de hoje−30 | Inatividade de cadastro, não atraso de entrega |
| Itens com múltiplas mudanças de status | Respostas com pelo menos dois eventos STATUS | Eventos no período e respostas criadas na coorte |

Painéis: quantidades por status; pendências por obra e grupo; críticos por nome; alterações por disciplina e mês; conclusão aplicável por obra, ordenada do menor percentual ao maior.

Confiança: alta para contagem/conclusão cadastrada; média para criticidade textual. Unicidade `(obra,item)` reduz risco de respostas duplicadas. A interseção entre criação e evento omite alterações recentes em itens antigos. Não há data-limite individual no model auditado; não inventar atraso documental.

## 3. Obras

Objetivo: qualidade registrada, aprovação, vistorias, diários e movimentos. Fontes: `relatorios/views/painel.py:238–258`, `relatorios/services/analises.py:60–93`; definições em `obras/models/fvs.py:10–18,34–45,71–109`.

| Indicador | Fórmula / unidade | Universo |
| --- | --- | --- |
| FVS abertas | Contagem de FVS | Emissão no período e obra; inclui aprovadas |
| Itens não conformes | Contagem de FVSItem resultado NC | Itens das FVS da coorte |
| Conformidade verificada | 100 × C / (C + NC), % | NA e vazio excluídos; zero denominador → — |
| Vistorias feitas | Contagem VistoriaItem status FEITO | Atualização no período e obra da atividade |
| Diários registrados | Contagem DiarioObra | Data no período e obra |
| Movimentações de saída | Contagem MovimentoEstoque tipo SAIDA | Data no período e obra de origem |
| FVS com fechamento | Contagem status APROVADA | Não verifica data_fechamento |
| Aprovadas sem devolução | APROVADA sem qualquer evento DEVOLVIDA | Histórico integral; distinct evita repetição |
| FVS aguardando aprovação | Contagem AGUARDANDO_APROVACAO | Coorte de FVS |
| Efetivo médio registrado | Média aritmética dos efetivos não nulos | Pessoas por diário; zero participa |
| Vistorias cautelares | Contagem VistoriaCautelar | Criação no período e obra |
| Ocorrências cautelares | Contagem OcorrenciaCautelar | Vinculadas à coorte de vistorias |

Painéis: FVS por status, obra, mês e executora; NC por item; taxa NC/(C+NC) por executora; vistorias por status; movimentos por tipo; frequência de registros de saída por descrição; ocorrências por manifestação; diários por obra.

Confiança: alta para C/NC atual; não representa resultado inicial nem inspeções ocorridas no período, pois não usa data_verificacao. Empresa e item em texto livre fragmentam grupos. O join por executora usa uma relação múltipla de itens; não foi demonstrada multiplicação indevida nessa consulta. Melhorias: exibir denominador/cobertura de inspeção, separar aprovação administrativa, parecer técnico e fechamento; não interpretar frequência de saída como quantidade física ou custo.

## 4. Suprimentos

Objetivo: volumes contratados, fluxo, pontualidade e diferença bruta de preços. Fontes: `relatorios/views/painel.py:262–281`, `relatorios/services/analises.py:96–155`; `compras/models/pedido.py:14–47`, `compras/models/core.py:79–83`, `compras/models/fluxo.py:104–151`, `compras/models/cotacao.py:137–160`.

| Indicador | Fórmula / unidade | Coorte e exclusões |
| --- | --- | --- |
| Pedidos emitidos | Contagem PedidoCompra | Data/obra; exclui CANCELADO |
| Total contratado | Soma valor_total, R$ | Mesmos pedidos; não é pagamento |
| Pedidos em aberto | Contagem não ENTREGUE | Mesmos pedidos |
| Entregas vencidas | Abertos com previsão atual < hoje, original se atual nula | Mesmos pedidos |
| Processos de compra | Contagem ProcessoCompra | Abertura/obra; não exclui cancelados |
| Ticket médio por pedido | Soma valor_total / quantidade, R$ | Sem pedidos retorna zero |
| Economia negociada comparável | Σ(q × preço inicial) − Σ(q × preço final), R$ | Adjudicações não canceladas das necessidades de processos da coorte |
| Economia percentual | 100 × economia / Σ(q × preço inicial), % | Somente q>0, inicial>0 e final≥0 |
| Tempo médio até contratar | Média de dias corridos entre abertura e conclusão da contratação | Somente intervalos não negativos e datas existentes |
| Entrega integral no prazo original | 100 × recebidos até prazo original / entregues com prazo original e recebido_em | %, uma casa |
| Atraso médio nas entregas tardias | Média de recebimento−prazo original, dias | Somente diferenças positivas; ausência → — |
| Reprogramações de entrega | Contagem HistoricoPrevisaoPedido | Eventos no período e pedidos da coorte |

Economia usa Decimal e exclui propostas perdedoras, mas ignora desconto_cotado, desconto_final, frete e desconto global. Os dois descontos de item existem nos models citados. O preço inicial é lido do item cotado relacionado; não foi demonstrado um snapshot imutável desse preço. A decisão é rotular explicitamente economia BRUTA, não calcular líquido sem regra de rateio validada.

Painéis: valores por mês/obra/fornecedor; quantidades por status/etapa/decisão/responsável; tempo por etapa; fornecedores com pedidos abertos atrasados/total de pedidos, mínimo três. Duração por etapa parte da última conclusão disponível ou abertura: lacuna intermediária acumula tempo na próxima etapa, não mede necessariamente duração exclusiva. Decisões de aprovação contam registros, não processos únicos.

Confiança: alta para pedidos persistidos; média para economia bruta e duração. A nota da página ainda diz que economia será adicionada, embora já seja calculada. Melhorias: corrigir nota, mostrar quantidade e base monetária comparável, sinalizar datas ausentes e universos distintos entre pedidos e processos.

## 5. Planejamento

Objetivo: comparar avanço físico e classificar marcos/contratações. Fonte: `relatorios/services/estrategicos.py:40–171`. Campos: `planejamento/models/cronograma.py:150–217`; conversão percentual: `planejamento/services/cronograma/normalizacao_csv.py:114–140`.

Usa última importação ativa CONCLUIDA; obra opcional. Fim limita data_atualizacao≤fim ou nula; início é ignorado. RESUMO GERAL seleciona maior `(data_atualizacao, semana, id)` por `(obra_id, projeto)`.

| Indicador | Regra / unidade |
| --- | --- |
| Cronogramas acompanhados | Quantidade de snapshots de resumo |
| Cronogramas atrás do previsto | Executado < previsto−0,1 ponto percentual |
| Cronogramas à frente | Executado > previsto+0,1 ponto percentual |
| Sem percentuais comparáveis | Executado ou previsto ausente |
| Avanço executado por obra | Percentual executado, com fallback de percentual_concluida |
| Desvio físico por obra | Executado−previsto, pontos percentuais; previsto tem fallback de tarefa |
| Marcos registrados | Linhas MARCOS na semana do resumo selecionado |
| Marcos concluídos | Progresso ≥0,999 na escala 0–1 |
| Marcos pendentes atrasados | Não concluídos com término-base < data_atualizacao; hoje se data nula |
| Marcos concluídos com atraso | Concluído e término_real > término_base |
| Suprimentos programados | Quantidade de itens da importação de suprimentos ativa |
| Contratações realizadas | Data real de contratação informada |
| Contratações pendentes vencidas | Sem data real e prazo-limite < hoje |
| Contratações realizadas fora do prazo | Data real > prazo-limite |

Percentuais 0–1 são multiplicados por 100 e arredondados para uma casa antes da comparação. Não há média entre obras, corretamente, sem pesos comparáveis. Painéis adicionais: situação dos marcos; pendências de contratação por obra; itens por categoria.

Confiança: média. Marco é selecionado por semana, não por identidade completa de snapshot: várias atualizações na mesma semana podem duplicá-lo; risco identificado, ocorrência não verificada. Em suprimentos, fim limita prazo-limite, mas contratação posterior ao fim conta como realizada; vencimento continua comparado a hoje. Portanto não representa posição histórica integral. Melhorias: definir referência temporal, identidade de marco/snapshot e comparar percentuais com precisão preservada.

## 6. Financeiro

Objetivo: distinguir previsão, obrigação e pagamento. Fonte: `relatorios/services/estrategicos.py:180–228`.

| Indicador | Fórmula / unidade | Filtros |
| --- | --- | --- |
| Previsão financeira ativa | Σvalor_previsto, R$ | ativa=True, data_prevista e obra |
| Pagamentos efetivados | Σvalor, R$ | EFETIVADO, data_pagamento e obra do título |
| Valor original dos títulos | Σvalor_original, R$ | Exclui CANCELADO/REJEITADO; vencimento e obra |
| Títulos vencidos | Quantidade não PAGO com vencimento < hoje | Mesmos títulos |
| Original dos títulos vencidos | Σvalor_original dos vencidos, R$ | Não é saldo líquido |

Painéis: previsão mensal; pagamento mensal; previsão por certeza. São visões distintas, não parcelas somáveis de despesa.

Regra existente: `saldo=max(original+juros+multa+outros_acrescimos−desconto−pagamento_efetivado,0)`. Evidências: `financeiro/models/titulos.py:188–230`, `financeiro/services/regras.py:18`. Pagamento é OneToOne (`financeiro/models/pagamentos.py:27–32`), sem pagamento parcial (`financeiro/services/regras.py:23–29`; `financeiro/services/pagamentos.py:10–26`).

Confiança: alta para valores originais corretamente rotulados; não substituem saldo. Recomendação: adicionar saldo aberto/vencido usando regra existente e verificar divergência entre status e pagamento. Preservar original separado. Vencimento nulo não é vencido e desaparece sob filtro de datas; expor cobertura sem vencimento.

Estornos são excluídos do pagamento atual. Reutilização do registro após estorno altera a visão retrospectiva (`financeiro/services/pagamentos.py:28–42,87–100`); não prometer fluxo histórico imutável. Séries convertem Decimal para float antes da formatação (`estrategicos.py:214–226`); manter Decimal até apresentar valores.

## 7. Pós-Obra

Objetivo: demanda, estoque atual de atendimento, prazo, experiência e material consumido. Fontes: `relatorios/views/painel.py:285–306`, `relatorios/services/analises.py:158–209`; `pos_obra/models/atendimento.py:6–40,61–100`.

Coorte por criação e empreendimento; filtro de obra não aplicado. Status/prazo refletem situação atual.

| Indicador | Fórmula / unidade | Restrições |
| --- | --- | --- |
| OS abertas no período | Contagem de todos os chamados | Coorte de abertura |
| OS não encerradas | Exclui CONCLUIDO/CANCELADO | Estado atual |
| OS concluídas | Contagem CONCLUIDO | Estado atual |
| OS com prazo vencido | Ativas com prazo < hoje | Prazo nulo não vence |
| Custo registrado de materiais | Σ(utilizado × custo_unitario), R$ | Só materiais vinculados; não inclui serviços, mão de obra ou deslocamento |
| Pesquisas respondidas | Contagem PesquisaSatisfacao | OneToOne por OS, ligada à coorte |
| Tempo médio de resolução | Média de (finalizado_em−criado_em)/86400, dias | CONCLUIDO, datas existentes, duração≥0 |
| Tempo mediano de resolução | Mediana das mesmas durações | Mesmo universo |
| OS encerradas no prazo | 100 × finalização local≤prazo / concluídas com finalização e prazo | %, uma casa |
| Abertas há mais de 30/60/90 dias | Contagens cumulativas das ativas | Implementação atual usa hoje−29/59/89 à meia-noite; corrigir conforme decisão inicial |
| Agendamentos remarcados | Agendamentos distintos com situação ou histórico REAGENDAMENTO/SUBSTITUIDO | Conta agendamentos, não eventos de remarcação |
| Possíveis grupos reincidentes | Grupos empreendimento/cliente/tipo/ambiente não vazio com ≥2 OS | Inclui canceladas; não exige solução anterior |
| Pesquisas por OS concluída | Atualmente todas pesquisadas / concluídas | Corrigir interseção do numerador com concluídas |
| Notas médias | Média atendimento, prazo e qualidade, duas casas | Escala declarada 1–5; model não impõe limite superior |
| OS por 100 unidades | 100 × quantidade de OS / quantidade_unidades | Somente obras vinculadas com unidades>0; não é proporção de unidades afetadas |

Materiais: quantidade com três casas e custo com quatro; agregado declara quatro casas e exibição duas. Validar preservação da precisão do produto conforme backend, sem impor arredondamento por item não previsto.

Painéis: volumes por mês, status, tipo, empreendimento, prioridade, categoria de problema e responsável; notas médias; resolução declarada (duplicada em dois painéis); custo por tipo; OS/100 unidades.

Confiança: alta para contagens da coorte; baixa para aging e cobertura atuais. Pesquisa em OS que deixou de estar concluída pode fazer a razão superar 100%; ocorrência real não consultada. Reincidência é apenas candidata; notas não são NPS. Melhorias prioritárias: aging por instante, cobertura consistente, n de respostas/datas elegíveis e separação de períodos de abertura e conclusão quando requerida.

## Casos de referência sintéticos para backend, BI e QA

Estes exemplos são aritmética de referência, não dados reais nem testes executados.

1. FVS: C=8, NC=2, NA=3 e vazio=1 → denominador 10; conformidade 80,0%; NC 20,0%. Sem C/NC → —.
2. Título: original 1.000, acréscimos 50, desconto 100, sem pagamento → saldo 950. Pagamento integral 950 → zero; estorno → 950. Não simular parcialidade como fluxo suportado.
3. Economia bruta: q=10, inicial=100, final=90 → base 1.000, final 900, economia 100 e 10,0%. Descontos existentes não entram nessa métrica; inicial zero torna item não comparável. Final maior que inicial produz economia negativa, sem ocultá-la.
4. Pesquisa: duas OS concluídas e três pesquisadas, sendo uma reaberta → fórmula atual 150%; cobertura das concluídas deve considerar apenas as duas pesquisas elegíveis e resultar 100%.
5. Aging: fixar instante de referência; OS com N dias exatos não entra em “mais de N”; N dias e um segundo entra; N dias menos um segundo não entra. As faixas 30/60/90 são cumulativas.
6. Planejamento: mesmo marco em duas atualizações na mesma semana deve pertencer somente ao snapshot escolhido, conforme identidade validada. Percentuais ausentes não podem virar zero.
7. Financeiro: vencimento hoje não é vencido; vencimento nulo é sem data. Pagamento estornado não reduz saldo. Títulos cancelados/rejeitados permanecem fora do universo operacional definido.
8. Joins: dois históricos de remarcação para um agendamento devem contar um agendamento; vários históricos DEVOLVIDA não devem multiplicar FVS. Rankings truncados devem informar cobertura para reconciliar totais.

## Validação, arquivos e limitações

Comandos executados nesta auditoria: `Get-Content -Encoding utf8` para serviços, views, models e regras citados; `rg -n` para localização das fórmulas e referências; `rg --files -g AGENTS.md` para instruções locais. A busca encontrou apenas AGENTS.md da raiz. Leituras pontuais com wildcard de caminho não aceito pelo rg no PowerShell foram repetidas usando diretórios/caminhos existentes.

`relatorios/tests.py` foi lido: contém apenas stub de TestCase, sem casos de teste implementados. Não foram executados testes Django, pois esta fase é leitura e não houve configuração/verificação de banco de teste isolado. Não há reconciliação com registros reais nem evidência de incidência dos riscos apontados em produção.

Este registro é o único arquivo criado pelo especialista dados: `docs/relatorios/auditoria-indicadores.md`. Nenhuma alteração de esquema foi identificada como necessária para as correções propostas. Não houve migração, deploy, edição de aplicação, .env ou credenciais.
