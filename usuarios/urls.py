from django.urls import path
from usuarios import views

app_name = "usuarios"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("notificacoes/", views.lista_notificacoes, name="notificacoes"),
    path("notificacoes/marcar-todas-lidas/", views.marcar_todas_notificacoes_lidas, name="marcar_todas_notificacoes_lidas"),
    path("notificacoes/<int:notificacao_id>/abrir/", views.abrir_notificacao, name="abrir_notificacao"),
    path("", views.lista_usuarios, name="lista_usuarios"),
    path("novo/", views.novo_usuario, name="novo_usuario"),
    path("<int:usuario_id>/configurar/", views.configurar_usuario, name="configurar_usuario"),
    path("<int:usuario_id>/status/", views.alternar_status_usuario, name="alternar_status_usuario"),
    path("<int:usuario_id>/excluir/", views.excluir_usuario, name="excluir_usuario"),
    path("<int:usuario_id>/compras/", views.editar_permissoes_compras, name="editar_permissoes_compras"),
]
