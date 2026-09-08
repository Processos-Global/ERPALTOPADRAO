from decimal import Decimal

from financeiro.models import TituloPagar


TOLERANCIA = Decimal("0.01")


def avaliar_conferencia(titulo):
    """Compara NF, valores recebidos e pedido sem bloquear divergências reais."""
    if not titulo.recebimento_id:
        return {
            "status": TituloPagar.Conferencia.NAO_CONFERIDO,
            "motivo": "Título sem recebimento vinculado.",
            "pedido": None,
            "nota": titulo.valor_original,
            "recebido": None,
        }

    recebimento = titulo.recebimento
    nota = recebimento.valor_total_nota or titulo.valor_original
    recebido = recebimento.valor_itens_recebidos
    pedido = recebimento.pedido.valor_total if recebimento.pedido_id else None

    if recebido and abs(nota - recebido) > TOLERANCIA:
        return {
            "status": TituloPagar.Conferencia.DIVERGENCIA,
            "motivo": "O valor da nota fiscal diverge do valor informado nos itens recebidos.",
            "pedido": pedido,
            "nota": nota,
            "recebido": recebido,
        }

    return {
        "status": TituloPagar.Conferencia.CONFERIDO,
        "motivo": "Documento e recebimento conferidos.",
        "pedido": pedido,
        "nota": nota,
        "recebido": recebido or None,
    }
