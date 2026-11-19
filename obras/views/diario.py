from datetime import date, timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import acao_required, modulo_required
from usuarios.models import ModuloSistema, NivelPermissao

from obras.models import (
    DiarioAtividadeAdicional, DiarioAtividadePlanejada, DiarioObra, Obra,
    FotoDiarioObra,
)
from obras.services.fotos import validar_fotos
from planejamento.models import ImportacaoCronograma, RegistroCronograma
from planejamento.services.cronograma.consultas import normalizar_texto


PRE_HABITESE = {"CHECKLIST HABITE-SE", "CHECKLIST PRE HABITE-SE"}
POS_HABITESE = "POS HABITE-SE"


def _atividades_do_dia(obra, data_registro):
    """Usa a semana e o início importados, sem supor numeração ISO."""
    if not obra or not data_registro:
        return None, []
    importacao = ImportacaoCronograma.objects.filter(
        ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA
    ).order_by("-pk").first()
    if not importacao:
        return None, []
    semana = (
        RegistroCronograma.objects.filter(
            importacao=importacao, obra=obra, inicio_semana__lte=data_registro,
            inicio_semana__gt=data_registro - timedelta(days=7), semana__isnull=False,
        )
        .order_by("-inicio_semana", "-semana")
        .values("semana", "inicio_semana")
        .first()
    )
    if not semana:
        return None, []
    opcoes = {}
    registros = (
        RegistroCronograma.objects.filter(
            importacao=importacao, obra=obra, semana=semana["semana"],
            atividade_planejamento__isnull=False, atividade_planejamento__obra=obra,
        )
        .select_related("atividade_planejamento")
        .order_by("atividade_planejamento_id", "-pk")
    )
    for registro in registros:
        atividade = registro.atividade_planejamento
        if atividade.pk in opcoes:
            continue
        disciplina = normalizar_texto(registro.disciplina or atividade.disciplina)
        if disciplina in PRE_HABITESE:
            origem = DiarioAtividadePlanejada.Origem.PRE_HABITESE
        elif disciplina == POS_HABITESE:
            origem = DiarioAtividadePlanejada.Origem.POS_HABITESE
        else:
            origem = DiarioAtividadePlanejada.Origem.SEMANAL
        opcoes[atividade.pk] = {
            "id": atividade.pk,
            "origem": origem,
            "disciplina": registro.disciplina or atividade.disciplina,
            "nome": registro.nome_tarefa or atividade.nome_tarefa,
            "local": registro.local_tarefa or atividade.local_tarefa,
        }
    return semana, list(opcoes.values())


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def diario_atividades_api(request):
    obra_id = request.GET.get("obra")
    try:
        data_registro = date.fromisoformat(request.GET.get("data") or "")
    except ValueError:
        return JsonResponse({"semana": None, "atividades": []})
    obra = Obra.objects.filter(pk=obra_id, ativa=True).first() if str(obra_id or "").isdigit() else None
    semana, atividades = _atividades_do_dia(obra, data_registro)
    return JsonResponse({
        "semana": semana["semana"] if semana else None,
        "inicio_semana": semana["inicio_semana"].isoformat() if semana else None,
        "atividades": atividades,
    })


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

    diarios = list(diarios.prefetch_related(
        "fotos", "atividades_planejadas__atividade", "atividades_adicionais"
    ).order_by("-data", "obra__nome", "-id")[:300])
    _anexar_concretagens(diarios)

    return render(request, "obras/diario_lista.html", {
        "diarios": diarios,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "obra_filtro": int(obra_id) if obra_id and str(obra_id).isdigit() else None,
        "data_inicio": data_inicio or "",
        "data_fim": data_fim or "",
    })


def _anexar_concretagens(diarios):
    """Concretagens (não canceladas) da mesma obra e data de cada diário, só para exibição."""
    from django.db.models import Count, Q, Sum

    from obras.models import Concretagem

    if not diarios:
        return
    chaves = {(d.obra_id, d.data) for d in diarios}
    concs = (
        Concretagem.objects.filter(obra_id__in={o for o, _ in chaves}, data_programada__in={dt for _, dt in chaves})
        .exclude(status=Concretagem.Status.CANCELADA)
        .annotate(
            qtd_caminhoes=Count("caminhoes", filter=Q(caminhoes__ativo=True), distinct=True),
            vol_entregue=Sum("caminhoes__volume_entregue", filter=Q(caminhoes__ativo=True)),
        )
        .prefetch_related("itens_planejados__local").order_by("horario_programado")
    )
    por_chave = {}
    for c in concs:
        por_chave.setdefault((c.obra_id, c.data_programada), []).append(c)
    for d in diarios:
        d.concretagens_dia = por_chave.get((d.obra_id, d.data), [])


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
@acao_required(ModuloSistema.DIARIO_OBRA, "criar")
def diario_novo(request, obra_id=None):
    obra_inicial = None
    if obra_id is not None:
        obra_inicial = get_object_or_404(Obra, pk=obra_id, ativa=True)
    return _diario_form(request, obra_inicial=obra_inicial)


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
@acao_required(ModuloSistema.DIARIO_OBRA, "editar")
def diario_editar(request, diario_id):
    diario = get_object_or_404(DiarioObra.objects.select_related("obra"), pk=diario_id)
    return _diario_form(request, obra_inicial=diario.obra, diario=diario)


