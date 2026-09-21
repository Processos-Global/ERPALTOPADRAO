from django.urls import path
from obras import views

app_name = "obras"
urlpatterns = [
    path("", views.fichas_tecnicas, name="menu"),
    path("fichas/", views.fichas_tecnicas, name="fichas_tecnicas"),
    path("fichas/<int:obra_id>/", views.ficha_tecnica, name="ficha_tecnica"),
    path("fichas/<int:obra_id>/acao/", views.ficha_tecnica_acao, name="ficha_tecnica_acao"),
]
