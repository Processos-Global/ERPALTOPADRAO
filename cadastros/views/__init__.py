from .cadastros import (
    fornecedor_editar,
    fornecedor_excluir,
    fornecedor_novo,
    fornecedores_lista,
    index,
    mao_obra_editar,
    mao_obra_excluir,
    mao_obra_lista,
    mao_obra_nova,
    material_editar,
    material_excluir,
    material_novo,
    materiais_lista,
)

__all__ = [name for name in globals() if not name.startswith("_")]
