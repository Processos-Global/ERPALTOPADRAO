from collections import OrderedDict
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.validators import validar_documento_upload
from usuarios.decorators import algum_modulo_required, possui_permissao_modulo
from usuarios.models import ModuloSistema, NivelPermissao


def _pode_operar(usuario):
    if getattr(usuario, "is_superuser", False):
        return True
    return any(
        possui_permissao_modulo(usuario, modulo, NivelPermissao.EDICAO)
        for modulo in (ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
    )


def _exigir_operacao(usuario):
    if not _pode_operar(usuario):
        raise PermissionDenied("É necessária permissão de edição em Planejamento ou Suprimentos.")


def _voltar():
    return redirect("planejamento:painel_grandes_fornecedores")


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
def painel_grandes_fornecedores(request):
    # Compatibilidade com favoritos/URLs antigas: a operação de Grandes
    # Fornecedores pertence agora ao módulo de Compras.
    return redirect("compras:grandes_fornecedores")


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
@require_POST
def atualizar_status_item_grande_fornecedor(request, item_id):
    from compras.models import GrandeFornecedorItem
    from compras.services.grandes_fornecedores import atualizar_status_operacional_item

    _exigir_operacao(request.user)
    item = get_object_or_404(
        GrandeFornecedorItem.objects.select_related("fluxo__processo", "pedido_item"),
        pk=item_id,
        fluxo__processo__fluxo_grande_fornecedor=True,
    )
    try:
        atualizar_status_operacional_item(
            micro_item=item,
            novo_status=request.POST.get("status"),
            usuario=request.user,
        )
        messages.success(request, f"Status de {item.item} atualizado.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return _voltar()


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
@require_POST
def atualizar_previsao_item_grande_fornecedor(request, item_id):
    from compras.models import GrandeFornecedorItem
    from compras.services.grandes_fornecedores import atualizar_previsao_operacional_item

    _exigir_operacao(request.user)
    item = get_object_or_404(
        GrandeFornecedorItem.objects.select_related("fluxo__processo", "pedido_item"),
        pk=item_id,
        fluxo__processo__fluxo_grande_fornecedor=True,
    )
    previsao = parse_date(request.POST.get("previsao_entrega") or "")
    try:
        atualizar_previsao_operacional_item(
            micro_item=item,
            previsao=previsao,
            usuario=request.user,
        )
        messages.success(request, f"Previsão de {item.item} atualizada.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return _voltar()


@algum_modulo_required(ModuloSistema.PLANEJAMENTO, ModuloSistema.SUPRIMENTOS)
@require_POST
def receber_pedido_grande_fornecedor(request, pedido_id):
    from compras.models import PedidoCompra
    from compras.services.pedidos import registrar_recebimento

    _exigir_operacao(request.user)
    pedido = get_object_or_404(
        PedidoCompra.objects.select_related("processo").prefetch_related("itens"),
        pk=pedido_id,
        processo__fluxo_grande_fornecedor=True,
    )
    quantidades = {}
    valores_itens = {}
    for item in pedido.itens.all():
        quantidade = request.POST.get(f"item_{item.pk}")
        valor_item = request.POST.get(f"valor_item_{item.pk}")
        if quantidade not in (None, ""):
            quantidades[item.pk] = quantidade
        if valor_item not in (None, ""):
            valores_itens[item.pk] = valor_item

    try:
        arquivo = request.FILES.get("arquivo_nota_fiscal")
        validar_documento_upload(arquivo)
        recebimento = registrar_recebimento(
            pedido=pedido,
            quantidades=quantidades,
            valores_itens=valores_itens,
            usuario=request.user,
            numero_nota_fiscal=request.POST.get("numero_nota_fiscal", ""),
            valor_total_nota=request.POST.get("valor_total_nota", ""),
            arquivo_nota_fiscal=arquivo,
            observacao=request.POST.get("observacao", ""),
        )
        messages.success(request, f"Recebimento registrado com a NF {recebimento.numero_nota_fiscal}.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return _voltar()
