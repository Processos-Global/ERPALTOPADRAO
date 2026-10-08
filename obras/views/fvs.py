from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from obras.forms import FVSDecisaoForm, FVSCriacaoForm, FVSItemFormSet, FVSResumoForm
from obras.models import AmbienteFichaTecnica, FVS, FVSHistorico, FVSItem, Obra, FotoFVSItem
from obras.services.fotos import validar_fotos
from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao


def _pode_aprovar(user):
    return bool(user.is_superuser or user.has_perm("obras.aprovar_fvs"))


def _registrar(fvs, user, acao, observacao=""):
    FVSHistorico.objects.create(fvs=fvs, usuario=user, acao=acao, observacao=observacao or "")


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def fvs_lista(request):
    qs = FVS.objects.select_related("obra", "modelo_origem", "criado_por", "aprovado_por").prefetch_related("ambientes")
    obra_id = (request.GET.get("obra") or "").strip()
    status = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    if obra_id.isdigit():
        qs = qs.filter(obra_id=int(obra_id))
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(modelo_nome__icontains=q) | Q(empresa_executora__icontains=q))
    contagens = FVS.objects.aggregate(
        total=Count("id"),
        aguardando=Count("id", filter=Q(status=FVS.Status.AGUARDANDO_APROVACAO)),
        devolvidas=Count("id", filter=Q(status=FVS.Status.DEVOLVIDA)),
        aprovadas=Count("id", filter=Q(status=FVS.Status.APROVADA)),
    )
    return render(request, "obras/fvs/lista.html", {
        "fichas": qs,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "status_choices": FVS.Status.choices,
        "obra_filtro": int(obra_id) if obra_id.isdigit() else None,
        "status_filtro": status,
        "q": q,
        "contagens": contagens,
        "pode_aprovar": _pode_aprovar(request.user),
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def fvs_nova(request):
    form = FVSCriacaoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            fvs = form.save(commit=False)
            modelo = form.cleaned_data["modelo_origem"]
            fvs.modelo_nome = modelo.nome
            fvs.modelo_revisao = modelo.revisao
            fvs.normas_referencias = modelo.normas_referencias
            fvs.criado_por = request.user
            fvs.status = FVS.Status.RASCUNHO
            fvs.save()
            form.save_m2m()
            FVSItem.objects.bulk_create([
                FVSItem(
                    fvs=fvs,
                    ordem=item.ordem,
                    item_verificacao=item.item_verificacao,
                    metodo_instrumento=item.metodo_instrumento,
                    criterio_aceite=item.criterio_aceite,
                    tolerancia=item.tolerancia,
                    obrigatorio=item.obrigatorio,
                )
                for item in modelo.itens.all()
            ])
            _registrar(fvs, request.user, FVSHistorico.Acao.CRIADA)
        messages.success(request, f"{fvs.numero} criada. Preencha os itens e envie ao gestor quando concluir.")
        return redirect("obras:fvs_detalhe", pk=fvs.pk)
    return render(request, "obras/fvs/form.html", {"form": form})


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def fvs_detalhe(request, pk):
    fvs = get_object_or_404(
        FVS.objects.select_related("obra", "modelo_origem", "criado_por", "aprovado_por", "enviado_aprovacao_por").prefetch_related("ambientes", "historico__usuario"),
        pk=pk,
    )
    itens_qs = fvs.itens.prefetch_related("fotos").all()
    resumo_form = FVSResumoForm(request.POST or None, instance=fvs, prefix="resumo")
    item_formset = FVSItemFormSet(request.POST or None, queryset=itens_qs, prefix="itens")

    if request.method == "POST":
        if not fvs.pode_editar:
            raise PermissionDenied("Esta FVS está bloqueada para edição.")
        try:
            fotos_por_item = {form.instance.pk: validar_fotos(request.FILES.getlist(f"fotos_item_{form.instance.pk}")) for form in item_formset.forms}
            if sum(len(lista) for lista in fotos_por_item.values()) > 30:
                raise ValidationError("Envie no máximo 30 fotos por salvamento da FVS.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            fotos_por_item = None
        if fotos_por_item is not None and resumo_form.is_valid() and item_formset.is_valid():
            with transaction.atomic():
                resumo_form.save()
                item_formset.save()
                for item_id, fotos in fotos_por_item.items():
                    for foto in fotos:
                        FotoFVSItem.objects.create(item_id=item_id, arquivo=foto)
                if fvs.status in {FVS.Status.RASCUNHO, FVS.Status.DEVOLVIDA}:
                    fvs.status = FVS.Status.EM_PREENCHIMENTO
                    fvs.save(update_fields=["status", "atualizado_em"])
                _registrar(fvs, request.user, FVSHistorico.Acao.SALVA)
            messages.success(request, "Preenchimento da FVS salvo.")
            return redirect("obras:fvs_detalhe", pk=fvs.pk)

    resultados = {
        "c": itens_qs.filter(resultado=FVSItem.Resultado.CONFORME).count(),
        "nc": itens_qs.filter(resultado=FVSItem.Resultado.NAO_CONFORME).count(),
        "na": itens_qs.filter(resultado=FVSItem.Resultado.NAO_APLICAVEL).count(),
        "pendentes": itens_qs.filter(resultado="").count(),
    }
    return render(request, "obras/fvs/detalhe.html", {
        "fvs": fvs,
        "resumo_form": resumo_form,
        "item_formset": item_formset,
        "resultados": resultados,
        "pode_aprovar": _pode_aprovar(request.user),
        "decisao_form": FVSDecisaoForm(),
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
@require_POST
def fvs_enviar_aprovacao(request, pk):
    fvs = get_object_or_404(FVS, pk=pk)
    if not fvs.pode_editar:
        messages.error(request, "Esta FVS não pode ser enviada no status atual.")
        return redirect("obras:fvs_detalhe", pk=pk)
    if fvs.itens.filter(resultado="").exists():
        messages.error(request, "Preencha o resultado de todos os itens antes de enviar ao gestor.")
        return redirect("obras:fvs_detalhe", pk=pk)
    if not fvs.parecer:
        messages.error(request, "Defina o parecer técnico antes de enviar ao gestor.")
        return redirect("obras:fvs_detalhe", pk=pk)
    fvs.status = FVS.Status.AGUARDANDO_APROVACAO
    fvs.enviado_aprovacao_por = request.user
    fvs.enviado_aprovacao_em = timezone.now()
    fvs.save(update_fields=["status", "enviado_aprovacao_por", "enviado_aprovacao_em", "atualizado_em"])
    _registrar(fvs, request.user, FVSHistorico.Acao.ENVIADA)
    messages.success(request, "FVS enviada para aprovação do gestor.")
    return redirect("obras:fvs_detalhe", pk=pk)


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
@require_POST
def fvs_decidir(request, pk):
    if not _pode_aprovar(request.user):
        raise PermissionDenied("Você não possui permissão para aprovar FVS.")
    fvs = get_object_or_404(FVS, pk=pk)
    if fvs.status != FVS.Status.AGUARDANDO_APROVACAO:
        messages.error(request, "Esta FVS não está aguardando aprovação.")
        return redirect("obras:fvs_detalhe", pk=pk)
    form = FVSDecisaoForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revise a decisão informada.")
        return redirect("obras:fvs_detalhe", pk=pk)
    decisao = form.cleaned_data["decisao"]
    obs = form.cleaned_data["observacao"]
    if decisao == "APROVAR":
        fvs.status = FVS.Status.APROVADA
        fvs.aprovado_por = request.user
        fvs.aprovado_em = timezone.now()
        fvs.data_fechamento = timezone.localdate()
        fvs.save(update_fields=["status", "aprovado_por", "aprovado_em", "data_fechamento", "atualizado_em"])
        _registrar(fvs, request.user, FVSHistorico.Acao.APROVADA, obs)
        messages.success(request, "FVS aprovada e bloqueada para edição.")
    else:
        fvs.status = FVS.Status.DEVOLVIDA
        fvs.aprovado_por = None
        fvs.aprovado_em = None
        fvs.data_fechamento = None
        fvs.save(update_fields=["status", "aprovado_por", "aprovado_em", "data_fechamento", "atualizado_em"])
        _registrar(fvs, request.user, FVSHistorico.Acao.DEVOLVIDA, obs)
        messages.warning(request, "FVS devolvida para correção.")
    return redirect("obras:fvs_detalhe", pk=pk)


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def fvs_ambientes(request):
    obra_id = request.GET.get("obra_id")
    if not (obra_id or "").isdigit():
        return JsonResponse({"ambientes": []})
    ambientes = AmbienteFichaTecnica.objects.filter(pavimento__ficha__obra_id=int(obra_id), ativo=True).select_related("pavimento", "tipo_ambiente", "caracteristica").order_by("pavimento__ordem", "ordem", "identificacao")
    return JsonResponse({"ambientes": [
        {
            "id": a.pk,
            "nome": a.identificacao,
            "pavimento": a.pavimento.nome,
            "tipo": a.tipo_ambiente.nome,
            "caracteristica": a.caracteristica.nome,
            "area": str(a.area_m2),
            "label": f"{a.pavimento.nome} · {a.identificacao}",
        }
        for a in ambientes
    ]})
