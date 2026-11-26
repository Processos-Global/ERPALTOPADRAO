# Regras de negócio

## Compras e estoque

A quantidade solicitada é registrada em `quantidade_necessaria`. A quantidade a cotar é registrada em `quantidade_incluida`. Na abertura e na inclusão, o valor comercial usa a quantidade solicitada quando o operador deixa o campo em branco. O operador pode informar um valor positivo menor e pode revisar a quantidade comercial na cotação enquanto o item estiver editável. O limite continua sendo a quantidade solicitada, com até quatro casas decimais. A cotação, as adjudicações, os pedidos e os recebimentos mantêm as validações comerciais e os vínculos existentes.

O saldo exibido é físico e corresponde à obra, ao ID exato do material e à unidade cadastrada. O cálculo soma os itens de recebimento e as transferências de entrada, descontando saídas e transferências de saída. Estoque zero é um resultado válido. Falhas de consulta são apresentadas como indisponibilidade. A consulta é informativa e as aprovações comerciais e a emissão do pedido independem do saldo.

Saídas e transferências são registradas no Almoxarifado conforme o saldo físico disponível. Reservas e movimentos históricos continuam consultáveis pelo registro original. Uma necessidade em cotação que tenha reserva histórica pode ser arquivada com estado cancelado, preservando as relações.

## Financeiro

- O pedido normal entra em Compromissos na emissão. O recebimento registra os itens efetivos no estoque e cria a solicitação financeira vinculada à nota. Cada recebimento é apurado separadamente, inclusive no parcelamento.
- A solicitação considera o valor fiscal reconciliado e a compensação de antecipações aplicável. O valor esperado usa quantidades efetivas, preços e descontos aprovados, com ajustes de frete. A diferença é documentado menos esperado. O percentual usa o esperado como denominador e fica em branco quando ele é zero. A moeda é BRL, apurada em `Decimal` e arredondada em centavos.
- Nota ausente ou inconsistente requer correção documental. A correção pode ser feita no recebimento, mantendo itens e quantidades já registrados. Diferença comercial com documentação válida fica disponível para avaliação financeira. A aprovação individual registra ciência e justificativa. A ação em lote verifica o ciclo e rejeita esse tipo de divergência.
- A nota aceita vencimento informado no recebimento. Parcelas com data conhecida preservam as condições existentes. Títulos sem vencimento ou apropriação ficam disponíveis para configuração. O envio e a aprovação usam o ciclo vigente.
- Pagamentos e programação exigem título aprovado, saldo positivo e decisão vigente quando o título possui ciclo. Registros históricos aprovados sem ciclo continuam compatíveis com a confirmação autorizada. O malote verifica a aprovação vigente e agrupa títulos de uma obra por emissão. Obrigações sem obra formam uma emissão própria. Emitir registra o arquivo e os valores, e a confirmação de pagamento continua sendo uma operação separada.
- O Planejamento mostra contratado, recebido, aguardando aprovação, aprovado a pagar e efetivamente pago. A projeção usa datas comerciais identificáveis e distribui o saldo residual entre as parcelas, deduzindo o maior valor já reconhecido em títulos, recebimentos ou pagamentos. Os indicadores existentes de pagamentos usam a data de efetivação. Estornos retiram o pagamento efetivo e recuperam o saldo conforme o fluxo anterior.
