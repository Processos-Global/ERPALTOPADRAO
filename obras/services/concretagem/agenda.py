"""Agenda interna: concretagens do mês, rompimentos previstos de CPs e CPs a enviar."""
import calendar
import datetime

from obras.models import Concretagem, LaudoConcretagem

S = Concretagem.Status
IDADES = (7, 14, 28)


def _base_data(conc):
    """Data de referência para o rompimento: dia em que a concretagem foi executada (ou o programado)."""
    if conc.executada_em:
        return conc.executada_em.date()
    return conc.data_programada


def montar_mes(ano, mes, obra_id=None):
    primeiro = datetime.date(ano, mes, 1)
    ultimo = datetime.date(ano, mes, calendar.monthrange(ano, mes)[1])
    concs = Concretagem.objects.select_related("obra", "concreteira").exclude(status=S.CANCELADA)
    if obra_id:
        concs = concs.filter(obra_id=obra_id)

    eventos = {}

    def add(dia, evento):
        eventos.setdefault(dia, []).append(evento)

    for c in concs.filter(data_programada__range=(primeiro, ultimo)):
        add(c.data_programada, {"tipo": "concretagem", "conc": c})

    # Rompimentos previstos: concretagens executadas cujo laudo daquela idade ainda não foi lançado.
    janela_ini = primeiro - datetime.timedelta(days=max(IDADES))
    candidatas = concs.filter(status__in=(S.EXECUTADA, S.AGUARDANDO_LAUDOS, S.CONCLUIDA), data_programada__gte=janela_ini - datetime.timedelta(days=5))
    lancados = set(
        LaudoConcretagem.objects.filter(concretagem__in=candidatas).values_list("concretagem_id", "idade_dias")
    )
    for c in candidatas:
        base = _base_data(c)
        if not base:
            continue
        for idade in IDADES:
            dia = base + datetime.timedelta(days=idade)
            if primeiro <= dia <= ultimo:
                add(dia, {"tipo": "rompimento", "conc": c, "idade": idade, "lancado": (c.pk, idade) in lancados})

    semanas = []
    for semana in calendar.Calendar(firstweekday=6).monthdatescalendar(ano, mes):
        semanas.append([
            {"data": d, "do_mes": d.month == mes, "hoje": d == datetime.date.today(), "eventos": eventos.get(d, [])}
            for d in semana
        ])
    return semanas


def cps_a_enviar(obra_id=None):
    qs = Concretagem.objects.filter(status=S.EXECUTADA).select_related("obra").order_by("executada_em")
    return qs.filter(obra_id=obra_id) if obra_id else qs


def concretagens_do_dia(obra_id, data):
    """Concretagens (não canceladas) de uma obra numa data, para o Diário de Obra."""
    from django.db.models import Count, Q, Sum

    return (
        Concretagem.objects.filter(obra_id=obra_id, data_programada=data).exclude(status=S.CANCELADA)
        .annotate(
            qtd_caminhoes=Count("caminhoes", filter=Q(caminhoes__ativo=True), distinct=True),
            vol_entregue=Sum("caminhoes__volume_entregue", filter=Q(caminhoes__ativo=True)),
        )
        .select_related("concreteira").prefetch_related("itens_planejados__local")
        .order_by("horario_programado")
    )
