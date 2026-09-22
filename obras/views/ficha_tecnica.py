from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
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
from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao

from obras.models import (
    AmbienteFichaTecnica,
    CategoriaFichaTecnica,
    FichaTecnicaObra,
    ItemFichaTecnica,
    Obra,
    PavimentoFichaTecnica,
)


# Regras de escopo específicas da ficha técnica.
# O sistema de ar-condicionado é uma definição da obra/projeto, enquanto
# os equipamentos são informados por ambiente. Mantemos esta regra aqui
# também para bases antigas em que o tipo_preenchimento ficou invertido.
NOME_CAT_AR_SISTEMA = "AR CONDICIONADO - SISTEMA"
NOME_CAT_AR_EQUIPAMENTO = "AR CONDICIONADO - EQUIPAMENTO"
TIPOS_SISTEMA_AR = ("DUTADO", "VRF", "SPLIT", "MULTI SPLIT")


def _sincronizar_item_sistema_ar(aplicacao, tipo_sistema):
    """Mantém uma linha técnica automática para levar o tipo do sistema até Compras."""
    item = (
        aplicacao.itens.filter(
            tipo_item__isnull=True,
            descricao_item=NOME_CAT_AR_SISTEMA,
        )
        .order_by("id")
        .first()
    )
    if item is None:
        item = ItemFichaTecnica.objects.create(
            aplicacao_categoria=aplicacao,
            descricao_item=NOME_CAT_AR_SISTEMA,
            quantidade=Decimal("1.00"),
            especificacao=tipo_sistema,
            ordem=0,
        )
        return item

    alterados = []
    if item.quantidade != Decimal("1.00"):
        item.quantidade = Decimal("1.00")
        alterados.append("quantidade")
    if item.especificacao != tipo_sistema:
        item.especificacao = tipo_sistema
        alterados.append("especificacao")
    if not item.ativo:
        item.ativo = True
        alterados.append("ativo")
    if alterados:
        item.save(update_fields=[*alterados, "atualizado_em"])
    return item


