from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, render

from obras.models import Obra
from orcamento.models import InsumoOrcamento
from orcamento.services.insumos import alternar_mao_de_obra, listar_insumos_obra


@login_required
def lista_insumos(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    insumos = listar_insumos_obra(obra)

    return render(
        request,
        "orcamento/insumos.html",
        {
            "obra": obra,
            "insumos": insumos,
        },
    )


@login_required
def alternar_mao_de_obra_view(request, insumo_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    insumo = get_object_or_404(InsumoOrcamento, pk=insumo_id)
    insumo = alternar_mao_de_obra(insumo)

    return JsonResponse({"id": insumo.id, "mao_de_obra": insumo.mao_de_obra})
