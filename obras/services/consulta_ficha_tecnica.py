"""Consulta e exportação da Ficha Técnica; nenhuma leitura cria ficha ou item."""

from django.db.models import Count, Q

from cadastros.models import CategoriaGrandeFornecedor, Material, TipoItemGrandeFornecedor
from obras.models import AmbienteFichaTecnica, FichaTecnicaObra, ItemFichaTecnica, Obra, PavimentoFichaTecnica


def _id(parametros, nome):
    valor = str(parametros.get(nome) or "").strip()
    return int(valor) if valor.isascii() and valor.isdecimal() and int(valor) > 0 else None


def consultar_ficha_tecnica(parametros):
    filtros = {nome: _id(parametros, nome) for nome in ("obra", "pavimento", "ambiente", "categoria", "tipo", "material")}
    filtros["busca"] = (parametros.get("busca") or "").strip()[:150]
    obras = Obra.objects.filter(ativa=True, ficha_tecnica__isnull=False).order_by("nome")
    pavimentos = PavimentoFichaTecnica.objects.filter(ficha__obra__ativa=True, ativo=True)
    ambientes = AmbienteFichaTecnica.objects.filter(pavimento__ficha__obra__ativa=True, pavimento__ativo=True, ativo=True)
    if filtros["obra"]:
        pavimentos = pavimentos.filter(ficha__obra_id=filtros["obra"])
        ambientes = ambientes.filter(pavimento__ficha__obra_id=filtros["obra"])
    if filtros["pavimento"]:
        ambientes = ambientes.filter(pavimento_id=filtros["pavimento"])
    ambientes = ambientes.select_related("pavimento", "pavimento__ficha__obra", "tipo_ambiente").annotate(
        total_itens_ativos=Count(
            "categorias_gf__itens",
            filter=Q(categorias_gf__ativo=True, categorias_gf__itens__ativo=True),
            distinct=True,
        ),
    ).order_by("pavimento__ficha__obra__nome", "pavimento__ordem", "pavimento_id", "ordem", "id")

    itens = ItemFichaTecnica.objects.filter(
        ativo=True, aplicacao_categoria__ativo=True,
        aplicacao_categoria__ficha__obra__ativa=True,
    ).filter(
        Q(aplicacao_categoria__ambiente__isnull=True) |
        Q(aplicacao_categoria__ambiente__ativo=True,
          aplicacao_categoria__ambiente__pavimento__ativo=True)
    ).select_related(
        "aplicacao_categoria__ficha__obra", "aplicacao_categoria__ambiente__pavimento",
        "aplicacao_categoria__categoria", "tipo_item", "unidade", "opcao_especificacao", "material",
    )
    if filtros["obra"]:
        itens = itens.filter(aplicacao_categoria__ficha__obra_id=filtros["obra"])
    if filtros["pavimento"]:
        itens = itens.filter(aplicacao_categoria__ambiente__pavimento_id=filtros["pavimento"])
    if filtros["ambiente"]:
        itens = itens.filter(aplicacao_categoria__ambiente_id=filtros["ambiente"])
    if filtros["categoria"]:
        itens = itens.filter(aplicacao_categoria__categoria_id=filtros["categoria"])
    if filtros["tipo"]:
        itens = itens.filter(tipo_item_id=filtros["tipo"])
    if filtros["material"]:
        itens = itens.filter(material_id=filtros["material"])
    if filtros["busca"]:
        termo = filtros["busca"]
        itens = itens.filter(
            Q(tipo_item__nome__icontains=termo) | Q(descricao_item__icontains=termo) |
            Q(especificacao__icontains=termo) | Q(descricao_medidas__icontains=termo) |
            Q(opcao_especificacao__nome__icontains=termo) | Q(material__nome__icontains=termo)
        )
    itens = list(itens.order_by(
        "aplicacao_categoria__ficha__obra__nome",
        "aplicacao_categoria__ambiente__pavimento__ordem",
        "aplicacao_categoria__ambiente__pavimento_id",
        "aplicacao_categoria__ambiente__ordem",
        "aplicacao_categoria__categoria__ordem", "ordem", "id",
    ))

    por_ambiente = {}
    gerais = {}
    for item in itens:
        ambiente_id = item.aplicacao_categoria.ambiente_id
        if ambiente_id:
            por_ambiente.setdefault(ambiente_id, []).append(item)
        else:
            gerais.setdefault(item.aplicacao_categoria.ficha.obra_id, []).append(item)
    arvore = []
    por_obra = {}
    for ambiente in ambientes:
        if filtros["ambiente"] and ambiente.pk != filtros["ambiente"]:
            continue
        obra = ambiente.pavimento.ficha.obra
        no_obra = por_obra.get(obra.pk)
        if no_obra is None:
            no_obra = {"obra": obra, "pavimentos": [], "gerais": gerais.get(obra.pk, [])}
            por_obra[obra.pk] = no_obra
            arvore.append(no_obra)
        if not no_obra["pavimentos"] or no_obra["pavimentos"][-1]["pavimento"].pk != ambiente.pavimento_id:
            no_obra["pavimentos"].append({"pavimento": ambiente.pavimento, "ambientes": []})
        no_obra["pavimentos"][-1]["ambientes"].append({
            "ambiente": ambiente, "itens": por_ambiente.get(ambiente.pk, []),
        })
    for obra_id, itens_gerais in gerais.items():
        if obra_id not in por_obra:
            obra = itens_gerais[0].aplicacao_categoria.ficha.obra
            arvore.append({"obra": obra, "pavimentos": [], "gerais": itens_gerais})
    arvore.sort(key=lambda no: no["obra"].nome.casefold())

    return {
        "filtros": filtros, "obras_filtro": obras,
        "pavimentos_filtro": pavimentos.select_related("ficha__obra").order_by("ficha__obra__nome", "ordem", "id"),
        "ambientes_filtro": ambientes,
        "categorias_filtro": CategoriaGrandeFornecedor.objects.filter(ativo=True).order_by("ordem", "nome"),
        "tipos_filtro": TipoItemGrandeFornecedor.objects.filter(ativo=True).select_related("categoria").order_by("categoria__nome", "nome"),
        "materiais_filtro": Material.objects.filter(ativo=True).order_by("nome"),
        "arvore": arvore, "itens": itens, "total": len(itens),
    }
