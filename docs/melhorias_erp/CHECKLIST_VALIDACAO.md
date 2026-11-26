# Checklist de validação

| Etapa | Situação | Evidência e pendências |
| --- | --- | --- |
| 0. Auditoria | Implementado | Inspeção inicial, suíte de referência e sete cenários de medição. A cobertura estática concentrou-se nos pontos de entrada mais críticos. |
| 1. Desempenho global | Parcialmente implementado | Paginação real em Compras, Diário e Projetos. Consultas e conteúdo seletivos nos cronogramas e Ficha Técnica. Busca assíncrona no material da consulta da ficha. O dashboard de Compras agrega no banco e limita os cartões. Outros seletores extensos, cache e revisão exaustiva de planos SQL permanecem pendentes. |
| 2. Redesign | Validado nas telas revisadas | Textos e cabeçalhos condensados em Cadastros, Diário, Vistorias, Projetos e Pós-Obra. Planejamento e Ficha Técnica usam navegação por seções. O Edge validou claro, escuro e três tamanhos de tela. |
| 3. Transições e downloads | Implementado nos fluxos revisados | Indicador localizado no filtro de Suprimentos e de Ordens de Serviço, opt-out de downloads, recuperação no retorno do histórico. O filtro de Suprimentos da revisão inicial não oferece exportação. |
| 4. Vistorias | Implementado | Consolidação por obra, detalhe de pendências sob demanda e PDF com o mesmo serviço de filtros e totais. Permissões e PDF com regressão. |
| 5. Diário de Obra | Implementado | Semana da data do diário, recorte por obra e importação ativa, grupos Pré e Pós Habite-se e grupo complementar quando aplicável. Seleções existentes permanecem no formulário. Textos manuais legados podem ser consultados no histórico. |
| 6. Almoxarifado | Validado em QA | Resumo por necessidade distingue físico, reservado, disponível, compra, pendência e recebimento. Bloqueio e exceção auditada reaproveitam o fluxo existente. O MySQL descartável validou a concorrência por material e obra. |
| 7. Obras e Ficha Técnica | Parcialmente implementado | Abas e consulta por ambiente evitam consultas de itens fora do detalhamento. Busca de materiais sob demanda, exportações filtradas, medidas, sugestões e integração com a matriz validadas. Outros dropdowns da ficha ainda precisam da mesma revisão. |
| 8. Suprimentos | Parcialmente implementado | Detalhe comercial por item sob demanda, histórico existente, filtros e previsões preservados. Relatório de Grandes Fornecedores separa solicitado e contratado, com responsável quando disponível. As demais etapas de valor no histórico do suprimento ainda dependem de rastreabilidade por fonte. |
| 9. Cronograma Físico | Validado nas telas revisadas | Abas calculam e exibem somente a área selecionada. Intervalos oficiais aparecem quando disponíveis. Avanço incremental, previsão e marcos conforme as datas do retrato têm testes. As telas do cronograma integram a matriz visual. |
| 10. Compras | Validado nos fluxos revisados | Paginação e cálculo de SLA otimizados, histórico, pedidos e anexos sob demanda, vínculo oficial por necessidade e acompanhamento de cobertura. A data necessária na obra tem campo próprio no item de Suprimentos e depende de preenchimento. |
| 11. Demais módulos | Validado nas telas revisadas | Projetos, Cadastros, Pós-Obra e relatórios receberam melhorias pontuais. A matriz visual inclui Cadastros, Pós-Obra e Portal do Cliente. A medição de volume foi feita nos cenários documentados. |
| 12. Testes | Validado em QA | Suíte completa em SQLite em memória e MySQL descartável com as migrations reais. Capturas e testes de interação em Edge, em desktop, tablet e celular. |
| 13. Documentação | Implementado | Auditoria, inventário, desempenho, checklist, testes e comandos de publicação. |

O Financeiro passou a integrar a reestruturação global. A homologação operacional segue os documentos da retomada. [Checklist](../reestruturacao_financeiro/CHECKLIST_VALIDACAO.md) · [Testes](../reestruturacao_financeiro/RELATORIO_TESTES.md) · [Publicação](../reestruturacao_financeiro/INSTRUCOES_DEPLOY.md)
