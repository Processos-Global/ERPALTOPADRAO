from collections import OrderedDict
from decimal import Decimal
import unicodedata

from django.db.models import Q

from compras.models import RecebimentoPedidoItem
from obras.models import MovimentoEstoque, Obra

ZERO = Decimal("0")


def _normalizar(texto):
    texto = " ".join(str(texto or "").strip().upper().split())
    return "".join(
        caractere for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )


def chave_estoque(material_id, descricao, unidade):
    unidade_norm = _normalizar(unidade)
    if material_id:
        return f"M:{material_id}:{unidade_norm}"
    return f"D:{_normalizar(descricao)}:{unidade_norm}"


def _linha_base(obra, material_id, material_nome, descricao, unidade):
    return {
        "obra": obra,
        "obra_id": obra.pk,
        "material_id": material_id,
        "material_nome": material_nome or descricao,
        "descricao": descricao,
        "unidade": unidade,
        "entradas_compras": ZERO,
        "transferencias_entrada": ZERO,
        "saidas": ZERO,
        "transferencias_saida": ZERO,
        "saldo": ZERO,
        "valor_unitario_medio": ZERO,
        "valor_estoque": ZERO,
    }


def _dados_item_recebimento(rec):
    item = rec.item_pedido
    obra_item = item.pedido.obra
    material = item.necessidade.material if item.necessidade_id else None
    material_id = material.pk if material else None
    descricao = (item.descricao or "").strip() or (str(material) if material else "Item sem descrição")
    unidade = (item.unidade or "").strip() or "UN"
    material_nome = str(material) if material else descricao
    chave_item = chave_estoque(material_id, descricao, unidade)
    return item, obra_item, material_id, material_nome, descricao, unidade, chave_item


def _valor_recebimento(rec, item):
    quantidade = rec.quantidade or ZERO
    if rec.valor_recebido is not None:
        return rec.valor_recebido
    return quantidade * (item.valor_unitario or ZERO)


