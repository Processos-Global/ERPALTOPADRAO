from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from compras.services.permissoes import compras_acao_required
from obras.models import Obra
from obras.services.estoque import saldos_fisicos_materiais
from usuarios.models import AcaoCompra


def _identificador_valido(valor):
    return (
        valor.isascii() and valor.isdecimal() and len(valor) <= 19
        and 0 < int(valor) <= 2**63 - 1
    )


@require_safe
@compras_acao_required(AcaoCompra.VISUALIZAR)
@never_cache
def estoque_materiais_obra(request):
    obra_id = request.GET.get("obra", "")
    materiais = request.GET.getlist("material")
    if not _identificador_valido(obra_id) or len(materiais) > 200 or not all(
        _identificador_valido(material_id) for material_id in materiais
    ):
        return JsonResponse({"erro": "Obra ou materiais inválidos."}, status=400)
    obra = get_object_or_404(Obra.objects.only("pk"), pk=int(obra_id))
    saldos = saldos_fisicos_materiais(obra.pk, {int(material_id) for material_id in materiais})
    return JsonResponse({"saldos": saldos})
