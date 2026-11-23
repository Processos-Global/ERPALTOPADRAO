"""Prazos de Compras baseados em regras versionadas e transições efetivas."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone

from compras.models.pedido import PedidoCompra
from compras.models.sla import PrazoEntregaPedido, RegraPrazoCompra, TransicaoEtapaCompra
from compras.services.permissoes import possui_acao_compras
from usuarios.models import AcaoCompra


TERMINAIS = {"CONTRATADO", "CANCELADO", "REPROVADO"}


def _data_referencia(valor):
    return timezone.localtime(valor).date() if hasattr(valor, "hour") else valor


def _somar_dias(inicio, dias, contagem):
    if contagem == RegraPrazoCompra.Contagem.CORRIDOS:
        return inicio + timedelta(days=dias)
    atual = inicio
    restante = dias
    while restante:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            restante -= 1
    return atual


def _dias_decorridos(inicio, fim, contagem):
    if contagem == RegraPrazoCompra.Contagem.CORRIDOS:
        return max((fim - inicio).days, 0)
    atual = inicio
    total = 0
    while atual < fim:
        atual += timedelta(days=1)
        total += atual.weekday() < 5
    return total


def selecionar_regra(processo, *, escopo, etapa="", referencia=None, material_ids=None):
    referencia = referencia or timezone.localdate()
    tipo = (RegraPrazoCompra.TipoFornecedor.GRANDE if processo.fluxo_grande_fornecedor
            else RegraPrazoCompra.TipoFornecedor.COMUM)
    qs = RegraPrazoCompra.objects.filter(
        escopo=escopo, etapa=etapa, vigente_desde__lte=referencia,
    )
    from django.db.models import Q

    qs = qs.filter(Q(vigente_ate__isnull=True) | Q(vigente_ate__gte=referencia))
    qs = qs.filter(tipo_fornecedor__in=[RegraPrazoCompra.TipoFornecedor.TODOS, tipo])
    qs = qs.filter(Q(categoria__isnull=True) | Q(categoria_id=processo.categoria_grande_fornecedor_id))
    materiais = (set(material_ids) if material_ids is not None else
                set(processo.necessidades.exclude(material_id__isnull=True).values_list("material_id", flat=True)))
    material_unico = next(iter(materiais)) if len(materiais) == 1 else None
    qs = qs.filter(Q(material__isnull=True) | Q(material_id=material_unico))
    regras = list(qs)
    regras.sort(key=lambda r: (
        bool(r.material_id), bool(r.categoria_id), r.tipo_fornecedor != RegraPrazoCompra.TipoFornecedor.TODOS,
        r.vigente_desde, r.pk,
    ), reverse=True)
    return regras[0] if regras else None


def criar_regra_prazo(*, usuario, **campos):
    if not possui_acao_compras(usuario, AcaoCompra.ADMINISTRAR):
        raise PermissionDenied("Somente administradores de Compras podem configurar prazos.")
    campos["criado_por"] = usuario
    return RegraPrazoCompra.objects.create(**campos)


def registrar_prazo_entrega(pedido):
    """Congela o prazo comercial vigente depois de gravar os itens do pedido."""
    existente = PrazoEntregaPedido.objects.filter(pedido=pedido).first()
    if existente:
        return existente
    materiais = set(pedido.itens.exclude(necessidade__material_id__isnull=True).values_list(
        "necessidade__material_id", flat=True
    ))
    regra = selecionar_regra(
        pedido.processo, escopo=RegraPrazoCompra.Escopo.ENTREGA,
        referencia=pedido.data, material_ids=materiais,
    )
    return PrazoEntregaPedido.objects.create(
        pedido=pedido, regra=regra, prazo_dias=regra.dias if regra else None,
        contagem=regra.contagem if regra else "",
        limite_em=_somar_dias(pedido.data, regra.dias, regra.contagem) if regra else None,
    )


def reconciliar_regra_inicial(processo):
    """Finaliza o snapshot da abertura após gravar os materiais na mesma transação."""
    passagem = processo.transicoes_sla.filter(etapa=processo.etapa_atual, encerrada_em__isnull=True).first()
    if not passagem or passagem.motivo != "ABERTURA":
        return
    regra = selecionar_regra(processo, escopo=RegraPrazoCompra.Escopo.ETAPA,
                             etapa=processo.etapa_atual, referencia=_data_referencia(passagem.iniciada_em))
    if passagem.regra_id == (regra.pk if regra else None):
        return
    passagem.regra = regra
    passagem.prazo_dias = regra.dias if regra else None
    passagem.contagem = regra.contagem if regra else ""
    passagem.dias_alerta = regra.dias_alerta if regra else None
    passagem.limite_em = _somar_dias(_data_referencia(passagem.iniciada_em), regra.dias, regra.contagem) if regra else None
    passagem.save(update_fields=["regra", "prazo_dias", "contagem", "dias_alerta", "limite_em"])


def _abrir_passagem(processo, *, etapa, agora, usuario=None, anterior="", motivo=""):
    regra = selecionar_regra(processo, escopo=(
        RegraPrazoCompra.Escopo.PROCESSO if etapa == "PROCESSO" else RegraPrazoCompra.Escopo.ETAPA
    ), etapa="" if etapa == "PROCESSO" else etapa, referencia=_data_referencia(agora))
    return TransicaoEtapaCompra.objects.create(
        processo=processo, etapa=etapa, etapa_anterior=anterior, motivo=motivo,
        iniciada_em=agora, usuario=usuario, regra=regra,
        prazo_dias=regra.dias if regra else None,
        contagem=regra.contagem if regra else "",
        dias_alerta=regra.dias_alerta if regra else None,
        limite_em=_somar_dias(_data_referencia(agora), regra.dias, regra.contagem) if regra else None,
    )


def registrar_mudanca_processo(processo, *, criado=False, etapa_anterior="", status_anterior="", usuario=None):
    """Executada na transação do save; não reconstrói passagens anteriores."""
    agora = timezone.now()
    if criado:
        _abrir_passagem(processo, etapa="PROCESSO", agora=agora, usuario=usuario, motivo="ABERTURA")
        if processo.status not in TERMINAIS:
            _abrir_passagem(processo, etapa=processo.etapa_atual, agora=agora, usuario=usuario, motivo="ABERTURA")
        return
    mudou_etapa = etapa_anterior != processo.etapa_atual
    terminou = status_anterior not in TERMINAIS and processo.status in TERMINAIS
    reabriu = status_anterior in TERMINAIS and processo.status not in TERMINAIS
    if not (mudou_etapa or terminou or reabriu):
        return
    if mudou_etapa or terminou:
        TransicaoEtapaCompra.objects.filter(
            processo=processo, etapa=etapa_anterior, encerrada_em__isnull=True,
        ).update(encerrada_em=agora)
    if terminou:
        TransicaoEtapaCompra.objects.filter(processo=processo, etapa="PROCESSO", encerrada_em__isnull=True).update(encerrada_em=agora)
    if reabriu and not TransicaoEtapaCompra.objects.filter(processo=processo, etapa="PROCESSO", encerrada_em__isnull=True).exists():
        _abrir_passagem(processo, etapa="PROCESSO", agora=agora, usuario=usuario, motivo="REABERTURA")
    if processo.status not in TERMINAIS and (mudou_etapa or reabriu):
        ordem = {etapa: indice for indice, etapa in enumerate(processo.Etapa.values)}
        _abrir_passagem(processo, etapa=processo.etapa_atual, agora=agora, usuario=usuario,
                       anterior=etapa_anterior, motivo="RETORNO" if reabriu or ordem.get(etapa_anterior, 0) > ordem.get(processo.etapa_atual, 0) else "TRANSICAO")


def _indicador_passagem(passagem, referencia):
    if not passagem:
        return {"situacao": "SEM_HISTORICO", "rotulo": "Prazo indisponível", "limite": None,
                "decorridos": None, "permitidos": None, "restantes": None, "atraso": None}
    fim = _data_referencia(passagem.encerrada_em or referencia)
    inicio = _data_referencia(passagem.iniciada_em)
    decorridos = _dias_decorridos(inicio, fim, passagem.contagem or RegraPrazoCompra.Contagem.CORRIDOS)
    if not passagem.limite_em:
        return {"situacao": "SEM_REGRA", "rotulo": "Sem prazo configurado", "limite": None,
                "decorridos": decorridos, "permitidos": None, "restantes": None, "atraso": None}
    restantes = passagem.prazo_dias - decorridos
    atraso = max(-restantes, 0)
    if passagem.encerrada_em:
        situacao = "CONCLUIDO_ATRASADO" if atraso else "CONCLUIDO_PRAZO"
        rotulo = "Concluído com atraso" if atraso else "Concluído no prazo"
    elif atraso:
        situacao, rotulo = "ATRASADO", "Atrasado"
    elif restantes <= (passagem.dias_alerta or 0):
        situacao, rotulo = "PROXIMO", "Próximo do limite"
    else:
        situacao, rotulo = "NO_PRAZO", "Dentro do prazo"
    return {"situacao": situacao, "rotulo": rotulo, "limite": passagem.limite_em,
            "decorridos": decorridos, "permitidos": passagem.prazo_dias,
            "restantes": max(restantes, 0), "atraso": atraso, "contagem": passagem.contagem}


def indicador_processo(processo, referencia=None):
    referencia = referencia or timezone.now()
    passagens = list(processo.transicoes_sla.all())
    etapa = next((p for p in reversed(passagens) if p.etapa == processo.etapa_atual), None)
    if etapa is None and processo.status in TERMINAIS:
        etapa = next((p for p in reversed(passagens) if p.etapa != "PROCESSO"), None)
    geral = next((p for p in reversed(passagens) if p.etapa == "PROCESSO"), None)
    etapa_indicador = _indicador_passagem(etapa, referencia)
    geral_indicador = _indicador_passagem(geral, referencia)
    if processo.status in {processo.Status.CANCELADO, processo.Status.REPROVADO}:
        for indicador in (etapa_indicador, geral_indicador):
            if indicador["situacao"] in {"CONCLUIDO_PRAZO", "CONCLUIDO_ATRASADO"}:
                indicador["situacao"] = "ENCERRADO"
                indicador["rotulo"] = "Encerrado sem contratação"
    return {"etapa": etapa_indicador, "geral": geral_indicador, "passagens": passagens}


def indicador_pedido(pedido, referencia=None):
    referencia = _data_referencia(referencia or timezone.now())
    prevista_contratual = pedido.previsao_entrega_atual or pedido.previsao_entrega_original
    try:
        prazo_regra = pedido.prazo_sla
    except PrazoEntregaPedido.DoesNotExist:
        prazo_regra = None
    prevista = prevista_contratual or (prazo_regra.limite_em if prazo_regra else None)
    realizada = _data_referencia(pedido.recebido_em) if pedido.recebido_em else None
    if pedido.status == pedido.Status.CANCELADO or not prevista:
        situacao, atraso = ("CANCELADO" if pedido.status == pedido.Status.CANCELADO else "SEM_PRAZO"), None
    else:
        atraso = max(((realizada or referencia) - prevista).days, 0)
        situacao = ("ENTREGUE_ATRASADO" if atraso else "ENTREGUE_PRAZO") if realizada else ("ATRASADO" if atraso else "NO_PRAZO")
    return {"situacao": situacao, "previsao": prevista, "realizada": realizada,
            "dias_atraso_comercial": atraso, "data_necessaria_obra": None,
            "defasagem_necessidade": None,
            "origem_previsao": "CONTRATUAL" if prevista_contratual else ("REGRA" if prevista else "INDEFINIDA"),
            "limite_regra_comercial": prazo_regra.limite_em if prazo_regra else None,
            "prazo_regra_dias": prazo_regra.prazo_dias if prazo_regra else None}


def resumo_sla_processos(queryset, referencia=None, *, situacao_etapa=""):
    referencia = referencia or timezone.now()
    if hasattr(queryset, "prefetch_related"):
        processos = list(queryset.prefetch_related("transicoes_sla"))
    else:
        processos = list(queryset)
        prefetch_related_objects(processos, "transicoes_sla")
    indicadores = {p.pk: indicador_processo(p, referencia) for p in processos}
    if situacao_etapa:
        processos = [p for p in processos if indicadores[p.pk]["etapa"]["situacao"] == situacao_etapa]
        indicadores = {p.pk: indicadores[p.pk] for p in processos}
    prefetch_related_objects(
        processos,
        Prefetch("pedidos", queryset=PedidoCompra.objects.select_related("prazo_sla")),
    )
    etapas = [passagem for p in processos for passagem in indicadores[p.pk]["passagens"] if passagem.etapa != "PROCESSO"]
    atrasos = [indicadores[p.pk]["etapa"]["atraso"] or 0 for p in processos
               if indicadores[p.pk]["etapa"]["situacao"] == "ATRASADO"]
    pedidos = [indicador_pedido(pedido, referencia) for processo in processos for pedido in processo.pedidos.all()]
    medias_etapas = {}
    for etapa in sorted({passagem.etapa for passagem in etapas}):
        valores = [_indicador_passagem(p, referencia)["decorridos"] for p in etapas if p.etapa == etapa and p.encerrada_em]
        if valores:
            medias_etapas[etapa] = round(sum(valores) / len(valores), 1)
    gerais = [_indicador_passagem(passagem, referencia)["decorridos"]
              for processo in processos for passagem in indicadores[processo.pk]["passagens"]
              if processo.status == processo.Status.CONTRATADO
              and passagem.etapa == "PROCESSO" and passagem.encerrada_em]
    return {"indicadores": indicadores,
            "processos_atrasados": len(atrasos), "processos_proximos": sum(
                indicadores[p.pk]["etapa"]["situacao"] == "PROXIMO" for p in processos),
            "pedidos_atrasados": sum(p["situacao"] == "ATRASADO" for p in pedidos),
            "maior_atraso": max(atrasos, default=0),
            "media_contratacao": round(sum(gerais) / len(gerais), 1) if gerais else None,
            "medias_etapas": medias_etapas}
