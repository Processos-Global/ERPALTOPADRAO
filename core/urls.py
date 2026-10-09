from django.urls import path

from core import views
from core.views.arquivos import arquivo_publico


app_name = "core"


urlpatterns = [
    path("saari-arquivos/publico/<path:caminho>", arquivo_publico, name="arquivo_publico"),
    path(
        "",
        views.index_view,
        name="index",
    ),
]