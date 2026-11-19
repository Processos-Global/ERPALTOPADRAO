# Relatório técnico — oito etapas SAARI

Data: 19/11/2026. O inventário completo de arquivos está em [RELATORIO_IMPLEMENTACAO_SAARI.md](./RELATORIO_IMPLEMENTACAO_SAARI.md). Não houve commit, push, deploy nem migração no banco padrão. O projeto permaneceu nos aplicativos Django existentes. A coordenação foi registrada em `AGENTS.md`, seis agentes em `.codex/agents/` e sete skills em `.agents/skills/`.

| Etapa | Problema e implementação | Validação e limite |
|---|---|---|
| 1. Desempenho | Consultas repetidas no estoque, painel de suprimentos e dashboard financeiro. Pré-carregamento, agregações SQL e filtros/paginação. | Testes de desempenho; fixture sintética de cinco materiais: sete para duas queries. Sem medição de tempo em produção. |
| 2. Financeiro | Cards e tabelas com filtros/datas diferentes. Agenda, compromissos sem dupla contagem, indicadores filtrados e pagamentos pelo mês efetivo. | Testes de agenda, compromissos, indicadores e mês de pagamento. |
| 3. Vistorias/Diário | Resumo ausente e atividades do diário sem vínculo estruturado. Resumo deduplicado/PDF; atividades semanais, Pré/Pós Habite-se e adicionais justificadas. | Testes dos dois fluxos; migração `obras/0018`. |
| 4. Ficha/GF | Consulta e medidas pouco estruturadas. Árvore por ambientes, medidas/material opcionais, filtros, PDF/Excel e sugestões confirmadas antes de salvar. | Testes de consulta/editor; migrações `obras/0019`, `cadastros/0016`, `compras/0037`. Nomes semelhantes de materiais não são vinculados automaticamente. |
| 5. Estoque/Compras | Necessidade não verificava saldo compatível. Cobertura por obra, reservas, revalidação e exceção auditada. | Testes de cobertura/permissão; migrações `compras/0038`, `obras/0020`, `usuarios/0012`. **Pendente:** dedução/bloqueio de pedido de outro processo exige identidade inequívoca da demanda; concorrência MySQL não ensaiada. |
| 6. Recebimento/Financeiro | Contratado, recebido, liberado e pago se confundiam. Liberações com origem/valor, candidato idempotente, título separado e compensação de antecipação. Cancelamento integral auditado de Compras agora aparece em Compromissos com saldo cancelado, recebido e pago preservados. | Testes de parcial, múltiplos recebimentos, duplicação, antecipação, legado e cancelamento integral; migração `financeiro/0014`. **Pendente:** regra para desconto/cancelamento parcial de pedido ainda ativo. |
| 7. Planejamento/GF | Comparativo temporal e relatório GF incompletos. Séries semanais/mensais reais, marcos/desvios/projeção condicionada, histórico e relatório GF em tela/PDF/Excel. | Cinco testes de cronograma e dois de relatório. Dados históricos ausentes permanecem vazios. |
| 8. SLA Compras | Prazos não configuráveis nem versionados. Regras por etapa/processo/entrega, fornecedor, categoria e material; snapshots de transição/pedido; alertas e indicadores. | Seis testes; migrações `compras/0039` e `compras/0040`. Sem calendário de feriados, vínculo confiável da data necessária à obra ou detalhamento de fabricação/transporte. |

## Migrações e dados

Migrações criadas: `cadastros/0016`, `compras/0037` a `0040`, `financeiro/0014`, `obras/0018` a `0020`, `usuarios/0012`. São aditivas; novos campos opcionais preservam registros antigos. Nenhuma foi aplicada no banco padrão. A relação de nomes completos consta no inventário.

## URLs, permissões e dependências

Novas telas: `/financeiro/agenda/`, `/financeiro/compromissos/`, `/financeiro/liberacoes/`; `/obras/vistorias/resumo/` com PDF, `/obras/fichas/consulta/` com PDF/Excel e API `/obras/diario/atividades/`; `/compras/grandes-fornecedores/relatorio/` e `/compras/prazos/regras/`. Nova ação `EXCECAO_ESTOQUE`; regras SLA exigem `ADMINISTRAR` já existente. Não foram adicionadas dependências externas.

## Verificações

- `manage.py check --settings=relatorios.test_settings`: passou.
- `manage.py test compras financeiro obras planejamento --settings=obras.test_settings_concretagem`: **167/167 passaram** em SQLite isolado.
- `manage.py test --settings=relatorios.test_settings`: **280/280 passaram** em SQLite isolado. As seis falhas anteriores foram corrigidas em Pós-Obra/Usuários; o teste da Concretagem roda com geração de ficha síncrona e mídia temporária. Relatórios exige essa configuração de testes.
- `manage.py test pos_obra usuarios relatorios --settings=relatorios.test_settings`: **112/112 passaram**. `financeiro.test_liberacoes` e `financeiro.test_compromissos`: **11/11 passaram**.
- `makemigrations --check --dry-run` no grafo real: **sem alterações detectadas** após alinhar a declaração explícita de cinco IDs com as migrações históricas. `migrate --plan` no grafo real/SQLite isolado passou. Seis TOML de agentes validados; `git diff --check` passou.

Antes de produção: revisar as migrações, testar em cópia de dados e MySQL, conferir permissões por obra, relatórios, responsividade e tema escuro. Definir a identidade de demanda para bloquear pedidos pendentes, a política de ajuste parcial de pedidos ativos e o calendário de feriados. `relatorios.zip` já estava removido antes deste trabalho. A limpeza de `__unused_test_private_media__/` foi rejeitada pela revisão automática de segurança, então esse diretório permanece.
