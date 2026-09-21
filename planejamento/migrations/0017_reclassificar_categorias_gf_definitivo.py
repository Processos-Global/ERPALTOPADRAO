import unicodedata

from django.db import migrations


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    for caractere in "_/\\|:;,.()[]{}+":
        texto = texto.replace(caractere, " ")
    texto = texto.replace("-", " ")
    return " ".join(texto.split())


MAPA = {
    "PROJETO ESTRUTURAL": "PROJETO ESTRUTURAL",
    "PROJETO INSTALACOES COMPLEMENTARES": "PROJETOS COMPLEMENTARES",
    "PROJETO LUMINOTECNICO ILUMINACAO": "ILUMINAÇÃO",
    "PROJETO AUTOMACAO": "AUTOMAÇÃO",
    "PROJETO PAISAGISMO": "PAISAGISMO",
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


def reclassificar(apps, schema_editor):
    Item = apps.get_model("planejamento", "ItemCronogramaSuprimento")
    Categoria = apps.get_model("cadastros", "CategoriaGrandeFornecedor")

    por_nome = {_normalizar(c.nome): c.pk for c in Categoria.objects.filter(ativo=True)}

    for item in Item.objects.all().only("id", "categoria", "item", "tipo_fluxo_compra").iterator():
        # Projetos permanecem no mesmo fluxo GF; Materiais Variados continuam NORMAL.
        categoria_macro = _normalizar(item.categoria)
        if not categoria_macro or ("MATERIA" in categoria_macro and "VARIAD" in categoria_macro):
            Item.objects.filter(pk=item.pk).update(
                tipo_fluxo_compra="NORMAL",
                categoria_grande_fornecedor_id=None,
            )
            continue

        nome_destino = MAPA.get(_normalizar(item.item))
        categoria_id = por_nome.get(_normalizar(nome_destino)) if nome_destino else None

        Item.objects.filter(pk=item.pk).update(
            tipo_fluxo_compra="GRANDE_FORNECEDOR",
            categoria_grande_fornecedor_id=categoria_id,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0005_categorias_gf_cronograma"),
        ("planejamento", "0016_recalcular_categoria_gf_categoria_item"),
    ]

    operations = [
        migrations.RunPython(reclassificar, migrations.RunPython.noop),
    ]
