from orcamento.models import InsumoOrcamento


def listar_insumos_obra(obra):
    return (
        InsumoOrcamento.objects
        .filter(obra=obra, tipo=InsumoOrcamento.Tipo.INSUMO)
        .order_by("codigo")
    )


def alternar_mao_de_obra(insumo: InsumoOrcamento) -> InsumoOrcamento:
    """
    Alterna a flag de mão de obra do insumo.

    Como InsumoOrcamento já é o próprio item do orçamento (não existe uma
    tabela separada de "itens promovidos"), só trocar a flag já é
    suficiente para o item aparecer/deixar de aparecer no total de mão de
    obra da árvore do orçamento.
    """
    insumo.mao_de_obra = not insumo.mao_de_obra
    insumo.save(update_fields=["mao_de_obra", "atualizado_em"])
    return insumo
