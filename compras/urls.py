from django.urls import path
from compras import views

app_name = "compras"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("processos/", views.lista_processos, name="lista_processos"),
    path("processos/novo/", views.novo_processo, name="novo_processo"),
    path("processos/<int:pk>/", views.detalhe_processo, name="detalhe_processo"),
    path("processos/<int:pk>/necessidades/incluir/", views.acao_incluir_necessidade, name="incluir_necessidade"),
    path("processos/<int:pk>/fornecedores/criar/", views.acao_criar_fornecedor, name="criar_fornecedor"),
    path("processos/<int:pk>/cotacoes/incluir/", views.acao_incluir_cotacao, name="incluir_cotacao"),
    path("processos/<int:pk>/cotacoes/item/incluir/", views.acao_incluir_item_cotacao, name="incluir_item_cotacao"),
    path("processos/<int:pk>/cotacao/concluir/", views.acao_concluir_cotacao, name="concluir_cotacao"),
    path("processos/<int:pk>/compatibilizacao/registrar/", views.acao_compatibilizar, name="compatibilizar"),
    path("processos/<int:pk>/compatibilizacao/concluir/", views.acao_concluir_compatibilizacao, name="concluir_compatibilizacao"),
    path("processos/<int:pk>/negociacao/registrar/", views.acao_negociar, name="negociar"),
    path("processos/<int:pk>/adjudicacao/registrar/", views.acao_adjudicar, name="adjudicar"),
    path("processos/<int:pk>/adjudicacoes/<int:adjudicacao_id>/cancelar/", views.acao_cancelar_adjudicacao, name="cancelar_adjudicacao"),
    path("processos/<int:pk>/negociacao/concluir/", views.acao_concluir_negociacao, name="concluir_negociacao"),
    path("processos/<int:pk>/aprovacao/decidir/", views.acao_aprovar, name="aprovar"),
    path("processos/<int:pk>/contratacao/formalizar/", views.acao_formalizar, name="formalizar"),
    path("processos/<int:pk>/pedidos/gerar/", views.acao_gerar_pedidos, name="gerar_pedidos"),
    path("pedidos/", views.lista_pedidos, name="lista_pedidos"),
]
