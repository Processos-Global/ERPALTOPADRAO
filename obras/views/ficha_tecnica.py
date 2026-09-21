from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from cadastros.models import (
    CaracteristicaAmbiente,
    CategoriaGrandeFornecedor,
    OpcaoEspecificacaoGrandeFornecedor,
    TipoAmbiente,
    TipoItemGrandeFornecedor,
    TipoPavimento,
    UnidadeMedida,
)
from obras.models import (
    AmbienteFichaTecnica,
    CategoriaFichaTecnica,
    FichaTecnicaObra,
    ItemFichaTecnica,
    Obra,
    PavimentoFichaTecnica,
)


def _decimal(valor, padrao="0"):
    try:
        return Decimal(str(valor or padrao).replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal(padrao)


def _ficha(obra, usuario):
    ficha, _ = FichaTecnicaObra.objects.get_or_create(
        obra=obra,
        defaults={"criado_por": usuario, "status": FichaTecnicaObra.Status.EM_PREENCHIMENTO},
    )
    return ficha


@login_required
def fichas_tecnicas(request):
    obras = Obra.objects.filter(ativa=True).order_by("nome")
    fichas = {f.obra_id: f for f in FichaTecnicaObra.objects.filter(obra__in=obras)}
    linhas = [{"obra": obra, "ficha": fichas.get(obra.pk)} for obra in obras]
    return render(request, "obras/fichas_tecnicas.html", {"linhas": linhas})


@login_required
def ficha_tecnica(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    ficha = _ficha(obra, request.user)
    etapa = request.GET.get("etapa", "1")
    ambiente_id = request.GET.get("ambiente")

    pavimentos = list(ficha.pavimentos.prefetch_related("ambientes__tipo_ambiente", "ambientes__caracteristica"))
    ambientes = list(
        AmbienteFichaTecnica.objects.filter(pavimento__ficha=ficha, ativo=True)
        .select_related("pavimento", "tipo_ambiente", "caracteristica")
        .order_by("pavimento__ordem", "ordem", "identificacao")
    )
    ambiente_selecionado = None
    if ambiente_id and str(ambiente_id).isdigit():
        ambiente_selecionado = next((a for a in ambientes if a.pk == int(ambiente_id)), None)
    if not ambiente_selecionado and ambientes:
        ambiente_selecionado = ambientes[0]

    categorias = CategoriaGrandeFornecedor.objects.filter(ativo=True).prefetch_related("tipos_itens", "opcoes_especificacao")
    categorias_obra = categorias.filter(tipo_preenchimento__in=[
        CategoriaGrandeFornecedor.TipoPreenchimento.MULTIPLA_PROJETO,
        CategoriaGrandeFornecedor.TipoPreenchimento.SIM_NAO_PROJETO,
        CategoriaGrandeFornecedor.TipoPreenchimento.DESCRITIVO,
    ])
    categorias_ambiente = categorias.filter(tipo_preenchimento__in=[
        CategoriaGrandeFornecedor.TipoPreenchimento.MULTIPLA_AMBIENTE,
        CategoriaGrandeFornecedor.TipoPreenchimento.SIM_NAO_AMBIENTE,
    ])

    aplicacoes_obra = list(
        ficha.categorias_aplicadas.filter(ambiente__isnull=True, ativo=True)
        .select_related("categoria")
        .prefetch_related(
            "itens__tipo_item",
            "itens__unidade",
            "itens__opcao_especificacao",
            "itens__itens_compatibilizacao_gf",
        )
    )
    aplicacoes_ambiente = []
    if ambiente_selecionado:
        aplicacoes_ambiente = list(
            ficha.categorias_aplicadas.filter(ambiente=ambiente_selecionado, ativo=True)
            .select_related("categoria")
            .prefetch_related(
                "itens__tipo_item",
                "itens__unidade",
                "itens__opcao_especificacao",
                "itens__itens_compatibilizacao_gf",
            )
        )

    return render(request, "obras/ficha_tecnica.html", {
        "obra": obra,
        "ficha": ficha,
        "etapa": str(etapa),
        "pavimentos": pavimentos,
        "ambientes": ambientes,
        "ambiente_selecionado": ambiente_selecionado,
        "tipos_pavimento": TipoPavimento.objects.filter(ativo=True).order_by("ordem", "nome"),
        "tipos_ambiente": TipoAmbiente.objects.filter(ativo=True).select_related("caracteristica_padrao").order_by("nome"),
        "caracteristicas": CaracteristicaAmbiente.objects.filter(ativo=True).order_by("nome"),
        "categorias_obra": categorias_obra,
        "categorias_ambiente": categorias_ambiente,
        "aplicacoes_obra": aplicacoes_obra,
        "aplicacoes_ambiente": aplicacoes_ambiente,
        "aplicacoes_obra_ids": {a.categoria_id for a in aplicacoes_obra},
        "aplicacoes_ambiente_ids": {a.categoria_id for a in aplicacoes_ambiente},
        "unidades": UnidadeMedida.objects.filter(ativo=True).order_by("sigla"),
        "total_ambientes": len(ambientes),
        "total_categorias": ficha.categorias_aplicadas.filter(ativo=True).count(),
        "total_itens": ItemFichaTecnica.objects.filter(aplicacao_categoria__ficha=ficha, ativo=True).count(),
    })


@login_required
@require_POST
@transaction.atomic
def ficha_tecnica_acao(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    ficha = _ficha(obra, request.user)
    acao = request.POST.get("acao")
    etapa = request.POST.get("etapa", "1")

    if acao == "adicionar_pavimento":
        tipo = get_object_or_404(TipoPavimento, pk=request.POST.get("tipo_pavimento"), ativo=True)
        nome = (request.POST.get("nome") or tipo.nome).strip()
        ordem = ficha.pavimentos.count() + 1
        PavimentoFichaTecnica.objects.get_or_create(ficha=ficha, nome=nome, defaults={"tipo_pavimento": tipo, "ordem": ordem})
        messages.success(request, "Pavimento adicionado.")

    elif acao == "excluir_pavimento":
        pav = get_object_or_404(PavimentoFichaTecnica, pk=request.POST.get("pavimento_id"), ficha=ficha)
        pav.delete()
        messages.success(request, "Pavimento removido.")

    elif acao == "adicionar_ambiente":
        pav = get_object_or_404(PavimentoFichaTecnica, pk=request.POST.get("pavimento"), ficha=ficha)
        tipo = get_object_or_404(TipoAmbiente, pk=request.POST.get("tipo_ambiente"), ativo=True)
        caracteristica_id = request.POST.get("caracteristica") or (tipo.caracteristica_padrao_id or "")
        caracteristica = get_object_or_404(CaracteristicaAmbiente, pk=caracteristica_id, ativo=True)
        area = _decimal(request.POST.get("area_m2"))
        if area <= 0:
            messages.error(request, "Informe uma área em m² maior que zero.")
        else:
            identificacao = (request.POST.get("identificacao") or tipo.nome).strip()
            AmbienteFichaTecnica.objects.create(
                pavimento=pav,
                tipo_ambiente=tipo,
                identificacao=identificacao,
                caracteristica=caracteristica,
                area_m2=area,
                ordem=pav.ambientes.count() + 1,
            )
            messages.success(request, "Ambiente adicionado.")

    elif acao == "excluir_ambiente":
        ambiente = get_object_or_404(AmbienteFichaTecnica, pk=request.POST.get("ambiente_id"), pavimento__ficha=ficha)
        ambiente.delete()
        messages.success(request, "Ambiente removido.")

    elif acao == "salvar_categorias_obra":
        selecionadas = {int(x) for x in request.POST.getlist("categorias") if x.isdigit()}
        qs = ficha.categorias_aplicadas.filter(ambiente__isnull=True)
        qs.exclude(categoria_id__in=selecionadas).delete()
        for cat in CategoriaGrandeFornecedor.objects.filter(pk__in=selecionadas, ativo=True):
            CategoriaFichaTecnica.objects.get_or_create(ficha=ficha, categoria=cat, ambiente=None)
        messages.success(request, "Categorias gerais da obra atualizadas.")

    elif acao == "salvar_categorias_ambiente":
        ambiente = get_object_or_404(AmbienteFichaTecnica, pk=request.POST.get("ambiente_id"), pavimento__ficha=ficha)
        selecionadas = {int(x) for x in request.POST.getlist("categorias") if x.isdigit()}
        permitidas = []
        for cat in CategoriaGrandeFornecedor.objects.filter(pk__in=selecionadas, ativo=True):
            if cat.somente_area_molhada and ambiente.caracteristica.codigo != "AREA_MOLHADA":
                continue
            permitidas.append(cat)
        ids = {c.pk for c in permitidas}
        ficha.categorias_aplicadas.filter(ambiente=ambiente).exclude(categoria_id__in=ids).delete()
        for cat in permitidas:
            CategoriaFichaTecnica.objects.get_or_create(ficha=ficha, categoria=cat, ambiente=ambiente)
        messages.success(request, f"Categorias de {ambiente.identificacao} atualizadas.")
        return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=3&ambiente={ambiente.pk}")

    elif acao == "adicionar_item":
        aplicacao = get_object_or_404(CategoriaFichaTecnica, pk=request.POST.get("aplicacao"), ficha=ficha)
        tipo_item = None
        tipo_item_id = request.POST.get("tipo_item")
        if tipo_item_id:
            tipo_item = get_object_or_404(TipoItemGrandeFornecedor, pk=tipo_item_id, categoria=aplicacao.categoria, ativo=True)
        unidade = None
        unidade_id = request.POST.get("unidade")
        if unidade_id:
            unidade = get_object_or_404(UnidadeMedida, pk=unidade_id, ativo=True)
        opcao = None
        opcao_id = request.POST.get("opcao_especificacao")
        if opcao_id:
            opcao = get_object_or_404(OpcaoEspecificacaoGrandeFornecedor, pk=opcao_id, categoria=aplicacao.categoria, ativo=True)
        ItemFichaTecnica.objects.create(
            aplicacao_categoria=aplicacao,
            tipo_item=tipo_item,
            descricao_item=(request.POST.get("descricao_item") or "").strip(),
            quantidade=max(_decimal(request.POST.get("quantidade"), "1"), Decimal("0.01")),
            unidade=unidade or (tipo_item.unidade_padrao if tipo_item else None),
            opcao_especificacao=opcao,
            especificacao=(request.POST.get("especificacao") or "").strip(),
            observacao=(request.POST.get("observacao") or "").strip(),
            ordem=aplicacao.itens.count() + 1,
        )
        messages.success(request, "Item incluído na ficha técnica.")
        ambiente_param = f"&ambiente={aplicacao.ambiente_id}" if aplicacao.ambiente_id else ""
        return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=4{ambiente_param}")

    elif acao == "excluir_item":
        item = get_object_or_404(ItemFichaTecnica, pk=request.POST.get("item_id"), aplicacao_categoria__ficha=ficha)
        ambiente_id = item.aplicacao_categoria.ambiente_id
        item.delete()
        messages.success(request, "Item removido da ficha técnica.")
        ambiente_param = f"&ambiente={ambiente_id}" if ambiente_id else ""
        return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=4{ambiente_param}")

    if ficha.status != FichaTecnicaObra.Status.EM_PREENCHIMENTO:
        ficha.status = FichaTecnicaObra.Status.EM_PREENCHIMENTO
        ficha.save(update_fields=["status", "atualizado_em"])
    return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa={etapa}")
