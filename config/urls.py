from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),

    path("", include("core.urls")),
    path("usuarios/", include("usuarios.urls")),
    path("obras/", include("obras.urls")),
    path("planejamento/", include("planejamento.urls")),
    path("suprimentos/", include("suprimentos.urls")),
    path("compras/", include("compras.urls")),
    path("contratos/", include("contratos.urls")),
    path("financeiro/", include("financeiro.urls")),
    path("almoxarifado/", include("almoxarifado.urls")),
    path("projetos/", include("projetos.urls")),
    path("vistorias/", include("vistorias.urls")),
    path("diario-obra/", include("diario_obra.urls")),
    path("pos-obra/", include("pos_obra.urls")),
    path("relatorios/", include("relatorios.urls")),
    path("integracoes/", include("integracoes.urls")),
    path("cadastros/", include("cadastros.urls")),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )