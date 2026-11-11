# Evolução dos relatórios SAARI — plano técnico

Data: 2026-11-11. Especificação: solicitação do usuário em seis fases, nesta sessão. Execução autorizada após auditoria e consolidação, sem commit, push ou deploy.

## Diagnóstico consolidado

Os cinco perfis reais backend, dados, bi, frontend e qa foram acionados. As auditorias iniciais são somente leitura. O inventário de fórmulas está em [auditoria-indicadores.md](auditoria-indicadores.md).

### Correções obrigatórias

- Aplicar as ações visualizar/exportar já existentes em usuários, inclusive usuário inativo; não inventar autorização adicional aos módulos-fonte.
- Validar datas e identificadores sem erro 500 e sem transformar seleção inválida em consolidado. Cadastro de empreendimento sem OS deve resultar em consulta vazia.
- Exibir saldo financeiro líquido e vencido conforme a regra existente, mantendo previsão, original e pagamento separados. Pagamento é singular e integral; estorno não reduz saldo.
- Corrigir faixas de idade de OS para mais de N dias completos e cobertura de pesquisas para o mesmo conjunto de OS concluídas.
- Preservar precisão antes da comparação física; distinguir ponto percentual de percentual e não perder o sinal negativo.
- Transportar valores numéricos explícitos aos gráficos, inclusive dias, taxas e notas; ausência permanece nula. Corrigir URL ECharts.

### Melhorias de indicadores

- Geral: priorizar riscos documentais, qualidade, entregas, atendimento e desvio físico, com universos explícitos e obra aplicada quando houver vínculo real.
- Projetos: priorizar conclusão e pendências; mostrar base dos percentuais e identificar critério textual de documentos críticos, sem inventar prazos.
- Obras: mostrar amostra avaliada e ausência de resultados; distinguir FVS emitida, aprovada e fechamento. Manter conformidade C/(C+NC).
- Suprimentos: economia explicitamente bruta de preços unitários adjudicados; não presumir economia líquida com rateio de descontos. Identificar amostra, preservar variação negativa, não fundir fornecedores homônimos. Durações só com extremos consecutivos válidos.
- Planejamento: comparação previsto/executado por obra e projeto, desvio em p.p., snapshot de marcos consistente e evolução temporal dos resumos armazenados sem criar história ausente. Explicitar que suprimentos por prazo e situação atual não são fotografia histórica.
- Financeiro: saldo aberto, saldo vencido, obrigações líquidas e sinais de inconsistência sem mudar regras financeiras.
- Pós-Obra: cobertura e amostra da satisfação, tempo médio/mediano, idade e reincidência candidata; materiais continuam separados de custo total inexistente. Remover painel duplicado de resolução.

### Melhorias visuais

Preservar marrom/bege/dourado, fontes, cards, navegação horizontal, filtros e ECharts. Compactar espaços, tirar destaque automático do primeiro gráfico, corrigir contraste escuro. Exibir metodologia apenas em detalhe curto expansível. Sem busca, subtítulos decorativos ou redesign.

### Otimizações técnicas

Consolidar agregações repetidas; evitar calcular todos os painéis de planejamento para cards da visão geral. Unificar limites temporais seguros. Identificar truncamento/exportação resumida. Metadados do gráfico definidos no produtor, sem inferência por título, texto formatado ou número de linhas. Não há N+1 comprovado que justifique prefetch indiscriminado.

### Dependências futuras

Não implementar custo total de pós-obra, atraso documental sem data-limite, economia líquida sem regra validada de rateio, erro histórico de previsão sem snapshots, média física de portfólio sem pesos ou isolamento por empresa sem contrato de domínio. Compatibilidade MySQL e reconciliação com dados reais exigem ambiente próprio, sem produção.

## Contrato de apresentação

Cada painel mantém `title`, `caption`, `rows`, `kind`. Cada linha contém `label`, `value` (texto), `raw` (número ou null), `width` apenas para fallback. O campo `chart` é um objeto explícito com `type` (bar/line/scatter), `orientation` (horizontal/vertical), `unit` (count/currency/percent/percentage_point/days/score/rate), `precision`, `min`, `max`, `sort` (source/asc/desc/chronological), `negative` (boolean), `allowed_types`. Opcional `series`: lista de `{name, values}` alinhada a rows para comparações. JSON deve ser emitido por `json_script`, sem parsing de números formatados no cliente.

Percentuais: escala 0–100; notas: 1–5; p.p.: zero e sinais preservados; taxas por 100 unidades sem teto artificial; moeda: precisão 2; ausências nulas. Ordenação é decidida no produtor, não pelo título. Cards podem receber `severity` explícita, somente para risco demonstrado por valor >0, sem limiares inventados.

Complemento de integração: `_render` fornece `pode_exportar` boolean pela ação existente. Para painéis com múltiplas séries, cada linha fornece `series_values`, lista de textos formatados alinhada a `panel.series`, permitindo tabela completa mesmo sem JavaScript. O backend mantém os números em `series[].values`.

## Responsabilidades e sequência

1. QA cria settings independentes e testes de regressão em `relatorios/tests.py` e `relatorios/test_settings.py`. Nenhum import de config.settings, .env ou conexão real. Registrar falhas prévias antes das correções.
2. Backend é o único editor de `relatorios/views/painel.py` e `relatorios/services/` durante implementação. Corrige cálculos, filtros, permissões e produz contrato acima. Não modifica models, migrations ou outros módulos.
3. Frontend é o único editor de `templates/relatorios/` e `static/relatorios/`. Integra contrato, compacta apresentação e valida JavaScript. Não muda templates base, Compras ou Planejamento.
4. Dados revisa fórmulas corrigidas; BI revisa contrato e gráficos; QA revisa o diff e executa verificações. Correções retornam ao responsável do arquivo.
5. Coordenador consolida evidências, revisa escopo/Git e registra testes e limitações.

## Validação

- Títulos: original 1000, acréscimos 50, desconto 100 → saldo 950; pagamento efetivado integral → 0; estornado → 950; sem saldo negativo.
- FVS: C=8, NC=2, NA=3, vazio=1 → conformidade 80%, amostra 10.
- Pesquisas: duas concluídas e pesquisa em OS reaberta não elevam cobertura acima de 100%.
- Fronteiras exatas 30/60/90 dias, datas invertidas/inválidas/extremas, virada local do mês, IDs Unicode e inexistentes, obra/empreendimento sem dados.
- Permissões visualizar/exportar, superusuário e inativo; proteção CSV contra fórmulas.
- Todos os sete endpoints sem dados e com fixtures sintéticas, carregamento de templates, JSON numérico e negativos, ausência distinta de zero, comparação temporal e notas.
- `manage.py check --settings=relatorios.test_settings` e `manage.py test relatorios --settings=relatorios.test_settings`, com SQLite em memória, nenhuma migração executada e nenhuma configuração de produção carregada. Schemas de teste podem ser criados somente no banco efêmero.
- Verificação JavaScript e visual quando ferramentas permitirem; não alegar validação de navegador ou MySQL sem executá-la.

## Estado

Auditorias dos cinco especialistas concluídas antes da implementação. QA confirmou Python 3.14.4, Django 6.0.7 e SQLite 3.50.4 por imports isolados. Plano registrado para execução autorizada. Testes e resultados finais serão documentados em [validacao.md](validacao.md).
