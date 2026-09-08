from django.db import transaction
from django.utils import timezone

from financeiro.models import PrevisaoFinanceira, TituloPagar
from financeiro.services.auditoria import registrar_evento
from financeiro.services.matching import avaliar_conferencia
from financeiro.services.numeracao import gerar_numero


@transaction.atomic
def criar_titulo_manual(*, usuario=None, **dados):
    titulo = TituloPagar.objects.create(
        numero=gerar_numero("TITULO"),
        criado_por=usuario,
        **dados,
    )
    registrar_evento(titulo, "CRIADO", "Título criado manualmente.", usuario)
    return titulo


@transaction.atomic
def criar_ou_atualizar_titulo_recebimento(recebimento):
    valor = recebimento.valor_total_nota
    if not valor:
        return None

    pedido = recebimento.pedido
    titulo = TituloPagar.objects.filter(recebimento=recebimento).first()
    criado = titulo is None
    if criado:
        titulo = TituloPagar(
            numero=gerar_numero("TITULO"),
            recebimento=recebimento,
            pedido=pedido,
            origem=TituloPagar.Origem.COMPRA,
            fornecedor=pedido.fornecedor,
            obra=pedido.obra,
            descricao=f"NF {recebimento.numero_nota_fiscal or 's/n'} · {pedido.fornecedor.nome_exibicao}",
            documento_numero=recebimento.numero_nota_fiscal or "",
            valor_original=valor,
            status=TituloPagar.Status.DOCUMENTO_RECEBIDO,
            criado_por=recebimento.usuario,
        )
        previsao = pedido.previsoes_financeiras.filter(ativa=True, titulos_gerados__isnull=True).order_by("data_prevista", "id").first()
        if previsao:
            titulo.previsao_origem = previsao
            titulo.vencimento = previsao.data_prevista
            titulo.plano_financeiro = previsao.plano_financeiro
        titulo.save()
    else:
        campos_criticos = []
        if titulo.status in {TituloPagar.Status.RASCUNHO, TituloPagar.Status.DOCUMENTO_RECEBIDO, TituloPagar.Status.EM_CONFERENCIA}:
            if titulo.valor_original != valor:
                titulo.valor_original = valor
                campos_criticos.append("valor_original")
            titulo.documento_numero = recebimento.numero_nota_fiscal or titulo.documento_numero
            titulo.save(update_fields=["valor_original", "documento_numero", "atualizado_em"])

    resultado = avaliar_conferencia(titulo)
    titulo.conferencia = resultado["status"]
    if titulo.status == TituloPagar.Status.DOCUMENTO_RECEBIDO:
        titulo.status = TituloPagar.Status.EM_CONFERENCIA
    titulo.save(update_fields=["conferencia", "status", "atualizado_em"])

    registrar_evento(
        titulo,
        "CRIADO_RECEBIMENTO" if criado else "SINCRONIZADO_RECEBIMENTO",
        resultado["motivo"],
        recebimento.usuario,
        dados={
            "nota": str(resultado.get("nota") or ""),
            "recebido": str(resultado.get("recebido") or ""),
            "pedido": str(resultado.get("pedido") or ""),
        },
    )
    return titulo


@transaction.atomic
def atualizar_titulo(titulo, *, usuario, dados, motivo="Dados do título atualizados."):
    criticos = {"valor_original", "desconto", "juros", "multa", "outros_acrescimos", "vencimento", "fornecedor", "obra"}
    alterou_critico = False
    for campo, valor in dados.items():
        if getattr(titulo, campo) != valor:
            if campo in criticos:
                alterou_critico = True
            setattr(titulo, campo, valor)

    if alterou_critico and titulo.status in {TituloPagar.Status.AGUARDANDO_APROVACAO, TituloPagar.Status.APROVADO}:
        titulo.ciclo_aprovacao += 1
        titulo.status = TituloPagar.Status.EM_CONFERENCIA
        registrar_evento(titulo, "APROVACAO_INVALIDADA", "A aprovação foi invalidada porque dados financeiros relevantes foram alterados.", usuario)

    titulo.save()
    registrar_evento(titulo, "ATUALIZADO", motivo, usuario)
    return titulo


@transaction.atomic
def cancelar_titulo(titulo, *, usuario, motivo):
    if titulo.status == TituloPagar.Status.PAGO:
        raise ValueError("Título pago não pode ser cancelado. Estorne os pagamentos primeiro.")
    titulo.status = TituloPagar.Status.CANCELADO
    titulo.cancelado_em = timezone.now()
    titulo.save(update_fields=["status", "cancelado_em", "atualizado_em"])
    registrar_evento(titulo, "CANCELADO", motivo or "Título cancelado.", usuario)
    return titulo
