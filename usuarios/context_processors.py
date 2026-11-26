from django.utils.crypto import salted_hmac

from compras.services.permissoes import possui_acao_compras
from financeiro.services.permissoes import (
    permissao_modulo_financeiro_permite,
    permissoes_modulo_financeiro_ativas,
)
from obras.services.concretagem.permissoes import pode_concretagem
from pos_obra.access import acesso_interno
from pos_obra.models import Cliente
from usuarios.decorators import possui_permissao_acao
from usuarios.models import AcaoCompra, ModuloSistema, NivelPermissao, Notificacao, PermissaoModulo
from usuarios.services import pode_acao_cadastros
from usuarios.services.navegacao import acesso_menu_financeiro, internal_navigation, portal_navigation


def erp_layout(request):
    if not hasattr(request, "_saari_erp_layout"):
        request._saari_erp_layout = _build_erp_layout(request)
    return request._saari_erp_layout


def _build_erp_layout(request):
    user = request.user
    if not user.is_authenticated:
        return {}

    preferences_key = salted_hmac("saari.navegacao", str(user.pk), algorithm="sha256").hexdigest()[:24]
    cliente = Cliente.objects.filter(usuario=user).values("ativo", "portal_habilitado").first()
    if cliente is not None:
        return {
            "is_cliente_pos_obra": True,
            "erp_nav_account": preferences_key,
            **portal_navigation(request, cliente["ativo"] and cliente["portal_habilitado"]),
        }

    if user.is_superuser:
        levels = {module: NivelPermissao.ADMINISTRADOR for module in ModuloSistema}
    else:
        levels = dict(PermissaoModulo.objects.filter(usuario=user, ativo=True).values_list("modulo", "nivel"))

    financeiro = None
    if not user.is_superuser and ModuloSistema.FINANCEIRO in levels:
        financeiro = permissoes_modulo_financeiro_ativas().filter(usuario=user).first()

    def permite_financeiro(acao):
        return user.is_active and (
            user.is_superuser or (financeiro is not None and permissao_modulo_financeiro_permite(financeiro, acao))
        )

    access = {
        "obras": user.is_active and ModuloSistema.OBRAS in levels,
        "planejamento": user.is_active and ModuloSistema.PLANEJAMENTO in levels,
        "suprimentos": user.is_active and ModuloSistema.SUPRIMENTOS in levels,
        "projetos": user.is_active and ModuloSistema.PROJETOS in levels,
        "compras": ModuloSistema.COMPRAS in levels and possui_acao_compras(user, AcaoCompra.VISUALIZAR),
        "cadastros": ModuloSistema.CADASTROS in levels and pode_acao_cadastros(user, "visualizar"),
        **acesso_menu_financeiro(permite_financeiro),
        "pos_obra": ModuloSistema.POS_OBRA in levels and acesso_interno(user)
        and possui_permissao_acao(user, ModuloSistema.POS_OBRA, "visualizar"),
        "indicadores": ModuloSistema.RELATORIOS in levels
        and possui_permissao_acao(user, ModuloSistema.RELATORIOS, "visualizar"),
        "usuarios": user.is_superuser or (
            levels.get(ModuloSistema.USUARIOS) == NivelPermissao.ADMINISTRADOR
            and possui_permissao_acao(user, ModuloSistema.USUARIOS, "gerenciar")
        ),
        "concretagem": ModuloSistema.OBRAS in levels and pode_concretagem(user),
    }

    notificacoes = Notificacao.objects.filter(usuario=user)
    return {
        "erp_nav_account": preferences_key,
        "notificacoes_recentes": list(notificacoes.order_by("-atualizada_em", "-id")[:6]),
        "notificacoes_nao_lidas": notificacoes.filter(lida=False).count(),
        "sidebar_obra_ativa_nome": request.session.get("obra_ativa_nome", "Nenhuma obra selecionada"),
        "sidebar_obra_ativa_status": request.session.get("obra_ativa_status", "Sem obra ativa"),
        **{f"{key}_acesso": value for key, value in access.items()},
        **internal_navigation(request, access),
    }
