from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao

from obras.models import MovimentoEstoque, Obra
from obras.services import obter_estoque, obter_item_estoque, resumo_por_obra


def _decimal_positivo(valor):
    texto = str(valor or "").strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except (InvalidOperation, ValueError):
        return None
    return numero if numero > 0 else None


def _nome_obra(obra):
    return (obra.nome_curto or obra.nome or obra.codigo or "Obra").strip()


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def almoxarifado_dashboard(request):
    q = (request.GET.get("q") or "").strip().lower()
    obra_id = request.GET.get("obra")

    todas_linhas = obter_estoque(somente_com_saldo=True)
    resumo = resumo_por_obra(todas_linhas)
    valor_total_geral = sum((linha["valor_estoque"] for linha in todas_linhas), Decimal("0"))

    linhas = todas_linhas
    if obra_id and str(obra_id).isdigit():
        linhas = [linha for linha in linhas if linha["obra_id"] == int(obra_id)]
    if q:
        linhas = [
            linha for linha in linhas
            if q in linha["material_nome"].lower()
            or q in linha["descricao"].lower()
            or q in _nome_obra(linha["obra"]).lower()
            or q in (linha["obra"].codigo or "").lower()
        ]

    valor_total_filtrado = sum((linha["valor_estoque"] for linha in linhas), Decimal("0"))

    return render(request, "obras/almoxarifado_dashboard.html", {
        "linhas": linhas,
        "resumo_obras": resumo,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "obra_filtro": int(obra_id) if obra_id and str(obra_id).isdigit() else None,
        "q": request.GET.get("q", ""),
        "total_itens": len(linhas),
        "valor_total_geral": valor_total_geral,
        "valor_total_filtrado": valor_total_filtrado,
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def almoxarifado_obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    q = (request.GET.get("q") or "").strip().lower()
    estoque_completo = obter_estoque(obra=obra, somente_com_saldo=True)
    valor_total_obra = sum((linha["valor_estoque"] for linha in estoque_completo), Decimal("0"))

    linhas = estoque_completo
    if q:
        linhas = [
            linha for linha in linhas
            if q in linha["material_nome"].lower() or q in linha["descricao"].lower()
        ]

    movimentos = (
        MovimentoEstoque.objects
        .filter(Q(obra_origem=obra) | Q(obra_destino=obra))
        .select_related("obra_origem", "obra_destino", "material", "criado_por")
        .order_by("-data_movimento", "-id")[:100]
    )

    return render(request, "obras/almoxarifado_obra.html", {
        "obra": obra,
        "linhas": linhas,
        "estoque_modal": estoque_completo,
        "destinos": Obra.objects.filter(ativa=True).exclude(pk=obra.pk).order_by("nome"),
        "movimentos": movimentos,
        "q": request.GET.get("q", ""),
        "total_itens": len(estoque_completo),
        "valor_total_obra": valor_total_obra,
    })


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def saida_estoque(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id, ativa=True)
    chave_selecionada = request.POST.get("item") or ""
    item = obter_item_estoque(obra, chave_selecionada) if chave_selecionada else None

    if item is None:
        messages.error(request, "Selecione um item válido do estoque.")
        return redirect("obras:almoxarifado_obra", obra_id=obra.pk)

    quantidade = _decimal_positivo(request.POST.get("quantidade"))
    if quantidade is None:
        messages.error(request, "Informe uma quantidade válida maior que zero.")
        return redirect("obras:almoxarifado_obra", obra_id=obra.pk)
    if quantidade > item["saldo"]:
        messages.error(
            request,
            f"Saldo insuficiente. Disponível: {item['saldo']:.2f} {item['unidade']}.",
        )
        return redirect("obras:almoxarifado_obra", obra_id=obra.pk)

    with transaction.atomic():
        Obra.objects.select_for_update().get(pk=obra.pk)
        item_atual = obter_item_estoque(obra, chave_selecionada)
        if item_atual is None or quantidade > item_atual["saldo"]:
            messages.error(request, "O saldo foi alterado. Atualize a página e tente novamente.")
            return redirect("obras:almoxarifado_obra", obra_id=obra.pk)

        MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.SAIDA,
            obra_origem=obra,
            material_id=item_atual["material_id"],
            descricao_item=item_atual["descricao"],
            unidade=item_atual["unidade"],
            quantidade=quantidade,
            finalidade=(request.POST.get("finalidade") or "").strip(),
            documento_referencia=(request.POST.get("documento_referencia") or "").strip(),
            observacao=(request.POST.get("observacao") or "").strip(),
            criado_por=request.user,
        )

    messages.success(request, "Saída registrada com sucesso.")
    return redirect("obras:almoxarifado_obra", obra_id=obra.pk)


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def transferencia_estoque(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id, ativa=True)
    chave_selecionada = request.POST.get("item") or ""
    item = obter_item_estoque(obra, chave_selecionada) if chave_selecionada else None
    destino = Obra.objects.filter(
        ativa=True,
        pk=request.POST.get("obra_destino"),
    ).exclude(pk=obra.pk).first()
    quantidade = _decimal_positivo(request.POST.get("quantidade"))

    if item is None:
        messages.error(request, "Selecione um item válido do estoque.")
    elif destino is None:
        messages.error(request, "Selecione uma obra de destino válida.")
    elif quantidade is None:
        messages.error(request, "Informe uma quantidade válida maior que zero.")
    elif quantidade > item["saldo"]:
        messages.error(
            request,
            f"Saldo insuficiente. Disponível: {item['saldo']:.2f} {item['unidade']}.",
        )
    else:
        with transaction.atomic():
            # Bloqueia as duas obras em ordem fixa para evitar disputa entre transferências simultâneas.
            list(
                Obra.objects.select_for_update()
                .filter(pk__in=sorted([obra.pk, destino.pk]))
                .order_by("pk")
            )
            item_atual = obter_item_estoque(obra, chave_selecionada)
            if item_atual is None or quantidade > item_atual["saldo"]:
                messages.error(request, "O saldo foi alterado. Atualize a página e tente novamente.")
                return redirect("obras:almoxarifado_obra", obra_id=obra.pk)

            MovimentoEstoque.objects.create(
                tipo=MovimentoEstoque.Tipo.TRANSFERENCIA,
                obra_origem=obra,
                obra_destino=destino,
                material_id=item_atual["material_id"],
                descricao_item=item_atual["descricao"],
                unidade=item_atual["unidade"],
                quantidade=quantidade,
                finalidade=(request.POST.get("finalidade") or "").strip(),
                documento_referencia=(request.POST.get("documento_referencia") or "").strip(),
                observacao=(request.POST.get("observacao") or "").strip(),
                criado_por=request.user,
            )
        messages.success(request, f"Transferência para {_nome_obra(destino)} registrada com sucesso.")

    return redirect("obras:almoxarifado_obra", obra_id=obra.pk)
