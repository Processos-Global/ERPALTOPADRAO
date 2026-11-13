from django.urls import path

from . import views

app_name = "projetos"

urlpatterns = [
    path("", views.menu_projetos, name="menu"),
    path("checklist-compatibilizacao/", views.checklist_compatibilizacao, name="checklist_compatibilizacao"),
    path("checklist-documental/", views.checklist_documental, name="checklist_documental"),
    path("checklist/salvar/", views.checklist_salvar_celula, name="checklist_salvar_celula"),
    path("checklist/historico/<int:obra_id>/<int:item_id>/", views.checklist_historico, name="checklist_historico"),
    path("alteracoes/", views.alteracoes_projeto, name="alteracoes"),
]
