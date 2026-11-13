from django.db import transaction
from django.utils import timezone


MAPA = {
    "COTACAO": "data_real_cotacao",
    "COMPATIBILIZACAO": "data_real_compatibilizacao",
    "NEGOCIACAO": "data_real_negociacao",
    "CONTRATACAO": "data_real_contratacao",
}


def _menor_data(data_atual, nova_data):
    """Mantém a primeira conclusão registrada para o suprimento."""
    if data_atual is None:
        return nova_data
    if nova_data is None:
        return data_atual
    return min(data_atual, nova_data)


@transaction.atomic
def sincronizar_data_real(processo, etapa, usuario=None, data=None):
    """
    Consolida no Cronograma de Suprimentos a primeira data em que qualquer
    processo ligado ao suprimento concluiu a etapa.

    Com múltiplos processos para o mesmo suprimento, uma compra nova nunca
    deve sobrescrever uma conclusão anterior com uma data mais recente.
    """
    campo = MAPA.get(etapa)
    if not campo or not processo.item_cronograma_id:
        return

    item = (
        processo.item_cronograma.__class__.objects
        .select_for_update()
        .get(pk=processo.item_cronograma_id)
    )

    nova_data = data or timezone.localdate()
    data_atual = getattr(item, campo)
    data_consolidada = _menor_data(data_atual, nova_data)

    if data_consolidada == data_atual and not item.datas_editadas_manualmente:
        return

    setattr(item, campo, data_consolidada)

    # Quando Compras alimenta a data, ela deixa de ser uma edição manual da
    # tela de Planejamento.
    item.datas_editadas_manualmente = False
    item.datas_editadas_por = None
    item.datas_editadas_em = None
    item.save(
        update_fields=[
            campo,
            "datas_editadas_manualmente",
            "datas_editadas_por",
            "datas_editadas_em",
        ]
    )


@transaction.atomic
def limpar_data_real(processo, etapa):
    """
    Remove a data realizada somente quando o suprimento possui apenas este
    processo de compra.

    Em um suprimento com histórico de múltiplas compras, a data é consolidada
    e representa que a etapa já foi atingida por pelo menos uma compra. Assim,
    retornar/cancelar uma compra individual não faz o Cronograma voltar no
    tempo nem apaga a conclusão registrada por outro processo.
    """
    campo = MAPA.get(etapa)
    if not campo or not processo.item_cronograma_id:
        return

    item = (
        processo.item_cronograma.__class__.objects
        .select_for_update()
        .get(pk=processo.item_cronograma_id)
    )

    outros_processos_existem = (
        processo.__class__.objects
        .filter(item_cronograma_id=processo.item_cronograma_id)
        .exclude(pk=processo.pk)
        .exists()
    )
    if outros_processos_existem:
        return

    setattr(item, campo, None)
    item.datas_editadas_manualmente = False
    item.datas_editadas_por = None
    item.datas_editadas_em = None
    item.save(
        update_fields=[
            campo,
            "datas_editadas_manualmente",
            "datas_editadas_por",
            "datas_editadas_em",
        ]
    )
