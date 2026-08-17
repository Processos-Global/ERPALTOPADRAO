from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q

from compras.models import AlcadaAprovacaoCompra
from .comercial import total_aprovacao_processo


def _cargo_usuario(usuario):
    candidatos = [
        getattr(usuario, "cargo", None),
        getattr(getattr(usuario, "perfil", None), "cargo", None),
        getattr(getattr(usuario, "profile", None), "cargo", None),
    ]
    for cargo in candidatos:
        if cargo:
            return str(cargo).strip().casefold()
    return ""


def _usuario_atende_alcada(usuario, alcada):
    if getattr(usuario, "is_superuser", False):
        return True
    if alcada.usuario_id and alcada.usuario_id != usuario.pk:
        return False
    if alcada.cargo:
        return _cargo_usuario(usuario) == alcada.cargo.strip().casefold()
    return True


def resolver_alcada_aprovacao(processo, usuario, valor=None):
    """
    Resolve a alçada aplicável ao valor total aprovado.

    Compatibilidade: se não existir nenhuma alçada ativa configurada no sistema,
    mantém o fluxo legado e retorna None. Assim a implantação da configuração de
    alçadas pode ser gradual.
    """
    valor = Decimal(str(valor if valor is not None else total_aprovacao_processo(processo)))
    ativas = AlcadaAprovacaoCompra.objects.filter(ativo=True)
    if not ativas.exists():
        return None

    candidatas = (
        ativas
        .filter(Q(obra=processo.obra) | Q(obra__isnull=True))
        .filter(valor_minimo__lte=valor)
        .filter(Q(valor_maximo__isnull=True) | Q(valor_maximo__gte=valor))
        .order_by("-obra_id", "ordem", "valor_minimo", "id")
    )

    if not candidatas.exists():
        raise ValidationError(
            f"Não existe alçada de aprovação configurada para o valor de R$ {valor:,.2f}."
        )

    for alcada in candidatas:
        if _usuario_atende_alcada(usuario, alcada):
            return alcada

    raise ValidationError(
        f"Seu usuário não pertence à alçada exigida para aprovar R$ {valor:,.2f}."
    )
