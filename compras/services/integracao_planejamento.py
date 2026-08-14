from django.db import transaction
from django.utils import timezone

MAPA = {
    "COTACAO": "data_real_cotacao",
    "COMPATIBILIZACAO": "data_real_compatibilizacao",
    "NEGOCIACAO": "data_real_negociacao",
    "CONTRATACAO": "data_real_contratacao",
}

@transaction.atomic
def sincronizar_data_real(processo, etapa, usuario=None, data=None):
    campo = MAPA.get(etapa)
    if not campo:
        return
    item = processo.item_cronograma.__class__.objects.select_for_update().get(pk=processo.item_cronograma_id)
    setattr(item, campo, data or timezone.localdate())
    # Quando Compras alimenta a data, ela deixa de ser uma edição manual da tela de Planejamento.
    item.datas_editadas_manualmente = False
    item.datas_editadas_por = None
    item.datas_editadas_em = None
    item.save(update_fields=[campo, "datas_editadas_manualmente", "datas_editadas_por", "datas_editadas_em"])
