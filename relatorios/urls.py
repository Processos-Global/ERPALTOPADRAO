from django.urls import path
from .views import painel

app_name = "relatorios"
urlpatterns = [
    path("", painel.visao_geral, name="indicadores"),
    path("projetos/", painel.projetos, name="projetos"),
    path("obras/", painel.obras, name="obras"),
    path("suprimentos/", painel.suprimentos, name="suprimentos"),
    path("planejamento/", painel.planejamento, name="planejamento"),
    path("financeiro/", painel.financeiro, name="financeiro"),
    path("pos-obra/", painel.pos_obra, name="pos_obra"),
]
