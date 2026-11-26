# Checklist de validação

| Área | Situação | Conferência |
| --- | --- | --- |
| Ambiente | Validado em QA | SQLite em memória e MySQL descartável com `America/Sao_Paulo` e conversão histórica. Confirmar as tabelas de fuso no MySQL hospedado. |
| Esquema | Validado em QA | Diagnósticos de documento de fornecedor e contratação ativa, quatro migrations incrementais e índice completo de Suprimentos. Rodar diagnósticos no recorte autorizado antes de publicar. |
| Solicitação avulsa | Implementado | Reenvio, concorrência, chave por usuário, valores iguais legítimos, parcelas, código FIN, rollback, anexos e notificação interna. |
| Pagamentos | Implementado | Ciclo vigente, programação separada, pacote imutável, efetivação e estorno. Definir retorno operacional de Grande Fornecedor após estorno. |
| Frete e valores históricos | Implementado nos fluxos documentados | Parcelas, recebimento parcial, nota com frete, antecipação, cancelamento e Grandes Fornecedores. Transportadora distinta exige decisão de negócio. |
| Planejamento Financeiro | Implementado | Conferir recortes de período e obra, datas de emissão/liberação e previsão formalizada. Os valores das diferentes etapas são apresentados separadamente. |
| Escopo e permissões | Validado por módulo e ação | Portal e arquivos privados têm testes. Autorização de usuários internos por obra depende de política de negócio. |
| Compras e Almoxarifado | Implementado | Conferir Kanban, histórico sob demanda, SLA, prazos por fonte, reserva/consumo, transferências e revalidação de compra. |
| Diário, Ficha Técnica e Vistorias | Implementado | Semana do cronograma da obra, catálogos e detalhe sob demanda, confirmação de sugestões, histórico e PDF. |
| Cronogramas | Implementado | Revisar dados da importação, previsto/realizado, curvas, intervalos e etapas comerciais. A data necessária é parâmetro explícito do item. |
| Cadastros e Pós-Obra | Implementado | Paginação, filtro, permissão e contagem consolidada do Kanban. |
| Testes e navegador | Evidências anexadas aos relatórios | Verificar matriz, downloads e limitações em [Relatório de testes](RELATORIO_TESTES.md). |
| Publicação | Aguardando autorização | Seguir [procedimento de publicação e recuperação](INSTRUCOES_DEPLOY.md). |

Na homologação com o perfil da equipe, simule um lançamento com três parcelas, repita o POST, aprove uma parcela, emita um pacote e efetive o pagamento. Faça um estorno com justificativa e compare os relatórios. Com um pedido de R$ 1.100,00, autorize apenas R$ 800,00 no primeiro recebimento. Confirme que o restante segue sujeito ao recebimento e às condições contratuais. Confira os arquivos com um perfil autorizado e outro sem permissão.
