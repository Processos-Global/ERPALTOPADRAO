import unicodedata

from cadastros.models import CategoriaGrandeFornecedor


def normalizar_categoria(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    for caractere in "_/\\|:;,.()[]{}+":
        texto = texto.replace(caractere, " ")
    texto = texto.replace("-", " ")
    return " ".join(texto.split())


# Mapeamento determinístico entre os nomes reais do Cronograma de Suprimentos
# e as categorias técnicas utilizadas pela Ficha Técnica / Grandes Fornecedores.
# O objetivo é evitar falsos positivos como 'ESCORAMENTO METÁLICO' -> 'LOUÇAS E METAIS'.
_MAPA_ITEM_CATEGORIA = {
    # Projetos também seguem o fluxo de Grande Fornecedor.
    "PROJETO ESTRUTURAL": "PROJETO ESTRUTURAL",
    "PROJETO INSTALACOES COMPLEMENTARES": "PROJETOS COMPLEMENTARES",
    "PROJETO LUMINOTECNICO ILUMINACAO": "ILUMINAÇÃO",
    "PROJETO AUTOMACAO": "AUTOMAÇÃO",
    "PROJETO PAISAGISMO": "PAISAGISMO",

    # Grandes Fornecedores do cronograma.
    "CONJUNTO DE ACO": "CONJUNTO DE AÇO",
    "ESCORAMENTO MADEIRA METALICO": "ESCORAMENTO",
    "ELEVADOR": "ELEVADOR",
    "QUADROS ELETRICOS": "QUADROS ELETRICOS",
    "INSTALACOES DE AR CONDICIONADO INFRAESTRUTURA": "AR CONDICIONADO - EQUIPAMENTO",
    "INSTALACOES DE AR CONDICIONADO MAQUINAS": "AR CONDICIONADO - SISTEMA",
    "REVESTIMENTOS MARMORARIA": "MARMORARIA",
    "REVESTIMENTOS EM PEDRAS NATURAIS": "MARMORARIA",
    "FORRO EM MADEIRA": "PISO E FORRO DE MADEIRA",
    "MARCENARIA E ARMARIOS": "MARCENARIA DECORATIVA",
    "ESQUADRIAS DE ALUMINIO VIDROS": "ESQUADRIAS",
    "CLARABOIAS": "ESQUADRIAS",
    "PAINEIS EM MADEIRA": "MARCENARIA DECORATIVA",
    "PORTAS INTERNAS": "PORTAS",
    "MARCENARIA DECORATIVA E PAINEIS": "MARCENARIA DECORATIVA",
    "BRISES METALICOS ALUMINIO MADEIRA": "ESQUADRIAS",
    "GUARDA CORPOS": "ESQUADRIAS",
    "PISO DE MADEIRA": "PISO E FORRO DE MADEIRA",
    "ADEGA MARCENARIA ESPECIALIZADA": "ADEGA",
    "FOTOVOLTAICA": "FOTOVOLTAICA",
    "LOUCAS": "LOUÇAS E METAIS",
    "METAIS": "LOUÇAS E METAIS",
    "ESPELHOS": "VIDROS E ESPELHOS",
    "BOXES": "VIDROS E ESPELHOS",
    "PAISAGISMO EXECUCAO": "PAISAGISMO",
    "MOBILIARIO": "MOBILIÁRIO",
}


# Regras de fallback seguras para pequenas variações de escrita. Elas são
# avaliadas SOMENTE depois do mapa exato acima. Não há regra genérica para
# a palavra METAL/METÁLICO, justamente para impedir associações indevidas.
_ALIASES_SEGUROS = (
    (("AR CONDICIONADO", "INFRAESTRUT"), "AR CONDICIONADO - EQUIPAMENTO"),
    (("AR CONDICIONADO", "MAQUIN"), "AR CONDICIONADO - SISTEMA"),
    (("LUMINOTEC",), "ILUMINAÇÃO"),
    (("AUTOMAC",), "AUTOMAÇÃO"),
    (("PAISAG",), "PAISAGISMO"),
    (("QUADRO", "ELETR"), "QUADROS ELETRICOS"),
    (("MARMOR",), "MARMORARIA"),
    (("PEDRA", "NATURAL"), "MARMORARIA"),
    (("MARCENARIA", "ARMAR"), "MARCENARIA DECORATIVA"),
    (("MARCENARIA", "DECORAT"), "MARCENARIA DECORATIVA"),
    (("ESQUADRIA",), "ESQUADRIAS"),
    (("CLARABOIA",), "ESQUADRIAS"),
    (("GUARDA", "CORPO"), "ESQUADRIAS"),
    (("BRISE",), "ESQUADRIAS"),
    (("PORTA", "INTERNA"), "PORTAS"),
    (("PISO", "MADEIRA"), "PISO E FORRO DE MADEIRA"),
    (("FORRO", "MADEIRA"), "PISO E FORRO DE MADEIRA"),
    (("ADEGA",), "ADEGA"),
    (("LOUCA",), "LOUÇAS E METAIS"),
    (("METAIS",), "LOUÇAS E METAIS"),
    (("ESPELHO",), "VIDROS E ESPELHOS"),
    (("BOX",), "VIDROS E ESPELHOS"),
    (("FOTOVOLT",), "FOTOVOLTAICA"),
    (("MOBILIAR",), "MOBILIÁRIO"),
    (("CONJUNTO", "ACO"), "CONJUNTO DE AÇO"),
    (("ESCORAMENTO",), "ESCORAMENTO"),
    (("PROJETO", "ESTRUTURAL"), "PROJETO ESTRUTURAL"),
    (("PROJETO", "INSTALAC", "COMPLEMENT"), "PROJETOS COMPLEMENTARES"),
    (("ELEVADOR",), "ELEVADOR"),
    (("IRRIGA",), "IRRIGAÇÃO"),
    (("PROTEN",), "PROTENSÃO"),
    (("RALO", "LINEAR"), "RALOS LINEARES"),
    (("AQUECIMENTO", "PISCINA"), "AQUECIMENTO PISCINA"),
    (("COIFA",), "COIFA BOX"),
    (("ELETRODOM",), "ELETRODOMESTICOS"),
    (("FUNDAC",), "FUNDAÇÃO"),
)


def resolver_categoria_grande_fornecedor(texto_categoria, texto_item=None):
    """Resolve a CategoriaGrandeFornecedor de um item do cronograma.

    A decisão usa primeiro o ITEM/atividade, pois é nele que normalmente está
    a informação técnica que diferencia categorias dentro de PROJETOS e
    GRANDES FORNECEDORES. A categoria macro continua sendo usada como apoio.

    Não cria registros. Categorias de destino devem existir no cadastro.
    """
    categoria_norm = normalizar_categoria(texto_categoria)
    item_norm = normalizar_categoria(texto_item)
    texto_completo = " ".join(x for x in (categoria_norm, item_norm) if x).strip()

    if not texto_completo:
        return None

    categorias = list(
        CategoriaGrandeFornecedor.objects.filter(ativo=True).order_by("ordem", "nome")
    )
    por_normalizado = {normalizar_categoria(c.nome): c for c in categorias}

    # 1) Item exato do cronograma -> categoria técnica explícita.
    destino_nome = _MAPA_ITEM_CATEGORIA.get(item_norm)
    if destino_nome:
        return por_normalizado.get(normalizar_categoria(destino_nome))

    # 2) Se o próprio item ou categoria já for exatamente uma categoria GF.
    if item_norm in por_normalizado:
        return por_normalizado[item_norm]
    if categoria_norm in por_normalizado:
        return por_normalizado[categoria_norm]

    # 3) Fallback por termos seguros. Prioriza o item e depois o conjunto.
    for origem in (item_norm, texto_completo):
        if not origem:
            continue
        for termos, destino in _ALIASES_SEGUROS:
            if all(termo in origem for termo in termos):
                categoria = por_normalizado.get(normalizar_categoria(destino))
                if categoria:
                    return categoria

    return None
