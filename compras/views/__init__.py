from .menu import menu_suprimentos
from .processos import dashboard, detalhe_processo, lista_pedidos, lista_processos, novo_processo
from .acoes import (
    acao_adjudicar,
    acao_aprovar,
    acao_cancelar_adjudicacao,
    acao_compatibilizar,
    acao_concluir_compatibilizacao,
    acao_concluir_cotacao,
    acao_concluir_negociacao,
    acao_criar_fornecedor,
    acao_formalizar,
    acao_gerar_pedidos,
    acao_incluir_cotacao,
    acao_incluir_item_cotacao,
    acao_incluir_necessidade,
    acao_negociar,
    acao_atualizar_status_pedido,
    acao_atualizar_previsao_pedido,
    acao_receber_pedido,
    acao_cancelar_pedido,
)

__all__ = [name for name in globals() if not name.startswith("_")]
