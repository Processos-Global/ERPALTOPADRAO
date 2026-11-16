"""Agenda interna e indicadores da concretagem."""
import datetime

from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import Fornecedor
from obras.models import Concretagem, Obra
from obras.services.concretagem import agenda as agenda_svc
from obras.services.concretagem import indicadores as ind
from obras.services.concretagem.permissoes import contexto_permissoes, eh_gerente, ver_required

MESES = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro")


def _int(valor):
    return int(valor) if valor and str(valor).isdigit() else None


@ver_required
def agenda(request):
    hoje = timezone.localdate()
    try:
        ano, mes = (int(x) for x in (request.GET.get("mes") or "").split("-"))
        datetime.date(ano, mes, 1)
    except ValueError:
        ano, mes = hoje.year, hoje.month
    obra_id = _int(request.GET.get("obra"))
    anterior = datetime.date(ano, mes, 1) - datetime.timedelta(days=1)
    proximo = datetime.date(ano + (mes == 12), mes % 12 + 1, 1)
    return render(request, "obras/concretagem/agenda.html", {
        "semanas": agenda_svc.montar_mes(ano, mes, obra_id),
        "titulo_mes": f"{MESES[mes - 1]} de {ano}",
        "mes_anterior": f"{anterior.year}-{anterior.month:02d}",
        "mes_proximo": f"{proximo.year}-{proximo.month:02d}",
        "mes_atual": f"{hoje.year}-{hoje.month:02d}",
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "obra_filtro": obra_id,
        "cps_a_enviar": agenda_svc.cps_a_enviar(obra_id),
        "dias_semana": ("Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"),
        **contexto_permissoes(request.user),
    })


@ver_required
def indicadores(request):
    hoje = timezone.localdate()
    try:
        inicio = datetime.date.fromisoformat(request.GET.get("inicio") or "")
    except ValueError:
        inicio = datetime.date(hoje.year, hoje.month, 1) - datetime.timedelta(days=150)
        inicio = inicio.replace(day=1)
    try:
        fim = datetime.date.fromisoformat(request.GET.get("fim") or "")
    except ValueError:
        fim = hoje + datetime.timedelta(days=30)
    if fim < inicio:
        inicio, fim = fim, inicio
    obra_id = _int(request.GET.get("obra"))
    concreteira_id = _int(request.GET.get("concreteira"))
    gerente = eh_gerente(request.user)
    aba = request.GET.get("aba") or "geral"
    if aba == "uso" and not gerente:
        raise PermissionDenied("O indicador de uso exige a permissão Concretagem.")
    dados = ind.calcular(inicio, fim, obra_id, concreteira_id)
    concreteiras_ids = Concretagem.objects.exclude(concreteira=None).values("concreteira_id")
    return render(request, "obras/concretagem/indicadores.html", {
        "dados": dados,
        "graficos": {k: dados[k] for k in ("serie_mensal", "destinos_sobra", "laudos_idade", "por_tipo")},
        "uso": ind.calcular_uso(inicio, fim, obra_id, concreteira_id) if gerente and aba == "uso" else None,
        "aba": aba,
        "inicio": inicio, "fim": fim,
        "obras": Obra.objects.filter(ativa=True).order_by("nome"),
        "concreteiras": Fornecedor.objects.filter(pk__in=concreteiras_ids).order_by("nome"),
        "obra_filtro": obra_id, "concreteira_filtro": concreteira_id,
        **contexto_permissoes(request.user),
    })


@ver_required
def api_concretagens_dia(request):
    """JSON para o quadro “Concretagens do dia” do Diário de Obra."""
    from django.http import JsonResponse
    from django.urls import reverse

    obra_id = _int(request.GET.get("obra"))
    try:
        data = datetime.date.fromisoformat(request.GET.get("data") or "")
    except ValueError:
        return JsonResponse({"concretagens": []})
    if not obra_id:
        return JsonResponse({"concretagens": []})
    return JsonResponse({"concretagens": [
        {
            "codigo": c.codigo, "status": c.get_status_display(), "status_codigo": c.status,
            "horario": c.horario_programado.strftime("%H:%M") if c.horario_programado else "",
            "servico": c.descricao_servico(), "concreteira": c.concreteira_nome,
            "solicitado": str(c.volume_solicitado or ""), "entregue": str(c.vol_entregue or ""),
            "caminhoes": c.qtd_caminhoes, "url": reverse("obras:concretagem_detalhe", args=[c.pk]),
        }
        for c in agenda_svc.concretagens_do_dia(obra_id, data)
    ]})
