from django.db import transaction
from django.utils import timezone

from financeiro.models import SequenciaFinanceira, TituloPagar


PREFIXOS = {
    "TITULO": "FIN",
    "LOTE": "PAG",
    "RELATORIO_PAGAMENTO": "RPG",
}


@transaction.atomic
def gerar_numero(tipo):
    ano = timezone.localdate().year
    sequencia, _ = SequenciaFinanceira.objects.select_for_update().get_or_create(
        tipo=tipo,
        ano=ano,
        defaults={"ultimo_numero": 0},
    )
    ultimo = sequencia.ultimo_numero + 1
    numero = f"{PREFIXOS[tipo]}-{ano}-{ultimo:05d}"
    # Importações antigas podem ter gravado números sem avançar a sequência.
    while tipo == "TITULO" and TituloPagar.objects.filter(numero=numero).exists():
        ultimo += 1
        numero = f"{PREFIXOS[tipo]}-{ano}-{ultimo:05d}"
    sequencia.ultimo_numero = ultimo
    sequencia.save(update_fields=["ultimo_numero"])
    return numero
