# Frete de Compras e reconciliação

O total contratado usa os itens e descontos adjudicados, com o frete da proposta ou da condição negociada do respectivo fornecedor. O pedido grava subtotal, descontos, frete e valor total. Emissão parcelada distribui centavos sobre o total contratado. Para R$ 1.150,00 em três parcelas, os títulos somam R$ 383,33, R$ 383,33 e R$ 383,34. O teste verifica que o título integral transitório deixou de ser criado e que repetir a emissão mantém as mesmas obrigações.

O recebimento parcial reconhece os itens documentados. Frete discriminado na própria NF é registrado separadamente e comparado ao saldo de frete do pedido, sob bloqueio transacional. Um pedido de R$ 1.100,00 com R$ 1.000,00 de materiais e R$ 100,00 de frete pode ter um recebimento de R$ 800,00 e outro de R$ 200,00 mais os R$ 100,00 já evidenciados. O título da liberação usa o valor autorizado após a compensação de antecipações. Diferença de NF sem evidência fica para conferência. Grandes Fornecedores usa o mesmo registro de frete da nota.

Ao cancelar, os compromissos distinguem saldo de materiais cancelado, pagamentos efetivados e frete ainda sujeito à conferência. A operação não reinterpreta documentos ou fretes históricos. Frete devido a transportadora distinta, rateio de uma mesma cobrança entre pedidos, vencimento independente e tratamento no encerramento parcial precisam de vínculo e regra comercial aprovados.

```bash
python manage.py diagnosticar_frete_compras --somente-divergencias
```

O CSV usa os vínculos efetivos entre pedido, recebimento, parcela, previsão e título. Uma diferença negativa pode refletir liberações ainda pendentes. O diagnóstico não altera valores e não considera toda diferença uma duplicidade. Os comandos e a emissão financeira foram testados com dados sintéticos.
