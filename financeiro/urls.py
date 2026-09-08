from django.urls import path

from financeiro import views

app_name = "financeiro"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("contas-a-pagar/", views.titulos_lista, name="titulos"),
    path("contas-a-pagar/novo/", views.titulo_novo, name="titulo_novo"),
    path("contas-a-pagar/<int:pk>/", views.titulo_detalhe, name="titulo_detalhe"),
    path("contas-a-pagar/<int:pk>/editar/", views.titulo_editar, name="titulo_editar"),
    path("contas-a-pagar/<int:pk>/enviar-aprovacao/", views.titulo_enviar_aprovacao, name="titulo_enviar_aprovacao"),
    path("contas-a-pagar/<int:pk>/decidir/", views.titulo_decidir, name="titulo_decidir"),
    path("contas-a-pagar/<int:pk>/cancelar/", views.titulo_cancelar, name="titulo_cancelar"),
    path("aprovacoes/", views.aprovacoes_lista, name="aprovacoes"),
    path("aprovacoes/lote/", views.aprovacoes_lote, name="aprovacoes_lote"),
    path("previsoes/", views.previsoes_lista, name="previsoes"),
    path("previsoes/nova/", views.previsao_nova, name="previsao_nova"),
    path("previsoes/sincronizar/", views.sincronizar_compras, name="sincronizar_previsoes"),
    path("pagamentos/", views.pagamentos_lista, name="pagamentos"),
    path("pagamentos/titulo/<int:titulo_id>/novo/", views.pagamento_novo, name="pagamento_novo"),
    path("pagamentos/<int:pk>/estornar/", views.pagamento_estornar, name="pagamento_estornar"),
    path("gastos/", views.gastos, name="gastos"),
    path("configuracoes/plano-financeiro/", views.plano_financeiro, name="plano_financeiro"),
    path("configuracoes/plano-financeiro/<int:pk>/", views.plano_financeiro, name="plano_financeiro_editar"),
    path("configuracoes/despesas-recorrentes/", views.despesas_recorrentes, name="despesas_recorrentes"),
    path("configuracoes/despesas-recorrentes/<int:pk>/", views.despesas_recorrentes, name="despesa_recorrente_editar"),
]
