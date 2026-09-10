from django.contrib.auth import views as auth_views
from django.urls import path

from usuarios import views


app_name = "usuarios"

urlpatterns = [
    # Autenticação
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Recuperação de senha
    path(
        "esqueci-a-senha/",
        views.ERPPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "esqueci-a-senha/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="usuarios/autenticacao/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "redefinir-senha/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="usuarios/autenticacao/password_reset_confirm.html",
            success_url="/usuarios/redefinir-senha/concluida/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "redefinir-senha/concluida/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="usuarios/autenticacao/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # Notificações
    path("notificacoes/", views.lista_notificacoes, name="notificacoes"),
    path(
        "notificacoes/marcar-todas-lidas/",
        views.marcar_todas_notificacoes_lidas,
        name="marcar_todas_notificacoes_lidas",
    ),
    path(
        "notificacoes/<int:notificacao_id>/abrir/",
        views.abrir_notificacao,
        name="abrir_notificacao",
    ),

    # Gestão de usuários
    path("", views.lista_usuarios, name="lista_usuarios"),
    path("novo/", views.novo_usuario, name="novo_usuario"),
    path(
        "<int:usuario_id>/configurar/",
        views.configurar_usuario,
        name="configurar_usuario",
    ),
    path(
        "<int:usuario_id>/status/",
        views.alternar_status_usuario,
        name="alternar_status_usuario",
    ),
    path(
        "<int:usuario_id>/excluir/",
        views.excluir_usuario,
        name="excluir_usuario",
    ),
    path(
        "<int:usuario_id>/compras/",
        views.editar_permissoes_compras,
        name="editar_permissoes_compras",
    ),
]
