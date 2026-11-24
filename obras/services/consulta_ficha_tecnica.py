"""Consulta e exportação da Ficha Técnica; nenhuma leitura cria ficha ou item."""

from django.db.models import Count, Q

from cadastros.models import CategoriaGrandeFornecedor, Material, TipoItemGrandeFornecedor
from obras.models import AmbienteFichaTecnica, FichaTecnicaObra, ItemFichaTecnica, Obra, PavimentoFichaTecnica


def _id(parametros, nome):
    valor = str(parametros.get(nome) or "").strip().lstrip("0")
    if not valor.isascii() or not valor.isdecimal() or len(valor) > 19:
        return None
    numero = int(valor)
    return numero if numero <= 2**63 - 1 else None


def buscar_materiais_consulta(termo, pagina):
    por_pagina = 20
    inicio = (pagina - 1) * por_pagina
    materiais = Material.objects.filter(ativo=True)
    if termo:
        materiais = materiais.filter(
            Q(codigo__icontains=termo) | Q(nome__icontains=termo) | Q(especificacao__icontains=termo)
        )
    encontrados = list(materiais.only("nome", "especificacao").order_by(
        "nome", "especificacao", "pk",
    )[inicio:inicio + por_pagina + 1])
    return {
        "resultados": [
            {"id": material.pk, "texto": material.descricao_completa}
            for material in encontrados[:por_pagina]
        ],
        "mais": len(encontrados) > por_pagina,
    }


def consultar_ficha_tecnica(parametros, *, navegacao=False):
    filtros = {nome: _id(parametros, nome) for nome in ("obra", "pavimento", "ambiente", "categoria", "tipo", "material")}
    filtros["busca"] = (parametros.get("busca") or "").strip()[:150]
    apenas_gerais = (
        parametros.get("gerais") == "1" and filtros["obra"]
        and not (filtros["ambiente"] or filtros["pavimento"])
    )
    resumo = navegacao and not (filtros["ambiente"] or apenas_gerais)
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
    if apenas_gerais:
        itens = itens.filter(aplicacao_categoria__ambiente__isnull=True)
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
    contagens = {}
    por_ambiente = {}
    gerais = {}
    if resumo:
        contagens = {
            (obra_id, ambiente_id): total
            for obra_id, ambiente_id, total in itens.order_by().values_list(
                "aplicacao_categoria__ficha__obra_id", "aplicacao_categoria__ambiente_id",
            ).annotate(total=Count("pk"))
        }
        itens = []
    else:
        itens = list(itens.order_by(
            "aplicacao_categoria__ficha__obra__nome",
            "aplicacao_categoria__ambiente__pavimento__ordem",
            "aplicacao_categoria__ambiente__pavimento_id",
            "aplicacao_categoria__ambiente__ordem",
            "aplicacao_categoria__categoria__ordem", "ordem", "id",
        ))
    for item in itens:
        aplicacao = item.aplicacao_categoria
        obra_id, ambiente_id = aplicacao.ficha.obra_id, aplicacao.ambiente_id
        chave = (obra_id, ambiente_id)
        contagens[chave] = contagens.get(chave, 0) + 1
        if ambiente_id:
            por_ambiente.setdefault(ambiente_id, []).append(item)
        else:
            gerais.setdefault(obra_id, []).append(item)

    def no_de_obra(obra):
        return {
            "obra": obra, "pavimentos": [], "gerais": gerais.get(obra.pk, []),
            "total_gerais": contagens.get((obra.pk, None), 0),
        }

    arvore = []
    por_obra = {}
    for ambiente in ambientes if not apenas_gerais else []:
        if filtros["ambiente"] and ambiente.pk != filtros["ambiente"]:
            continue
        obra = ambiente.pavimento.ficha.obra
        no_obra = por_obra.get(obra.pk)
        if no_obra is None:
            no_obra = no_de_obra(obra)
            por_obra[obra.pk] = no_obra
            arvore.append(no_obra)
        if not no_obra["pavimentos"] or no_obra["pavimentos"][-1]["pavimento"].pk != ambiente.pavimento_id:
            no_obra["pavimentos"].append({"pavimento": ambiente.pavimento, "ambientes": []})
        no_obra["pavimentos"][-1]["ambientes"].append({
            "ambiente": ambiente, "itens": por_ambiente.get(ambiente.pk, []),
            "total_filtrado": contagens.get((obra.pk, ambiente.pk), 0),
        })
    ids_obras_gerais = {obra_id for obra_id, ambiente_id in contagens if ambiente_id is None} - por_obra.keys()
    if ids_obras_gerais:
        arvore.extend(no_de_obra(obra) for obra in obras.filter(pk__in=ids_obras_gerais))
    arvore.sort(key=lambda no: no["obra"].nome.casefold())

    return {
        "filtros": filtros, "obras_filtro": obras,
        "pavimentos_filtro": pavimentos.select_related("ficha__obra").order_by("ficha__obra__nome", "ordem", "id"),
        "ambientes_filtro": ambientes,
        "categorias_filtro": CategoriaGrandeFornecedor.objects.filter(ativo=True).order_by("ordem", "nome"),
        "tipos_filtro": TipoItemGrandeFornecedor.objects.filter(ativo=True).select_related("categoria").order_by("categoria__nome", "nome"),
        "arvore": arvore, "itens": itens, "total": sum(contagens.values()),
        "apenas_gerais": bool(apenas_gerais), "resumo_navegacao": resumo,
    }
