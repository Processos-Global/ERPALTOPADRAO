from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import CompatibilizacaoItem
from .auditoria import registrar_evento


@transaction.atomic
def registrar_compatibilizacao(*, item_cotado, resultado, usuario, observacao="", ressalva_motivo=""):
    processo = item_cotado.cotacao.processo
    if processo.etapa_atual != processo.Etapa.COMPATIBILIZACAO:
        raise ValidationError("A análise técnica só pode ser registrada na etapa de análise técnica.")
    if resultado not in CompatibilizacaoItem.Resultado.values:
        raise ValidationError("Resultado de compatibilização inválido.")
    if resultado == CompatibilizacaoItem.Resultado.APROVADO_COM_RESSALVA and not ressalva_motivo.strip():
        raise ValidationError("Informe a ressalva para aprovação com ressalva.")
    registro = CompatibilizacaoItem.objects.create(
        item_cotado=item_cotado,
        resultado=resultado,
        responsavel=usuario,
        observacao=observacao,
        ressalva_motivo=ressalva_motivo,
    )
    registrar_evento(
        item_cotado.cotacao.processo,
        "COMPATIBILIZACAO_ITEM",
        usuario,
        f"{item_cotado.cotacao.fornecedor.nome} / {item_cotado.necessidade.descricao}: {registro.get_resultado_display()}.",
        {"compatibilizacao_id": registro.pk, "item_cotado_id": item_cotado.pk},
    )
    return registro
