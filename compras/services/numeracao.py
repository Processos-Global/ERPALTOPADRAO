from django.db import transaction
from django.utils import timezone
from compras.models import SequenciaDocumentoCompra

@transaction.atomic
def gerar_numero(tipo: str) -> str:
    ano = timezone.localdate().year
    seq, _ = SequenciaDocumentoCompra.objects.select_for_update().get_or_create(tipo=tipo, ano=ano)
    seq.ultimo_numero += 1
    seq.save(update_fields=["ultimo_numero"])
    prefixo = {"PROCESSO": "PC", "PEDIDO": "PED"}[tipo]
    return f"{prefixo}-{ano}-{seq.ultimo_numero:04d}"
