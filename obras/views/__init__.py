from .menu import menu
from .ficha_tecnica import ficha_tecnica, ficha_tecnica_acao, fichas_tecnicas
from .estoque import (
    almoxarifado_dashboard,
    almoxarifado_obra,
    saida_estoque,
    transferencia_estoque,
)
from .diario import diario_editar, diario_lista, diario_novo

__all__ = [
    "menu",
    "ficha_tecnica", "ficha_tecnica_acao", "fichas_tecnicas",
    "almoxarifado_dashboard", "almoxarifado_obra", "saida_estoque", "transferencia_estoque",
    "diario_lista", "diario_novo", "diario_editar",
]
