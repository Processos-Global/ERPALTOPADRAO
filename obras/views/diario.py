from datetime import date

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from usuarios.decorators import acao_required, modulo_required, possui_permissao_modulo
from usuarios.models import ModuloSistema, NivelPermissao

from obras.models import (
    DiarioAtividadePlanejada, DiarioObra, Obra,
    FotoDiarioObra,
)
from obras.services.fotos import validar_fotos
from planejamento.services.cronograma.agenda_semanal import calcular_programacao_semanal
from planejamento.services.cronograma.atividades import listar_atividades_do_retrato
from planejamento.services.cronograma.consultas import (
    CronogramaBaseError, normalizar_texto, queryset_ativo,
)


PRE_HABITESE = {"CHECKLIST HABITE-SE", "CHECKLIST PRE HABITE-SE"}
POS_HABITESE = "POS HABITE-SE"
GRUPOS_ATIVIDADES = {
    DiarioAtividadePlanejada.Origem.PRE_HABITESE: "Pré Habite-se",
    DiarioAtividadePlanejada.Origem.POS_HABITESE: "Pós Habite-se",
    DiarioAtividadePlanejada.Origem.SEMANAL: "Outras atividades",
}
MAIOR_ID_OBRA = 2**63 - 1


def _inteiro_informado(valor, maximo):
    if not valor or not valor.isascii() or not valor.isdecimal() or len(valor) > len(str(maximo)):
        return None
    numero = int(valor)
    return numero if numero <= maximo else None


