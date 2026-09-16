from django.db import transaction
from django.utils import timezone

from financeiro.models import TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.numeracao import gerar_numero


@transaction.atomic
def criar_titulo_manual(*, usuario=None, **dados):
    fornecedor = dados.get("fornecedor")
    if fornecedor and not dados.get("beneficiario_nome"):
        dados["beneficiario_nome"] = getattr(fornecedor, "nome_exibicao", None) or str(fornecedor)

    titulo = TituloPagar.objects.create(
        numero=gerar_numero("TITULO"),
        origem=TituloPagar.Origem.MANUAL,
        status=TituloPagar.Status.AGUARDANDO_APROVACAO,
        ciclo_aprovacao=1,
        criado_por=usuario,
        **dados,
    )
    registrar_evento(titulo, "CRIADO_MANUAL", "Conta a Pagar criada manualmente e enviada para aprovação.", usuario)
    return titulo


@transaction.atomic
def atualizar_titulo(titulo, *, usuario, dados, motivo="Dados da Conta a Pagar atualizados."):
    criticos = {
        "valor_original",
        "desconto",
        "juros",
        "multa",
        "outros_acrescimos",
        "vencimento",
        "fornecedor",
        "beneficiario_nome",
        "beneficiario_documento",
        "obra",
    }
    alterou_critico = False
    for campo, valor in dados.items():
        if getattr(titulo, campo) != valor:
            if campo in criticos:
                alterou_critico = True
            setattr(titulo, campo, valor)

    if titulo.fornecedor_id and not titulo.beneficiario_nome:
        titulo.beneficiario_nome = getattr(titulo.fornecedor, "nome_exibicao", None) or str(titulo.fornecedor)

    if alterou_critico and titulo.status in {TituloPagar.Status.APROVADO, TituloPagar.Status.REJEITADO}:
        titulo.ciclo_aprovacao += 1
        titulo.status = TituloPagar.Status.AGUARDANDO_APROVACAO
        registrar_evento(
            titulo,
            "APROVACAO_REABERTA",
            "A Conta a Pagar voltou para aprovação porque dados financeiros foram alterados.",
            usuario,
        )

    titulo.save()
    registrar_evento(titulo, "ATUALIZADO", motivo, usuario)
    return titulo


@transaction.atomic
def cancelar_titulo(titulo, *, usuario, motivo):
    if titulo.status == TituloPagar.Status.PAGO:
        raise ValueError("Conta paga não pode ser cancelada. Estorne o pagamento primeiro.")
    titulo.status = TituloPagar.Status.CANCELADO
    titulo.cancelado_em = timezone.now()
    titulo.save(update_fields=["status", "cancelado_em", "atualizado_em"])
    registrar_evento(titulo, "CANCELADO", motivo or "Conta a Pagar cancelada.", usuario)
    return titulo
