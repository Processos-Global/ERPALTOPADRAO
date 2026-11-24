"""API pública para outros módulos criarem/atualizarem obrigações financeiras."""

from contextlib import contextmanager
from contextvars import ContextVar

from financeiro.services.previsoes import (
    sincronizar_conta_mao_obra,
    sincronizar_contas_grande_fornecedor,
    sincronizar_contas_pedido,
)

_sinais_pedido_adiados = ContextVar("sinais_financeiros_pedido_adiados", default=False)


@contextmanager
def adiar_sinais_financeiros_pedido():
    """Permite gravar pedido, itens e parcelas antes da sincronização explícita."""
    token = _sinais_pedido_adiados.set(True)
    try:
        yield
    finally:
        _sinais_pedido_adiados.reset(token)


def sinais_financeiros_pedido_adiados():
    return _sinais_pedido_adiados.get()


__all__ = [
    "adiar_sinais_financeiros_pedido",
    "sinais_financeiros_pedido_adiados",
    "sincronizar_conta_mao_obra",
    "sincronizar_contas_grande_fornecedor",
    "sincronizar_contas_pedido",
]
