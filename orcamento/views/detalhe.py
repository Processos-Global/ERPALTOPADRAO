from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from obras.models import Obra
from orcamento.services.arvore import montar_arvore_orcamento


@login_required
def detalhe_orcamento(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    arvore = montar_arvore_orcamento(obra)

    return render(
        request,
        "orcamento/detalhe.html",
        {
            "obra": obra,
            "fases": arvore["fases"],
            "valor_total": arvore["valor_total"],
            "valor_mao_de_obra": arvore["valor_mao_de_obra"],
            "quantidade_insumos": arvore["quantidade_insumos"],
        },
    )