def _diario_form(request, obra_inicial=None, diario=None):
    obras = Obra.objects.filter(ativa=True).order_by("nome")
    obra_selecionada = obra_inicial
    data_texto = request.POST.get("data") if request.method == "POST" else (
        diario.data.isoformat() if diario else date.today().isoformat()
    )
    try:
        data_registro = date.fromisoformat(data_texto or "")
    except ValueError:
        data_registro = None

    if request.method == "POST":
        obra_id = request.POST.get("obra")
        obra_selecionada = obras.filter(pk=int(obra_id)).first() if str(obra_id or "").isdigit() else None
    semana, opcoes = _atividades_do_dia(obra_selecionada, data_registro)
    opcoes_por_id = {opcao["id"]: opcao for opcao in opcoes}
    vinculos_existentes = list(diario.atividades_planejadas.select_related("atividade")) if diario else []
    vinculos_historicos = [
        vinculo for vinculo in vinculos_existentes
        if not semana or vinculo.atividade_id not in opcoes_por_id
        or vinculo.semana != semana["semana"]
        or vinculo.inicio_semana != semana["inicio_semana"]
    ]
    ids_historicos = {vinculo.pk for vinculo in vinculos_historicos}
    atividades_historicas = {vinculo.atividade_id for vinculo in vinculos_historicos}
    selecionadas = (
        {int(pk) for pk in request.POST.getlist("atividades") if pk.isdigit()}
        if request.method == "POST" else
        {vinculo.atividade_id for vinculo in vinculos_existentes} - atividades_historicas
    )

    if request.method == "POST":
        servicos = (request.POST.get("servicos_executados") or "").strip()
        efetivo_texto = (request.POST.get("efetivo") or "").strip()
        efetivo = int(efetivo_texto) if efetivo_texto.isdigit() else None
        adicional_descricao = (request.POST.get("adicional_descricao") or "").strip()
        adicional_justificativa = (request.POST.get("adicional_justificativa") or "").strip()
        ids_informados = request.POST.getlist("atividades")
        ids_remocao = request.POST.getlist("remover_atividade_historica")
        remover_historicas = {int(pk) for pk in ids_remocao if pk.isdigit()}

        if obra_selecionada is None:
            messages.error(request, "Selecione a obra do diário.")
        elif data_registro is None:
            messages.error(request, "Informe a data do diário.")
        elif not servicos:
            messages.error(request, "Informe os serviços executados no dia.")
        elif any(not pk.isdigit() for pk in ids_informados) or not selecionadas.issubset(opcoes_por_id):
            messages.error(request, "As atividades selecionadas não pertencem à obra e semana informadas.")
        elif any(not pk.isdigit() for pk in ids_remocao) or not remover_historicas.issubset(ids_historicos):
            messages.error(request, "Os vínculos históricos informados não pertencem a este diário.")
        elif diario and (diario.obra_id, diario.data) != (obra_selecionada.pk, data_registro) and vinculos_existentes:
            messages.error(request, "Remova os vínculos das atividades antes de alterar a obra ou a data do diário.")
        elif bool(adicional_descricao) != bool(adicional_justificativa):
            messages.error(request, "Informe descrição e justificativa da atividade adicional.")
        else:
            try:
                fotos = validar_fotos(request.FILES.getlist("fotos"))
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                fotos = None
            if fotos is None:
                return render(request, "obras/diario_form.html", {
                    "obra": obra_selecionada, "obras": obras, "diario": diario,
                    "climas": DiarioObra.Clima.choices, "hoje": date.today().isoformat(),
                    "data_exibida": data_texto, "semana": semana, "atividades": opcoes,
                    "atividades_selecionadas": selecionadas,
                    "vinculos_historicos": vinculos_historicos,
                    "atividades_adicionais": diario.atividades_adicionais.all() if diario else [],
                })
            obj = diario or DiarioObra(registrado_por=request.user)
            identidade_anterior = (obj.obra_id, obj.data) if obj.pk else None
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
                    vinculos = obj.atividades_planejadas
                    if identidade_anterior and identidade_anterior != (obj.obra_id, obj.data):
                        vinculos.all().delete()
                    else:
                        vinculos.filter(atividade_id__in=opcoes_por_id).exclude(
                            atividade_id__in=selecionadas | atividades_historicas
                        ).delete()
                        vinculos.filter(pk__in=remover_historicas).delete()
                    for pk in selecionadas:
                        opcao = opcoes_por_id[pk]
                        vinculos.update_or_create(atividade_id=pk, defaults={
                            "origem": opcao["origem"],
                            "semana": semana["semana"],
                            "inicio_semana": semana["inicio_semana"],
                        })
                    if diario:
                        remover = [int(pk) for pk in request.POST.getlist("remover_adicional") if pk.isdigit()]
                        DiarioAtividadeAdicional.objects.filter(diario=obj, pk__in=remover).delete()
                    if adicional_descricao:
                        DiarioAtividadeAdicional.objects.create(
                            diario=obj, descricao=adicional_descricao,
                            justificativa=adicional_justificativa,
                        )
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
        "data_exibida": data_texto,
        "semana": semana,
        "atividades": opcoes,
        "atividades_selecionadas": selecionadas,
        "vinculos_historicos": vinculos_historicos,
        "atividades_adicionais": diario.atividades_adicionais.all() if diario else [],
    })
