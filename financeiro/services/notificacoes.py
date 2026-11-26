from django.contrib.auth.models import User
from django.db import transaction
from django.urls import reverse

from financeiro.services.permissoes import permissao_modulo_financeiro_permite, permissoes_modulo_financeiro_ativas
from usuarios.models import TipoNotificacao
from usuarios.services.notificacoes import criar_notificacao


def usuarios_aprovadores_financeiro():
    ids = set(User.objects.filter(is_active=True, is_superuser=True).values_list("pk", flat=True))
    permissoes = permissoes_modulo_financeiro_ativas().filter(usuario__is_active=True, usuario__is_superuser=False)
    ids.update(p.usuario_id for p in permissoes if permissao_modulo_financeiro_permite(p, "APROVAR"))
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
            titulo="Conta a Pagar aguardando aprovação",
            mensagem=f"{titulo.numero} · {titulo.descricao} · R$ {titulo.valor_liquido:,.2f}",
            modulo=modulo,
            tipo=TipoNotificacao.ACAO,
            evento="FINANCEIRO_APROVACAO",
            url=url,
            chave_unica=f"financeiro:aprovacao:{titulo.pk}:ciclo:{titulo.ciclo_aprovacao}:usuario:{usuario.pk}",
            dados={"titulo_id": titulo.pk},
        )
