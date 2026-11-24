"""Prazos de Compras baseados em regras versionadas e transições efetivas."""

from datetime import timedelta
from itertools import groupby
from operator import itemgetter
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.db.models.functions import Coalesce
from django.utils import timezone

from compras.models.pedido import PedidoCompra
from compras.models.sla import PrazoEntregaPedido, RegraPrazoCompra, TransicaoEtapaCompra
from compras.services.permissoes import possui_acao_compras
from usuarios.models import AcaoCompra

from .integracao_planejamento import data_necessaria_processo


TERMINAIS = {"CONTRATADO", "CANCELADO", "REPROVADO"}
ROTULOS_PRAZO_PEDIDO = {
    "CANCELADO": "Cancelado",
    "SEM_DATA_ENTREGA": "Entrega sem data registrada",
    "SEM_PRAZO": "Prazo indefinido",
    "NO_PRAZO": "Em aberto, dentro do prazo",
    "ATRASADO": "Em aberto, em atraso",
    "ENTREGUE_PRAZO": "Entregue no prazo",
    "ENTREGUE_ATRASADO": "Entregue com atraso",
}


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
                "decorridos": None, "permitidos": None, "restantes": None, "atraso": None,
                "iniciada_em": None, "encerrada_em": None}
    fim = _data_referencia(passagem.encerrada_em or referencia)
    inicio = _data_referencia(passagem.iniciada_em)
    decorridos = _dias_decorridos(inicio, fim, passagem.contagem or RegraPrazoCompra.Contagem.CORRIDOS)
    if not passagem.limite_em:
        return {"situacao": "SEM_REGRA", "rotulo": "Sem prazo configurado", "limite": None,
                "decorridos": decorridos, "permitidos": None, "restantes": None, "atraso": None,
                "iniciada_em": passagem.iniciada_em, "encerrada_em": passagem.encerrada_em}
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
            "restantes": max(restantes, 0), "atraso": atraso, "contagem": passagem.contagem,
            "iniciada_em": passagem.iniciada_em, "encerrada_em": passagem.encerrada_em}


def _indicador_processo_passagem(passagem, status, referencia):
    indicador = _indicador_passagem(passagem, referencia)
    if status in {"CANCELADO", "REPROVADO"} and indicador["situacao"] in {
        "CONCLUIDO_PRAZO", "CONCLUIDO_ATRASADO",
    }:
        indicador["situacao"] = "ENCERRADO"
        indicador["rotulo"] = "Encerrado sem contratação"
    return indicador


def _passagem_etapa(ultimas_passagens, etapa_atual, status):
    etapa = ultimas_passagens.get(etapa_atual)
    if etapa is None and status in TERMINAIS:
        return max(
            (p for nome, p in ultimas_passagens.items() if nome != "PROCESSO"),
            key=lambda p: (p.iniciada_em, p.pk),
            default=None,
        )
    return etapa


def indicador_processo(processo, referencia=None):
    referencia = referencia or timezone.now()
    passagens = list(processo.transicoes_sla.all())
    ultimas = {p.etapa: p for p in passagens}
    etapa = _passagem_etapa(ultimas, processo.etapa_atual, processo.status)
    etapa_indicador = _indicador_processo_passagem(etapa, processo.status, referencia)
    geral_indicador = _indicador_processo_passagem(ultimas.get("PROCESSO"), processo.status, referencia)
    return {"etapa": etapa_indicador, "geral": geral_indicador, "passagens": passagens}


