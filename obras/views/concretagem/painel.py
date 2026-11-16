from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from obras.models import Concretagem, Obra
from obras.services.concretagem.permissoes import contexto_permissoes, ver_required

S = Concretagem.Status
ABERTAS = (S.RASCUNHO, S.SOLICITADA, S.CONFIRMADA, S.EXECUTADA, S.AGUARDANDO_LAUDOS)


def _base_qs():
    return Concretagem.objects.select_related("obra", "concreteira", "engenheiro").prefetch_related(
        "itens_planejados__local",
    )


@ver_required
def painel(request):
    hoje = timezone.localdate()
    contagens = Concretagem.objects.aggregate(
        aguardando=Count("id", filter=Q(status=S.SOLICITADA, confirmacao_cliente="")),
        reagendamento=Count("id", filter=Q(status=S.SOLICITADA, confirmacao_cliente="REAGENDAMENTO")),
        confirmadas=Count("id", filter=Q(status=S.CONFIRMADA)),
        hoje=Count("id", filter=Q(data_programada=hoje, status__in=ABERTAS)),
        laudos=Count("id", filter=Q(status=S.AGUARDANDO_LAUDOS)),
        rascunhos=Count("id", filter=Q(status=S.RASCUNHO)),
    )
    obras = (
        Obra.objects.filter(ativa=True)
        .annotate(
            conc_abertas=Count("concretagens", filter=Q(concretagens__status__in=ABERTAS), distinct=True),
            conc_total=Count("concretagens", distinct=True),
            conc_locais=Count("locais_concretagem", filter=Q(locais_concretagem__ativo=True), distinct=True),
        )
        .order_by("nome")
    )
    # Volume em consulta separada: somar sobre dois joins multiplicaria as linhas.
    volumes = dict(
        Concretagem.objects.exclude(status=S.CANCELADA)
        .values("obra_id").annotate(v=Sum("volume_solicitado")).values_list("obra_id", "v")
    )
    obras = list(obras)
    for o in obras:
        o.conc_volume = volumes.get(o.pk)
    proximas = _base_qs().filter(status__in=ABERTAS, data_programada__gte=hoje).order_by(
        "data_programada", "horario_programado",
    )[:12]
    pendentes = _base_qs().filter(status=S.SOLICITADA).exclude(confirmacao_cliente="ACEITO").order_by(
        "data_programada",
    )[:12]
    return render(request, "obras/concretagem/painel.html", {
        "contagens": contagens,
        "obras": obras,
        "proximas": proximas,
        "pendentes": pendentes,
        "hoje": hoje,
        **contexto_permissoes(request.user),
    })


@ver_required
def obra(request, obra_id):
    obra = get_object_or_404(Obra, pk=obra_id)
    status = (request.GET.get("status") or "").strip()
    q = (request.GET.get("q") or "").strip()
    qs = _base_qs().filter(obra=obra)
    if status in S.values:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) | Q(itens_planejados__descricao__icontains=q)
            | Q(itens_planejados__local__nome__icontains=q) | Q(concreteira__nome__icontains=q)
        ).distinct()
    resumo = Concretagem.objects.filter(obra=obra).exclude(status=S.CANCELADA).aggregate(
        total=Count("id"),
        abertas=Count("id", filter=Q(status__in=ABERTAS)),
        concluidas=Count("id", filter=Q(status=S.CONCLUIDA)),
        volume=Sum("volume_solicitado"),
    )
    return render(request, "obras/concretagem/obra.html", {
        "obra": obra,
        "concretagens": qs.order_by("-data_programada", "-criado_em"),
        "resumo": resumo,
        "locais_count": obra.locais_concretagem.filter(ativo=True).count(),
        "status_choices": S.choices,
        "status_filtro": status,
        "q": q,
        **contexto_permissoes(request.user),
    })
