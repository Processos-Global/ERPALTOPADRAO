# Auditoria financeira do SAARI

Base `94dc49c`, com as melhorias gerais da árvore de trabalho. A linha de base do app Financeiro passou em 18 testes com Django 6.0.7 e SQLite em memória. Os cenários são sintéticos e usam moeda BRL, com precisão de centavos. Os valores deste documento servem para reconciliação técnica.

## Entidades e origens

| Entidade | Origem e relação | Regra encontrada |
| --- | --- | --- |
| `TituloPagar` | Beneficiário, obra, plano financeiro e vínculos opcionais ao pedido, recebimento e previsão | Uma obrigação por registro. O número FIN é único. O status financeiro e a conferência documental têm campos próprios. |
| `Pagamento` | Vínculo um-para-um com `TituloPagar` | Pagamento integral, com data efetiva própria. O estorno reabre o título. A implantação anterior reutiliza a linha ao confirmar de novo. |
| `AprovacaoTituloFinanceiro` | Decisões por título e ciclo com restrição de unicidade | Aprovar muda o status do título existente. Alterações críticas previstas na edição podem reabrir um ciclo. |
| `PrevisaoFinanceira` | Manual, recorrência e registros integrados legados | As previsões de origem `COMPRA` ficam fora das projeções somadas às contas a pagar. Outras origens com eventual vínculo explícito de conversão precisam ser verificadas antes da soma. |
| `LiberacaoFinanceiraPedido` | Pedido, recebimento quando aplicável e título quando gerado | O total contratado do pedido, o valor documentado, as antecipações compensadas, o valor liberado e o pagamento representam etapas diferentes. |
| `RelatorioPagamento` e `ItemRelatorioPagamento` | Pacote emitido de contas aprovadas, com dados congelados por item | Emissão reserva uma decisão de aprovação e registra informações para pagamento. A confirmação de pagamento é uma operação própria. |

## Caminhos de criação

1. A solicitação avulsa chama `financeiro/services/titulos.py`. Cria uma obrigação por parcela em `AGUARDANDO_APROVACAO`. O POST antigo criava um novo grupo a cada chamada, inclusive em reenvios idênticos. Anexos e notificações eram processados em seguida pela view.
2. `financeiro/signals.py` sincroniza `PedidoCompra`, `ParcelaPrevistaPedido`, `GrandeFornecedorProcesso`, parcelas de grande fornecedor e seus rateios. `financeiro/services/previsoes.py` centraliza a montagem e atualização dos títulos integrados por referência externa. A API em `financeiro/services/integracoes.py` também expõe o caminho de mão de obra. Os comandos de sincronização existentes reutilizam esses serviços.
3. `financeiro/services/liberacoes.py` avalia recebimentos e condições e gera título para o saldo autorizado aplicável. Uma liberação compensada integralmente por antecipação fica no histórico da operação.
4. A página de previsões manuais e a geração de recorrências gravam `PrevisaoFinanceira`. Os relatórios de pagamento e os estornos atuam sobre obrigações existentes.

## Valores e datas

- Líquido do título = máximo entre zero e o original acrescido de juros, multa e outros acréscimos, já descontado o desconto do título. Saldo em aberto desconta o pagamento `EFETIVADO` e tem piso zero. Pagamento estornado vale zero na soma efetivada.
- A criação avulsa de R$ 100,00 em três parcelas de 30 dias distribui R$ 33,34, R$ 33,33 e R$ 33,33. A regra preexistente divide o bruto. Cada parcela tem vencimento e aprovação próprios. Ajustes manuais de juros, multa, desconto e acréscimos são atualmente copiados e precisam de acordo operacional se passarem a significar totais do grupo.
- Em Compras, a adjudicação separa os fornecedores. `PedidoCompra.valor_total` é o valor armazenado, a partir dos itens, descontos e frete da respectiva condição comercial. A sincronização usa o total do pedido único ou as parcelas previstas. Recebimentos parciais têm evidência fiscal própria.
- O painel anterior agrupava somente quatro origens. Os títulos legados de contrato, medição, despesa, imposto, adiantamento, reembolso, folha e outros continuam válidos. A agenda seleciona obrigações por vencimento e usa data efetiva para o total pago no período. Projeções futuras precisam de janela identificada.

## Controles e decisões em aberto

- Autorizações financeiras têm permissão ativa de módulo e ações `VISUALIZAR`, `LANCAR_TITULOS`, `EDITAR_TITULOS`, `APROVAR`, `PAGAR` e `ADMINISTRAR`, com fallback legado. O portal de clientes tem bloqueio próprio. O modelo atual não oferece atribuição de obras para usuários internos do Financeiro. A definição de obras por usuário, inclusive o tratamento de títulos legados sem obra, depende de regra de negócio.
- Pagamentos parciais exigem uma regra explícita para saldo, descontos, juros, estornos, reaproveitamento de comprovantes e sincronização com Compras antes de mudar o vínculo `OneToOneField`.
- Frete a transportadora distinta, rateio livre entre pedidos e alterações de frete em encerramentos parciais dependem de condição contratual ou evidência fiscal identificada. Valores antigos sem essa informação ficam para diagnóstico.