def resumir_sla_listagem(queryset, referencia, *, situacao_etapa=""):
    """Consome os campos de SLA em ordem de processo, sem instanciar os modelos."""
    campos = ("pk", "etapa", "iniciada_em", "encerrada_em", "contagem", "limite_em", "prazo_dias", "dias_alerta")
    linhas = queryset.order_by("pk", "transicoes_sla__iniciada_em", "transicoes_sla__pk").values_list(
        "pk", "status", "etapa_atual", *(f"transicoes_sla__{campo}" for campo in campos),
    ).iterator()
    ids_filtrados = [] if situacao_etapa else None
    totais_etapas = {}
    total_geral = qtd_geral = atrasados = proximos = maior_atraso = 0
    for (pk, status, etapa_atual), grupo in groupby(linhas, key=itemgetter(0, 1, 2)):
        ultimas = {}
        concluidas = []
        for _, _, _, *dados in grupo:
            if dados[0] is None:
                continue
            passagem = SimpleNamespace(**dict(zip(campos, dados)))
            ultimas[passagem.etapa] = passagem
            if passagem.encerrada_em:
                concluidas.append(passagem)
        etapa = _passagem_etapa(ultimas, etapa_atual, status)
        indicador = _indicador_processo_passagem(etapa, status, referencia)
        situacao = indicador["situacao"]
        if situacao_etapa:
            if situacao != situacao_etapa:
                continue
            ids_filtrados.append(pk)
        if situacao == "ATRASADO":
            atrasados += 1
            maior_atraso = max(maior_atraso, indicador["atraso"])
        proximos += situacao == "PROXIMO"
        for passagem in concluidas:
            if passagem.etapa != "PROCESSO" or status == "CONTRATADO":
                dias = _indicador_passagem(passagem, referencia)["decorridos"]
                if passagem.etapa == "PROCESSO":
                    total_geral += dias
                    qtd_geral += 1
                else:
                    total, qtd = totais_etapas.get(passagem.etapa, (0, 0))
                    totais_etapas[passagem.etapa] = total + dias, qtd + 1

    if ids_filtrados is not None:
        queryset = queryset.filter(pk__in=ids_filtrados)
    pedidos_atrasados = (
        PedidoCompra.objects.filter(processo_id__in=queryset.order_by().values("pk"), recebido_em__isnull=True)
        .exclude(status__in=(PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE))
        .alias(previsao_sla=Coalesce("previsao_entrega_atual", "previsao_entrega_original", "prazo_sla__limite_em"))
        .filter(previsao_sla__lt=_data_referencia(referencia))
        .count()
    )
    return queryset, {
        "processos_atrasados": atrasados,
        "processos_proximos": proximos,
        "pedidos_atrasados": pedidos_atrasados,
        "maior_atraso": maior_atraso,
        "media_contratacao": round(total_geral / qtd_geral, 1) if qtd_geral else None,
        "medias_etapas": {etapa: round(total / qtd, 1) for etapa, (total, qtd) in sorted(totais_etapas.items())},
    }


def impacto_na_obra(*, necessaria, previsao, realizada, referencia, cancelado=False, entregue=False):
    if cancelado:
        return None, "Cancelado"
    if not necessaria:
        return None, "Data necessária indefinida"
    if realizada:
        desvio = (realizada - necessaria).days
        return desvio, "Entregue após a data necessária" if desvio > 0 else "Entregue até a data necessária"
    if entregue:
        return None, "Entrega sem data registrada"
    if referencia > necessaria:
        return (referencia - necessaria).days, "Entrega pendente após a data necessária"
    if previsao:
        desvio = (previsao - necessaria).days
        return desvio, "Previsão após a data necessária" if desvio > 0 else "Previsão até a data necessária"
    return None, "Entrega pendente sem previsão"


def indicador_pedido(pedido, referencia=None):
    referencia = _data_referencia(referencia or timezone.now())
    prevista_contratual = pedido.previsao_entrega_atual or pedido.previsao_entrega_original
    try:
        prazo_regra = pedido.prazo_sla
    except PrazoEntregaPedido.DoesNotExist:
        prazo_regra = None
    prevista = prevista_contratual or (prazo_regra.limite_em if prazo_regra else None)
    realizada = _data_referencia(pedido.recebido_em) if pedido.recebido_em else None
    cancelado = pedido.status == pedido.Status.CANCELADO
    entregue = pedido.status == pedido.Status.ENTREGUE
    atraso = desvio_comercial = None
    if cancelado:
        situacao = "CANCELADO"
    elif entregue and not realizada:
        situacao = "SEM_DATA_ENTREGA"
    elif not prevista:
        situacao = "SEM_PRAZO"
    else:
        desvio = ((realizada or referencia) - prevista).days
        atraso = max(desvio, 0)
        desvio_comercial = desvio if realizada else (atraso or None)
        situacao = ("ENTREGUE_ATRASADO" if atraso else "ENTREGUE_PRAZO") if realizada else ("ATRASADO" if atraso else "NO_PRAZO")
    processo = pedido.processo
    necessaria = data_necessaria_processo(processo) if processo.obra_id == pedido.obra_id else None
    defasagem, situacao_obra = impacto_na_obra(
        necessaria=necessaria, previsao=prevista_contratual, realizada=realizada,
        referencia=referencia, cancelado=cancelado, entregue=entregue,
    )
    return {"situacao": situacao, "rotulo_comercial": ROTULOS_PRAZO_PEDIDO[situacao],
            "previsao": prevista, "realizada": realizada,
            "dias_atraso_comercial": atraso, "dias_desvio_comercial": desvio_comercial,
            "data_necessaria_obra": necessaria, "defasagem_necessidade": defasagem,
            "situacao_obra": situacao_obra,
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
        Prefetch("pedidos", queryset=PedidoCompra.objects.select_related(
            "prazo_sla", "processo__item_cronograma__cronograma_obra",
        )),
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
