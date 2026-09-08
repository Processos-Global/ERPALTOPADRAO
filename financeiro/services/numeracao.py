from django.db import transaction
from django.utils import timezone

from financeiro.models import SequenciaFinanceira


PREFIXOS = {
    "TITULO": "FIN",
    "LOTE": "PAG",
}


@transaction.atomic
def gerar_numero(tipo):
    ano = timezone.localdate().year
    sequencia, _ = SequenciaFinanceira.objects.select_for_update().get_or_create(
        tipo=tipo,
        ano=ano,
        defaults={"ultimo_numero": 0},
    )
    sequencia.ultimo_numero += 1
    sequencia.save(update_fields=["ultimo_numero"])
    return f"{PREFIXOS[tipo]}-{ano}-{sequencia.ultimo_numero:05d}"
