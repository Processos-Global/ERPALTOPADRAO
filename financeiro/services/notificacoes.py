from django.contrib.auth.models import User
from django.db import transaction
from django.urls import reverse

from usuarios.models import ModuloSistema, PermissaoModulo, TipoNotificacao
from usuarios.services.notificacoes import criar_notificacao

try:
    from usuarios.models import PermissaoFinanceiro
except ImportError:
    PermissaoFinanceiro = None


def usuarios_aprovadores_financeiro():
    ids = set(User.objects.filter(is_active=True, is_superuser=True).values_list("pk", flat=True))
    gerais = PermissaoModulo.objects.filter(usuario__is_active=True, modulo=ModuloSistema.FINANCEIRO, ativo=True).select_related("usuario")
    for geral in gerais:
        if PermissaoFinanceiro:
            granular = PermissaoFinanceiro.objects.filter(usuario=geral.usuario, ativo=True).first()
            if granular and (granular.aprovar_pagamentos or granular.administrar):
                ids.add(geral.usuario_id)
                continue
        if geral.nivel in {"APROVACAO", "ADMINISTRADOR"}:
            ids.add(geral.usuario_id)
    return User.objects.filter(pk__in=ids, is_active=True)


@transaction.atomic
def notificar_aprovadores(titulo):
    try:
        modulo = "FINANCEIRO"
        url = reverse("financeiro:titulo_detalhe", args=[titulo.pk])
    except Exception:
        modulo = "SISTEMA"
        url = ""
    for usuario in usuarios_aprovadores_financeiro():
        criar_notificacao(
            usuario=usuario,
            titulo="Pagamento aguardando aprovação",
            mensagem=f"{titulo.numero} · {titulo.descricao} · R$ {titulo.valor_liquido:,.2f}",
            modulo=modulo,
            tipo=TipoNotificacao.ACAO,
            evento="FINANCEIRO_APROVACAO",
            url=url,
            chave_unica=f"financeiro:aprovacao:{titulo.pk}:ciclo:{titulo.ciclo_aprovacao}:usuario:{usuario.pk}",
            dados={"titulo_id": titulo.pk},
        )