def obter_estoque(obra=None, somente_com_saldo=True):
    """Monta saldo físico e valor de estoque.

    Entradas físicas vêm exclusivamente dos recebimentos de Compras. Saídas e
    transferências são persistidas em Obras. A valorização usa custo médio móvel:
    cada recebimento adiciona seu valor e cada saída/transferência retira o custo
    médio existente naquele momento. Assim uma transferência leva também o valor
    do estoque da obra de origem para a obra de destino sem duplicar entradas.
    """
    linhas = OrderedDict()
    eventos = []

    recebimentos = (
        RecebimentoPedidoItem.objects
        .select_related(
            "recebimento",
            "recebimento__pedido__obra",
            "item_pedido__necessidade__material",
            "item_pedido__pedido__obra",
        )
        .order_by("recebimento__criado_em", "id")
    )
    # Para valorar corretamente transferências recebidas, o custo precisa ser
    # reconstruído desde a obra de origem. Por isso a simulação considera os
    # recebimentos de todas as obras e filtra apenas no resultado final.
    for rec in recebimentos:
        item, obra_item, material_id, material_nome, descricao, unidade, chave_item = _dados_item_recebimento(rec)
        chave = (obra_item.pk, chave_item)
        if chave not in linhas:
            linhas[chave] = _linha_base(
                obra_item, material_id, material_nome, descricao, unidade
            )
        quantidade = rec.quantidade or ZERO
        linhas[chave]["entradas_compras"] += quantidade
        eventos.append({
            "data": rec.recebimento.criado_em,
            "ordem": 0,
            "id": rec.pk,
            "tipo": "ENTRADA",
            "obra_origem_id": obra_item.pk,
            "obra_destino_id": None,
            "chave_item": chave_item,
            "quantidade": quantidade,
            "valor": _valor_recebimento(rec, item),
        })

    movimentos_base = MovimentoEstoque.objects.select_related(
        "obra_origem", "obra_destino", "material"
    )
    movimentos = movimentos_base.all()

    for mov in movimentos:
        material_id = mov.material_id
        material_nome = str(mov.material) if mov.material_id else mov.descricao_item
        descricao = mov.descricao_item
        unidade = mov.unidade
        chave_item = chave_estoque(material_id, descricao, unidade)

        chave_origem = (mov.obra_origem_id, chave_item)
        if chave_origem not in linhas:
            linhas[chave_origem] = _linha_base(
                mov.obra_origem, material_id, material_nome, descricao, unidade
            )

        if mov.tipo == MovimentoEstoque.Tipo.SAIDA:
            linhas[chave_origem]["saidas"] += mov.quantidade
        else:
            linhas[chave_origem]["transferencias_saida"] += mov.quantidade
            if mov.obra_destino_id:
                chave_destino = (mov.obra_destino_id, chave_item)
                if chave_destino not in linhas:
                    linhas[chave_destino] = _linha_base(
                        mov.obra_destino, material_id, material_nome, descricao, unidade
                    )
                linhas[chave_destino]["transferencias_entrada"] += mov.quantidade

        eventos.append({
            "data": mov.data_movimento,
            "ordem": 1,
            "id": mov.pk,
            "tipo": mov.tipo,
            "obra_origem_id": mov.obra_origem_id,
            "obra_destino_id": mov.obra_destino_id,
            "chave_item": chave_item,
            "quantidade": mov.quantidade or ZERO,
            "valor": ZERO,
        })

    # Custo médio móvel por obra/item. Não exige gravar valor nos movimentos.
    estados = {}
    eventos.sort(key=lambda evento: (evento["data"], evento["ordem"], evento["id"]))
    for evento in eventos:
        chave_origem = (evento["obra_origem_id"], evento["chave_item"])
        estado_origem = estados.setdefault(chave_origem, {"quantidade": ZERO, "valor": ZERO})

        if evento["tipo"] == "ENTRADA":
            estado_origem["quantidade"] += evento["quantidade"]
            estado_origem["valor"] += evento["valor"]
            continue

        quantidade = evento["quantidade"]
        custo_medio = (
            estado_origem["valor"] / estado_origem["quantidade"]
            if estado_origem["quantidade"] > ZERO
            else ZERO
        )
        quantidade_valorada = min(quantidade, max(estado_origem["quantidade"], ZERO))
        valor_movimento = custo_medio * quantidade_valorada
        estado_origem["quantidade"] -= quantidade
        estado_origem["valor"] -= valor_movimento
        if estado_origem["valor"] < ZERO and abs(estado_origem["valor"]) < Decimal("0.000001"):
            estado_origem["valor"] = ZERO

        if evento["tipo"] == MovimentoEstoque.Tipo.TRANSFERENCIA and evento["obra_destino_id"]:
            chave_destino = (evento["obra_destino_id"], evento["chave_item"])
            estado_destino = estados.setdefault(chave_destino, {"quantidade": ZERO, "valor": ZERO})
            estado_destino["quantidade"] += quantidade
            estado_destino["valor"] += valor_movimento

    resultado = []
    for chave, linha in linhas.items():
        if obra is not None and linha["obra_id"] != obra.pk:
            continue
        linha["saldo"] = (
            linha["entradas_compras"]
            + linha["transferencias_entrada"]
            - linha["saidas"]
            - linha["transferencias_saida"]
        )
        if somente_com_saldo and linha["saldo"] <= ZERO:
            continue

        estado = estados.get(chave, {"quantidade": ZERO, "valor": ZERO})
        valor = max(estado["valor"], ZERO)
        linha["valor_estoque"] = valor
        linha["valor_unitario_medio"] = valor / linha["saldo"] if linha["saldo"] > ZERO else ZERO
        linha["chave"] = chave_estoque(linha["material_id"], linha["descricao"], linha["unidade"])
        resultado.append(linha)

    resultado.sort(key=lambda x: (str(x["obra"]), x["material_nome"].upper(), x["unidade"]))
    return resultado


def obter_item_estoque(obra, chave):
    for linha in obter_estoque(obra=obra, somente_com_saldo=True):
        if linha["chave"] == chave:
            return linha
    return None


def resumo_por_obra(linhas=None):
    linhas = linhas if linhas is not None else obter_estoque(somente_com_saldo=True)
    obras = {obra.pk: obra for obra in Obra.objects.filter(ativa=True).order_by("nome")}
    resumo = {
        obra_id: {
            "obra": obra,
            "itens": 0,
            "valor_total": ZERO,
            "ultima_movimentacao": None,
        }
        for obra_id, obra in obras.items()
    }

    for linha in linhas:
        if linha["obra_id"] not in resumo:
            resumo[linha["obra_id"]] = {
                "obra": linha["obra"],
                "itens": 0,
                "valor_total": ZERO,
                "ultima_movimentacao": None,
            }
        resumo[linha["obra_id"]]["itens"] += 1
        resumo[linha["obra_id"]]["valor_total"] += linha["valor_estoque"]

    ultimos = (
        MovimentoEstoque.objects
        .filter(Q(obra_origem_id__in=resumo.keys()) | Q(obra_destino_id__in=resumo.keys()))
        .order_by("-data_movimento")
    )
    for mov in ultimos:
        for obra_id in {mov.obra_origem_id, mov.obra_destino_id}:
            if obra_id in resumo and resumo[obra_id]["ultima_movimentacao"] is None:
                resumo[obra_id]["ultima_movimentacao"] = mov.data_movimento

    return list(resumo.values())
