# Financeiro Alto Padrão — instalação

Este pacote foi construído sobre os apps enviados em 03/09/2026 e pressupõe os mesmos nomes de apps/models (`compras`, `cadastros`, `planejamento`, `usuarios`, `obras`).

## 1. INSTALLED_APPS

No `settings.py` do projeto, adicione:

```python
"financeiro.apps.FinanceiroConfig",
```

## 2. URLs raiz

No `urls.py` principal do projeto, importe `include` e adicione:

```python
path("financeiro/", include("financeiro.urls")),
```

## 3. Migrations

```bash
python manage.py migrate usuarios
python manage.py migrate financeiro
```

## 4. Plano financeiro inicial

```bash
python manage.py inicializar_financeiro
```

O comando é idempotente: não apaga nem duplica contas existentes pelo código.

## 5. Sincronização inicial

Depois das migrations, para importar pedidos/parcelas e recebimentos já existentes:

```bash
python manage.py sincronizar_financeiro
```

A partir daí, os signals do app mantêm novas parcelas de pedidos, pedidos e recebimentos sincronizados.

## 6. Permissões

Abra **Usuários e permissões** e ative o módulo Financeiro para os usuários necessários. As ações granulares são:

- Visualizar Financeiro
- Lançar títulos
- Editar títulos
- Aprovar pagamentos
- Programar pagamentos
- Registrar pagamentos
- Gerenciar bancos
- Conciliar movimentações
- Administrar Financeiro

## 7. Primeira configuração operacional

1. Cadastre ao menos uma conta bancária.
2. Rode `inicializar_financeiro` ou configure o plano manualmente.
3. Configure as alçadas financeiras.
4. Cadastre despesas recorrentes, se houver.
5. Rode `sincronizar_financeiro` uma vez para trazer o histórico operacional atual.

## Regras principais implementadas

- Pedido/parcelas geram **previsões**, não contas a pagar definitivas.
- Recebimento com NF e valor gera/atualiza um **título em conferência**.
- Pedido, recebimento e NF permanecem vinculados ao título.
- Alteração relevante depois da aprovação invalida o ciclo anterior.
- Alçadas são sequenciais por `ordem`; cada regra passa a ser obrigatória a partir de `valor_minimo`.
- Regra específica da obra substitui a regra global da mesma ordem.
- Só título aprovado pode ser programado/pago.
- Pagamento parcial mantém saldo em aberto.
- Juros, multa, descontos e acréscimos nunca sobrescrevem o valor original.
- Pagamento efetivado gera movimentação bancária de débito.
- Estorno remove a movimentação bancária e reabre o saldo do título.
- Fluxo de caixa usa títulos + previsões ainda não convertidas, evitando dupla contagem.
