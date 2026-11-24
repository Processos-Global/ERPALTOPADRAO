# Checklist de validação

| Etapa | Situação | Evidência e pendências |
| --- | --- | --- |
| 0. Auditoria | Implementado | Inspeção inicial, suíte de referência e sete cenários de medição. A cobertura estática concentrou-se nos pontos de entrada mais críticos. |
| 1. Desempenho global | Parcialmente implementado | Paginação real em Compras, Diário e Projetos. Consultas e conteúdo seletivos nos cronogramas e Ficha Técnica. Busca assíncrona no material da consulta da ficha. O dashboard de Compras agrega no banco e limita os cartões. Outros seletores extensos, cache e revisão exaustiva de planos SQL permanecem pendentes. |
| 2. Redesign | Parcialmente implementado | Textos e cabeçalhos condensados em Cadastros, Diário, Vistorias, Projetos e Pós-Obra. Planejamento e Ficha Técnica usam navegação por seções. Padronização integral de formulários, tabelas, filtros e temas depende de revisão visual. |
| 3. Transições e downloads | Implementado nos fluxos revisados | Indicador localizado no filtro de Suprimentos e de Ordens de Serviço, opt-out de downloads, recuperação no retorno do histórico. O filtro de Suprimentos da revisão inicial não oferece exportação. |
| 4. Vistorias | Implementado | Consolidação por obra, detalhe de pendências sob demanda e PDF com o mesmo serviço de filtros e totais. Permissões e PDF com regressão. |
| 5. Diário de Obra | Implementado | Semana da data do diário, recorte por obra e importação ativa, grupos Pré e Pós Habite-se e grupo complementar quando aplicável. Seleções existentes permanecem no formulário. Textos manuais legados podem ser consultados no histórico. |
| 6. Almoxarifado | Parcialmente implementado | Resumo por necessidade distingue físico, reservado, disponível, compra, pendência e recebimento. Bloqueio e exceção auditada reaproveitam o fluxo existente. A concorrência continua pendente em MySQL. |
| 7. Obras e Ficha Técnica | Parcialmente implementado | Abas e consulta por ambiente evitam consultas de itens fora do detalhamento. Busca de materiais sob demanda, exportações filtradas, medidas, sugestões e integração com a matriz validadas. Outros dropdowns da ficha ainda precisam da mesma revisão. |
| 8. Suprimentos | Parcialmente implementado | Detalhe comercial por item sob demanda, histórico existente, filtros e previsões preservados. Relatório de Grandes Fornecedores separa solicitado e contratado, com responsável quando disponível. As demais etapas de valor no histórico do suprimento ainda dependem de rastreabilidade por fonte. |
| 9. Cronograma Físico | Parcialmente implementado | Abas calculam e exibem somente a área selecionada. Intervalos oficiais aparecem quando disponíveis. Avanço incremental e previsão existentes têm testes. Marcos exibem futuro, no prazo, atraso e adiantamento conforme as datas do retrato. Revisão visual dos gráficos permanece pendente. |
| 10. Compras | Parcialmente implementado | Paginação e cálculo de SLA otimizados, histórico, pedidos e anexos sob demanda, vínculo oficial por necessidade e acompanhamento de cobertura. Demais abas do detalhe ainda requerem revisão. A data necessária na obra segue indefinida até existir fonte oficial. |
| 11. Demais módulos | Parcialmente implementado | Projetos, Cadastros, Pós-Obra e relatórios receberam melhorias pontuais. A revisão visual e de volume de cada tela permanece pendente. |
| 12. Testes | Parcialmente implementado | Suíte em SQLite isolado, consultas e templates exercitados, verificações de sintaxe e migrações. MySQL de homologação e capturas desktop, mobile, claro e escuro permanecem pendentes. |
| 13. Documentação | Implementado | Auditoria, inventário, desempenho, checklist, testes e comandos de publicação. |

A revisão do Financeiro fica fora do escopo desta entrega. O layout compartilhado mantém o fluxo de download específico do módulo.
