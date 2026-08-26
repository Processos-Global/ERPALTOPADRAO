from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from usuarios.models import (
    AcaoCompra,
    ModuloNotificacao,
    ModuloSistema,
    NivelPermissao,
    Notificacao,
    PermissaoCompras,
    PermissaoModulo,
    TipoNotificacao,
)


CAMPO_POR_ACAO_COMPRA = {
    AcaoCompra.VISUALIZAR: "visualizar",
    AcaoCompra.SOLICITAR: "solicitar_compra",
    AcaoCompra.COTAR: "executar_cotacao",
    AcaoCompra.COMPATIBILIZAR: "compatibilizar",
    AcaoCompra.NEGOCIAR: "negociar",
    AcaoCompra.APROVAR: "aprovar_compra",
    AcaoCompra.GERENCIAR_PEDIDOS: "gerenciar_pedidos",
    AcaoCompra.RECEBER_PEDIDOS: "receber_pedidos",
    AcaoCompra.CANCELAR_PEDIDOS: "cancelar_pedidos",
    AcaoCompra.ADMINISTRAR: "administrar",
}


ACOES_LEGADAS_APROVACAO = {
    AcaoCompra.APROVAR,
}


def _possui_acao_legada(nivel, acao):
    if nivel == NivelPermissao.ADMINISTRADOR:
        return True

    if acao == AcaoCompra.VISUALIZAR:
        return nivel in {
            NivelPermissao.LEITURA,
            NivelPermissao.EDICAO,
            NivelPermissao.APROVACAO,
        }

    if acao in ACOES_LEGADAS_APROVACAO:
        return nivel == NivelPermissao.APROVACAO

    if acao == AcaoCompra.ADMINISTRAR:
        return False

    return nivel in {
        NivelPermissao.EDICAO,
        NivelPermissao.APROVACAO,
    }


def usuarios_com_acao_compras(acao):
    """
    Retorna todos os usuários ativos que possuem a ação de Compras informada.

    A resolução respeita o modelo atual do ERP:
    1. o usuário precisa possuir acesso ativo ao módulo COMPRAS;
    2. se existir PermissaoCompras ativa, valem as permissões granulares;
    3. se ainda não existir PermissaoCompras, mantém compatibilidade com o
       nível legado da PermissaoModulo.

    Um usuário pode acumular várias ações e, portanto, receber notificações
    de vários pontos do fluxo.
    """
    try:
        acao = AcaoCompra(acao)
    except ValueError:
        return User.objects.none()

    permissoes_modulo = (
        PermissaoModulo.objects
        .filter(
            modulo=ModuloSistema.COMPRAS,
            ativo=True,
            usuario__is_active=True,
        )
        .select_related("usuario", "usuario__permissao_compras_erp")
        .order_by("usuario_id")
    )

    ids = set(
        User.objects.filter(
            is_active=True,
            is_superuser=True,
        ).values_list("pk", flat=True)
    )

    for permissao_modulo in permissoes_modulo:
        usuario = permissao_modulo.usuario

        try:
            granular = usuario.permissao_compras_erp
        except PermissaoCompras.DoesNotExist:
            granular = None

        if granular is not None and granular.ativo:
            if granular.administrar:
                ids.add(usuario.pk)
                continue

            campo = CAMPO_POR_ACAO_COMPRA.get(acao)
            if campo and getattr(granular, campo, False):
                ids.add(usuario.pk)
            continue

        if _possui_acao_legada(permissao_modulo.nivel, acao):
            ids.add(usuario.pk)

    return User.objects.filter(pk__in=ids, is_active=True).order_by("pk")


@transaction.atomic
def criar_notificacao(
    *,
    usuario,
    titulo,
    mensagem,
    modulo=ModuloNotificacao.SISTEMA,
    tipo=TipoNotificacao.INFORMACAO,
    evento="",
    url="",
    chave_unica=None,
    dados=None,
):
    """
    Cria uma notificação ou reabre a mesma pendência quando uma chave única
    já existir para o usuário.

    Reabrir em vez de duplicar é importante em fluxos que podem voltar de
    etapa, como aprovação -> negociação -> aprovação.
    """
    defaults = {
        "titulo": titulo,
        "mensagem": mensagem,
        "modulo": modulo,
        "tipo": tipo,
        "evento": evento or "",
        "url": url or "",
        "dados": dados or {},
        "lida": False,
        "lida_em": None,
    }

    if chave_unica:
        notificacao, criada = Notificacao.objects.update_or_create(
            usuario=usuario,
            chave_unica=chave_unica,
            defaults=defaults,
        )
        return notificacao, criada

    notificacao = Notificacao.objects.create(
        usuario=usuario,
        chave_unica=None,
        **defaults,
    )
    return notificacao, True


@transaction.atomic
def notificar_usuarios_com_acao_compras(
    *,
    acao,
    titulo,
    mensagem,
    evento="",
    url="",
    chave_unica=None,
    dados=None,
    tipo=TipoNotificacao.ACAO,
):
    criadas = []

    for usuario in usuarios_com_acao_compras(acao):
        notificacao, _ = criar_notificacao(
            usuario=usuario,
            titulo=titulo,
            mensagem=mensagem,
            modulo=ModuloNotificacao.COMPRAS,
            tipo=tipo,
            evento=evento,
            url=url,
            chave_unica=chave_unica,
            dados=dados,
        )
        criadas.append(notificacao)

    return criadas


@transaction.atomic
def marcar_chave_como_lida(chave_unica):
    if not chave_unica:
        return 0

    agora = timezone.now()
    return (
        Notificacao.objects
        .filter(chave_unica=chave_unica, lida=False)
        .update(lida=True, lida_em=agora)
    )
