from datetime import date

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import modulo_required
from usuarios.models import ModuloSistema, NivelPermissao

from obras.models import DiarioObra, Obra, FotoDiarioObra
from obras.services.fotos import validar_fotos


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def diario_lista(request):
    obra_id = request.GET.get("obra")
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")

    diarios = DiarioObra.objects.select_related("obra", "registrado_por")
    if obra_id and str(obra_id).isdigit():
        diarios = diarios.filter(obra_id=int(obra_id))
    if data_inicio:
        diarios = diarios.filter(data__gte=data_inicio)
    if data_fim:
        diarios = diarios.filter(data__lte=data_fim)

    return render(request, "obras/diario_lista.html", {
        "diarios": diarios.prefetch_related("fotos").order_by("-data", "obra__nome", "-id")[:300],
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "obra_filtro": int(obra_id) if obra_id and str(obra_id).isdigit() else None,
        "data_inicio": data_inicio or "",
        "data_fim": data_fim or "",
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def diario_novo(request, obra_id=None):
    obra_inicial = None
    if obra_id is not None:
        obra_inicial = get_object_or_404(Obra, pk=obra_id, ativa=True)
    return _diario_form(request, obra_inicial=obra_inicial)


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def diario_editar(request, diario_id):
    diario = get_object_or_404(DiarioObra.objects.select_related("obra"), pk=diario_id)
    return _diario_form(request, obra_inicial=diario.obra, diario=diario)


def _diario_form(request, obra_inicial=None, diario=None):
    obras = Obra.objects.filter(ativa=True).order_by("nome")
    obra_selecionada = obra_inicial

    if request.method == "POST":
        obra_id = request.POST.get("obra")
        obra_selecionada = obras.filter(pk=obra_id).first()
        data_registro = request.POST.get("data")
        servicos = (request.POST.get("servicos_executados") or "").strip()
        efetivo_texto = (request.POST.get("efetivo") or "").strip()
        efetivo = int(efetivo_texto) if efetivo_texto.isdigit() else None

        if obra_selecionada is None:
            messages.error(request, "Selecione a obra do diário.")
        elif not data_registro:
            messages.error(request, "Informe a data do diário.")
        elif not servicos:
            messages.error(request, "Informe os serviços executados no dia.")
        else:
            try:
                fotos = validar_fotos(request.FILES.getlist("fotos"))
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                fotos = None
            if fotos is None:
                return render(request, "obras/diario_form.html", {"obra": obra_selecionada, "obras": obras, "diario": diario, "climas": DiarioObra.Clima.choices, "hoje": date.today().isoformat()})
            obj = diario or DiarioObra(registrado_por=request.user)
            obj.obra = obra_selecionada
            obj.data = data_registro
            obj.clima = request.POST.get("clima") or ""
            obj.efetivo = efetivo
            obj.servicos_executados = servicos
            obj.equipe_presente = (request.POST.get("equipe_presente") or "").strip()
            obj.ocorrencias = (request.POST.get("ocorrencias") or "").strip()
            obj.observacoes = (request.POST.get("observacoes") or "").strip()
            try:
                with transaction.atomic():
                    obj.save()
                    for foto in fotos:
                        FotoDiarioObra.objects.create(diario=obj, arquivo=foto)
            except IntegrityError:
                messages.error(request, "Já existe um diário registrado para esta obra nesta data.")
            else:
                messages.success(request, "Diário de obra salvo com sucesso.")
                return redirect("obras:diario_lista")

    return render(request, "obras/diario_form.html", {
        "obra": obra_selecionada,
        "obras": obras,
        "diario": diario,
        "climas": DiarioObra.Clima.choices,
        "hoje": date.today().isoformat(),
    })