def _atividades_do_dia(obra, data_registro):
    """Calcula a programação entre os retratos da obra selecionada."""
    if not obra or not data_registro:
        return None, []
    try:
        registros = queryset_ativo(obra=obra).filter(semana__isnull=False)
    except CronogramaBaseError:
        return None, []

    primeiro_inicio_possivel = date.fromordinal(max(1, data_registro.toordinal() - 6))
    semana = (
        registros.filter(inicio_semana__range=(primeiro_inicio_possivel, data_registro))
        .order_by("-inicio_semana", "-semana")
        .values("semana", "inicio_semana")
        .first()
    )
    if not semana:
        return None, []
    # O delta de um retrato mais antigo pode pertencer a uma semana não importada.
    inicio_anterior_minimo = date.fromordinal(max(1, semana["inicio_semana"].toordinal() - 7))
    anterior = (
        registros.filter(
            inicio_semana__gte=inicio_anterior_minimo, inicio_semana__lt=semana["inicio_semana"],
        )
        .order_by("-inicio_semana", "-semana")
        .values("semana", "inicio_semana")
        .first()
    )
    registros_vinculaveis = registros.filter(atividade_planejamento__obra=obra)
    programacao = calcular_programacao_semanal(
        atividades_atuais=listar_atividades_do_retrato(
            registros_vinculaveis.filter(**semana), somente_mais_recente_por_atividade=True,
        ),
        atividades_anteriores=(
            listar_atividades_do_retrato(
                registros_vinculaveis.filter(**anterior), somente_mais_recente_por_atividade=True,
            )
            if anterior else []
        ),
        semana_anterior=anterior["semana"] if anterior else None,
        inicio_semana=semana["inicio_semana"],
    )

    opcoes = []
    for atividade in programacao:
        atividade_id = atividade["atividade_planejamento_id"]
        disciplina = normalizar_texto(atividade["disciplina"])
        if disciplina in PRE_HABITESE:
            origem = DiarioAtividadePlanejada.Origem.PRE_HABITESE
        elif disciplina == POS_HABITESE:
            origem = DiarioAtividadePlanejada.Origem.POS_HABITESE
        else:
            origem = DiarioAtividadePlanejada.Origem.SEMANAL
        opcoes.append({
            "id": atividade_id,
            "origem": origem,
            "grupo": GRUPOS_ATIVIDADES[origem],
            "disciplina": atividade["disciplina"],
            "nome": atividade["atividade"],
            "local": atividade["local"],
        })
    ordem = {grupo: indice for indice, grupo in enumerate(GRUPOS_ATIVIDADES)}
    opcoes.sort(key=lambda opcao: ordem[opcao["origem"]])
    return semana, opcoes


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def diario_atividades_api(request):
    obra_id = _inteiro_informado(request.GET.get("obra"), MAIOR_ID_OBRA)
    try:
        data_registro = date.fromisoformat(request.GET.get("data") or "")
    except ValueError:
        return JsonResponse({"semana": None, "atividades": []})
    obra = Obra.objects.filter(pk=obra_id, ativa=True).first() if obra_id else None
    semana, atividades = _atividades_do_dia(obra, data_registro)
    return JsonResponse({
        "semana": semana["semana"] if semana else None,
        "inicio_semana": semana["inicio_semana"].isoformat() if semana else None,
        "atividades": atividades,
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def diario_lista(request):
    obra_id = _inteiro_informado(request.GET.get("obra"), MAIOR_ID_OBRA)
    data_inicio = request.GET.get("inicio")
    data_fim = request.GET.get("fim")

    diarios = DiarioObra.objects.select_related("obra", "registrado_por")
    if obra_id:
        diarios = diarios.filter(obra_id=obra_id)
    if data_inicio:
        diarios = diarios.filter(data__gte=data_inicio)
    if data_fim:
        diarios = diarios.filter(data__lte=data_fim)

    diarios = diarios.prefetch_related(
        "fotos",
        "atividades_planejadas__atividade",
        "atividades_adicionais",
    ).order_by("-data", "obra__nome", "-id")
    pagina = Paginator(diarios, 30).get_page(request.GET.get("page"))
    diarios = list(pagina.object_list)
    pagina.object_list = diarios

    from obras.services.concretagem.permissoes import pode_concretagem

    if pode_concretagem(request.user):
        _anexar_concretagens(diarios)
    else:
        for d in diarios:
            d.concretagens_dia = []

    return render(request, "obras/diario_lista.html", {
        "diarios": diarios,
        "pagina": pagina,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "obra_filtro": obra_id,
        "data_inicio": data_inicio or "",
        "data_fim": data_fim or "",
        "pode_editar_diario": possui_permissao_modulo(request.user, ModuloSistema.OBRAS, NivelPermissao.EDICAO),
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
        obra_id = _inteiro_informado(request.POST.get("obra"), MAIOR_ID_OBRA)
        obra_selecionada = obras.filter(pk=obra_id).first() if obra_id else None
    semana, opcoes = _atividades_do_dia(obra_selecionada, data_registro)
    ids_disponiveis = {opcao["id"] for opcao in opcoes}
    vinculos_existentes = list(diario.atividades_planejadas.select_related("atividade")) if diario else []
    vinculos_historicos = [
        vinculo for vinculo in vinculos_existentes
        if not semana or vinculo.atividade_id not in ids_disponiveis
        or vinculo.semana != semana["semana"]
        or vinculo.inicio_semana != semana["inicio_semana"]
    ]
    ids_historicos = {str(vinculo.pk): vinculo.pk for vinculo in vinculos_historicos}
    atividades_historicas = {vinculo.atividade_id for vinculo in vinculos_historicos}
    opcoes = [opcao for opcao in opcoes if opcao["id"] not in atividades_historicas]
    opcoes_por_id = {opcao["id"]: opcao for opcao in opcoes}
    selecionadas = {vinculo.atividade_id for vinculo in vinculos_existentes} - atividades_historicas

    if request.method == "POST":
        efetivo_texto = (request.POST.get("efetivo") or "").strip()
        efetivo = _inteiro_informado(efetivo_texto, 2**31 - 1)
        ids_informados = set(request.POST.getlist("atividades"))
        ids_remocao = set(request.POST.getlist("remover_atividade_historica"))
        ids_opcoes = {str(pk): pk for pk in opcoes_por_id}
        selecionadas = {ids_opcoes[pk] for pk in ids_informados & ids_opcoes.keys()}

        if obra_selecionada is None:
            messages.error(request, "Selecione a obra do diário.")
        elif data_registro is None:
            messages.error(request, "Informe a data do diário.")
        elif not ids_informados.issubset(ids_opcoes):
            messages.error(request, "As atividades selecionadas não pertencem à obra e semana informadas.")
        elif not ids_remocao.issubset(ids_historicos):
            messages.error(request, "Os vínculos históricos informados não pertencem a este diário.")
        elif diario and (diario.obra_id, diario.data) != (obra_selecionada.pk, data_registro) and vinculos_existentes:
            messages.error(request, "Remova os vínculos das atividades antes de alterar a obra ou a data do diário.")
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
                })
            obj = diario or DiarioObra(registrado_por=request.user, servicos_executados="")
            identidade_anterior = (obj.obra_id, obj.data) if obj.pk else None
            obj.obra = obra_selecionada
            obj.data = data_registro
            obj.clima = request.POST.get("clima") or ""
            obj.efetivo = efetivo
            obj.equipe_presente = (request.POST.get("equipe_presente") or "").strip()
            obj.ocorrencias = (request.POST.get("ocorrencias") or "").strip()
            try:
                with transaction.atomic():
                    if diario:
                        obj.save(update_fields=[
                            "obra", "data", "clima", "efetivo", "equipe_presente",
                            "ocorrencias", "atualizado_em",
                        ])
                    else:
                        obj.save()
                    vinculos = obj.atividades_planejadas
                    if identidade_anterior and identidade_anterior != (obj.obra_id, obj.data):
                        vinculos.all().delete()
                    else:
                        vinculos.filter(atividade_id__in=opcoes_por_id).exclude(
                            atividade_id__in=selecionadas
                        ).delete()
                        vinculos.filter(pk__in=[ids_historicos[pk] for pk in ids_remocao]).delete()
                    for pk in selecionadas:
                        opcao = opcoes_por_id[pk]
                        vinculos.update_or_create(atividade_id=pk, defaults={
                            "origem": opcao["origem"],
                            "semana": semana["semana"],
                            "inicio_semana": semana["inicio_semana"],
                        })
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
    })