def _categorias_por_escopo():
    categorias = CategoriaGrandeFornecedor.objects.filter(ativo=True).prefetch_related(
        "tipos_itens", "opcoes_especificacao"
    )

    tipos_obra = [
        CategoriaGrandeFornecedor.TipoPreenchimento.MULTIPLA_PROJETO,
        CategoriaGrandeFornecedor.TipoPreenchimento.SIM_NAO_PROJETO,
        CategoriaGrandeFornecedor.TipoPreenchimento.DESCRITIVO,
    ]
    tipos_ambiente = [
        CategoriaGrandeFornecedor.TipoPreenchimento.MULTIPLA_AMBIENTE,
        CategoriaGrandeFornecedor.TipoPreenchimento.SIM_NAO_AMBIENTE,
    ]

    categorias_obra = (
        categorias.filter(
            Q(tipo_preenchimento__in=tipos_obra)
            | Q(nome__iexact=NOME_CAT_AR_SISTEMA)
        )
        .exclude(nome__iexact=NOME_CAT_AR_EQUIPAMENTO)
        .order_by("ordem", "nome")
    )

    categorias_ambiente = (
        categorias.filter(
            Q(tipo_preenchimento__in=tipos_ambiente)
            | Q(nome__iexact=NOME_CAT_AR_EQUIPAMENTO)
        )
        .exclude(nome__iexact=NOME_CAT_AR_SISTEMA)
        .order_by("ordem", "nome")
    )

    return categorias_obra, categorias_ambiente


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


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def fichas_tecnicas(request):
    obras = Obra.objects.filter(ativa=True).order_by("nome")
    fichas = {f.obra_id: f for f in FichaTecnicaObra.objects.filter(obra__in=obras)}
    linhas = [{"obra": obra, "ficha": fichas.get(obra.pk)} for obra in obras]
    return render(request, "obras/fichas_tecnicas.html", {"linhas": linhas})


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
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

    categorias_obra, categorias_ambiente = _categorias_por_escopo()

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

    aplicacao_ar_sistema = next(
        (a for a in aplicacoes_obra if a.categoria.nome.upper() == NOME_CAT_AR_SISTEMA),
        None,
    )
    ar_sistema_tipo_atual = aplicacao_ar_sistema.descricao if aplicacao_ar_sistema else ""

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
        "ar_sistema_categoria_id": aplicacao_ar_sistema.categoria_id if aplicacao_ar_sistema else (
            categorias_obra.filter(nome__iexact=NOME_CAT_AR_SISTEMA).values_list("pk", flat=True).first()
        ),
        "ar_sistema_tipo_atual": ar_sistema_tipo_atual,
        "tipos_sistema_ar": TIPOS_SISTEMA_AR,
        "unidades": UnidadeMedida.objects.filter(ativo=True).order_by("sigla"),
        "total_ambientes": len(ambientes),
        "total_categorias": ficha.categorias_aplicadas.filter(ativo=True).count(),
        "total_itens": ItemFichaTecnica.objects.filter(aplicacao_categoria__ficha=ficha, ativo=True).count(),
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
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
        categorias_obra, _ = _categorias_por_escopo()
        permitidas = list(categorias_obra.filter(pk__in=selecionadas))
        ids = {c.pk for c in permitidas}

        categoria_ar_sistema = next(
            (c for c in permitidas if c.nome.upper() == NOME_CAT_AR_SISTEMA),
            None,
        )
        tipo_sistema_ar = (request.POST.get("tipo_sistema_ar") or "").strip().upper()
        if categoria_ar_sistema and tipo_sistema_ar not in TIPOS_SISTEMA_AR:
            messages.error(
                request,
                "Selecione o tipo do sistema de ar-condicionado: Dutado, VRF, Split ou Multi Split.",
            )
            return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=3")

        qs = ficha.categorias_aplicadas.filter(ambiente__isnull=True)
        qs.exclude(categoria_id__in=ids).delete()
        for cat in permitidas:
            aplicacao, _ = CategoriaFichaTecnica.objects.get_or_create(
                ficha=ficha, categoria=cat, ambiente=None
            )
            if cat.nome.upper() == NOME_CAT_AR_SISTEMA:
                if aplicacao.descricao != tipo_sistema_ar:
                    aplicacao.descricao = tipo_sistema_ar
                    aplicacao.save(update_fields=["descricao"])
                _sincronizar_item_sistema_ar(aplicacao, tipo_sistema_ar)

        messages.success(request, "Categorias gerais da obra atualizadas.")

    elif acao == "salvar_categorias_ambiente":
        ambiente = get_object_or_404(AmbienteFichaTecnica, pk=request.POST.get("ambiente_id"), pavimento__ficha=ficha)
        selecionadas = {int(x) for x in request.POST.getlist("categorias") if x.isdigit()}
        _, categorias_ambiente = _categorias_por_escopo()
        permitidas = []
        for cat in categorias_ambiente.filter(pk__in=selecionadas):
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
        if (
            item.aplicacao_categoria.ambiente_id is None
            and item.aplicacao_categoria.categoria.nome.upper() == NOME_CAT_AR_SISTEMA
            and item.tipo_item_id is None
            and item.descricao_item.upper() == NOME_CAT_AR_SISTEMA
        ):
            messages.error(
                request,
                "O tipo do sistema de ar-condicionado é alterado na etapa Categorias de Grandes Fornecedores.",
            )
            return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=3")
        item.delete()
        messages.success(request, "Item removido da ficha técnica.")
        ambiente_param = f"&ambiente={ambiente_id}" if ambiente_id else ""
        return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa=4{ambiente_param}")

    if ficha.status != FichaTecnicaObra.Status.EM_PREENCHIMENTO:
        ficha.status = FichaTecnicaObra.Status.EM_PREENCHIMENTO
        ficha.save(update_fields=["status", "atualizado_em"])
    return redirect(f"{reverse('obras:ficha_tecnica', args=[obra.pk])}?etapa={etapa}")
