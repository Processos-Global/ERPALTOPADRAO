from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from usuarios.models import (
    AcaoCompra,
    ModuloSistema,
    NivelPermissao,
    PermissaoCompras,
    PermissaoModulo,
)


ORDEM = {
    NivelPermissao.LEITURA: 1,
    NivelPermissao.EDICAO: 2,
    NivelPermissao.APROVACAO: 3,
    NivelPermissao.ADMINISTRADOR: 4,
}


CAMPO_POR_ACAO = {
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


ACOES_EDICAO = {
    AcaoCompra.SOLICITAR,
    AcaoCompra.COTAR,
    AcaoCompra.COMPATIBILIZAR,
    AcaoCompra.NEGOCIAR,
    AcaoCompra.GERENCIAR_PEDIDOS,
    AcaoCompra.RECEBER_PEDIDOS,
    AcaoCompra.CANCELAR_PEDIDOS,
    AcaoCompra.ADMINISTRAR,
}


ACOES_VISUALIZACAO = set(CAMPO_POR_ACAO.keys())


def _permissao_modulo_compras(usuario):
    if not usuario.is_authenticated:
        return None

    return (
        PermissaoModulo.objects
        .filter(
            usuario=usuario,
            modulo=ModuloSistema.COMPRAS,
            ativo=True,
        )
        .only("nivel")
        .first()
    )


def obter_permissao_compras(usuario):
    if not usuario.is_authenticated:
        return None

    try:
        permissao = usuario.permissao_compras_erp
    except PermissaoCompras.DoesNotExist:
        permissao = None

    if permissao is None or not permissao.ativo:
        return None

    return permissao


def _possui_acao_por_nivel_legado(nivel, acao):
    """
    Compatibilidade para usuários ainda sem registro em PermissaoCompras.

    Enquanto a tela de permissões granulares não for implantada para todos,
    o nível antigo continua produzindo exatamente o comportamento anterior.
    """

    if nivel == NivelPermissao.ADMINISTRADOR:
        return True

    if acao == AcaoCompra.VISUALIZAR:
        return nivel in {
            NivelPermissao.LEITURA,
            NivelPermissao.EDICAO,
            NivelPermissao.APROVACAO,
        }

    if acao == AcaoCompra.APROVAR:
        return nivel == NivelPermissao.APROVACAO

    if acao == AcaoCompra.ADMINISTRAR:
        return False

    return nivel in {
        NivelPermissao.EDICAO,
        NivelPermissao.APROVACAO,
    }


def possui_acao_compras(usuario, acao):
    if not usuario.is_authenticated:
        return False

    if usuario.is_superuser:
        return True

    try:
        acao = AcaoCompra(acao)
    except ValueError:
        return False

    permissao_modulo = _permissao_modulo_compras(usuario)

    if permissao_modulo is None:
        return False

    permissao = obter_permissao_compras(usuario)

    if permissao is None:
        return _possui_acao_por_nivel_legado(
            permissao_modulo.nivel,
            acao,
        )

    if permissao.administrar:
        return True

    if acao == AcaoCompra.VISUALIZAR:
        return bool(
            permissao.visualizar
            or permissao.solicitar_compra
            or permissao.executar_cotacao
            or permissao.compatibilizar
            or permissao.negociar
            or permissao.aprovar_compra
            or permissao.gerenciar_pedidos
            or permissao.receber_pedidos
            or permissao.cancelar_pedidos
        )

    campo = CAMPO_POR_ACAO.get(acao)

    if not campo:
        return False

    return bool(getattr(permissao, campo, False))


def possui_permissao_compras(
    usuario,
    nivel_minimo=NivelPermissao.LEITURA,
):
    """
    Mantém compatibilidade com o restante do projeto que ainda usa os níveis
    LEITURA / EDICAO / APROVACAO / ADMINISTRADOR.

    Quando existe PermissaoCompras, o nível é inferido a partir das ações
    granulares. Quando ainda não existe, vale o comportamento legado.
    """

    if not usuario.is_authenticated:
        return False

    if usuario.is_superuser:
        return True

    permissao_modulo = _permissao_modulo_compras(usuario)

    if permissao_modulo is None:
        return False

    permissao = obter_permissao_compras(usuario)

    if permissao is None:
        return (
            ORDEM.get(permissao_modulo.nivel, 0)
            >= ORDEM.get(nivel_minimo, 999)
        )

    if nivel_minimo == NivelPermissao.LEITURA:
        return possui_acao_compras(
            usuario,
            AcaoCompra.VISUALIZAR,
        )

    if nivel_minimo == NivelPermissao.EDICAO:
        return any(
            possui_acao_compras(usuario, acao)
            for acao in ACOES_EDICAO
        )

    if nivel_minimo == NivelPermissao.APROVACAO:
        return (
            possui_acao_compras(
                usuario,
                AcaoCompra.APROVAR,
            )
            or possui_acao_compras(
                usuario,
                AcaoCompra.ADMINISTRAR,
            )
        )

    if nivel_minimo == NivelPermissao.ADMINISTRADOR:
        return possui_acao_compras(
            usuario,
            AcaoCompra.ADMINISTRAR,
        )

    return False


def compras_acao_required(acao):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not possui_acao_compras(
                request.user,
                acao,
            ):
                try:
                    descricao = AcaoCompra(acao).label
                except ValueError:
                    descricao = "executar esta ação"

                raise PermissionDenied(
                    "Você não possui permissão para "
                    f"{descricao.lower()} no módulo de Compras."
                )

            return view_func(
                request,
                *args,
                **kwargs,
            )

        return wrapper

    return decorator


def compras_permission_required(
    nivel_minimo=NivelPermissao.LEITURA,
):
    """
    Decorator legado mantido para não quebrar chamadas existentes.
    Novas ações do módulo devem usar compras_acao_required().
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not possui_permissao_compras(
                request.user,
                nivel_minimo,
            ):
                raise PermissionDenied(
                    "Você não possui permissão suficiente "
                    "no módulo de Compras."
                )

            return view_func(
                request,
                *args,
                **kwargs,
            )

        return wrapper

    return decorator
