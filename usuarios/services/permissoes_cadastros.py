from usuarios.models import ModuloSistema, NivelPermissao, PermissaoCadastros, PermissaoModulo


ACOES_CADASTROS = {"visualizar", "criar", "editar", "excluir", "administrar"}


def pode_acao_cadastros(usuario, acao: str) -> bool:
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.is_superuser:
        return True
    if acao not in ACOES_CADASTROS:
        return False

    permissao_modulo = (
        PermissaoModulo.objects
        .filter(usuario=usuario, modulo=ModuloSistema.CADASTROS, ativo=True)
        .first()
    )
    if not permissao_modulo:
        return False

    try:
        granular = usuario.permissao_cadastros_erp
    except PermissaoCadastros.DoesNotExist:
        granular = None

    if granular and granular.ativo:
        if granular.administrar:
            return True
        return bool(getattr(granular, acao, False))

    # Compatibilidade com o nível geral, caso ainda não exista registro granular.
    if acao == "visualizar":
        return True
    if acao in {"criar", "editar"}:
        return permissao_modulo.nivel in {
            NivelPermissao.EDICAO,
            NivelPermissao.APROVACAO,
            NivelPermissao.ADMINISTRADOR,
        }
    if acao in {"excluir", "administrar"}:
        return permissao_modulo.nivel == NivelPermissao.ADMINISTRADOR
    return False
