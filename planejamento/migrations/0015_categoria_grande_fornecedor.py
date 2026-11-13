import unicodedata

from django.db import migrations, models
import django.db.models.deletion


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    for caractere in "_/\\|:;,.()[]{}":
        texto = texto.replace(caractere, " ")
    texto = texto.replace("-", " ")
    return " ".join(texto.split())


ALIASES = (
    (("AR CONDICIONADO", "MAQUIN"), "AR CONDICIONADO - SISTEMA"),
    (("AR CONDICIONADO", "SISTEMA"), "AR CONDICIONADO - SISTEMA"),
    (("AR CONDICIONADO", "EQUIP"), "AR CONDICIONADO - EQUIPAMENTO"),
    (("ESQUADRIA",), "ESQUADRIAS"),
    (("MARMOR",), "MARMORARIA"),
    (("GRANITO",), "MARMORARIA"),
    (("LOUCA", "METAL"), "LOUÇAS E METAIS"),
    (("MARCENARIA", "DECORAT"), "MARCENARIA DECORATIVA"),
    (("VIDRO", "ESPELHO"), "VIDROS E ESPELHOS"),
    (("QUADRO", "ELETR"), "QUADROS ELETRICOS"),
    (("PISO", "FORRO", "MADEIRA"), "PISO E FORRO DE MADEIRA"),
    (("RALO", "LINEAR"), "RALOS LINEARES"),
    (("AQUECIMENTO", "PISCINA"), "AQUECIMENTO PISCINA"),
    (("PAISAG",), "PAISAGISMO"),
    (("IRRIGA",), "IRRIGAÇÃO"),
    (("PROTEN",), "PROTENSÃO"),
    (("ILUMINA",), "ILUMINAÇÃO"),
    (("AUTOMA",), "AUTOMAÇÃO"),
    (("ELEVADOR",), "ELEVADOR"),
    (("PORTA",), "PORTAS"),
    (("ADEGA",), "ADEGA"),
    (("COIFA",), "COIFA BOX"),
    (("ELETRODOM",), "ELETRODOMESTICOS"),
    (("FUNDAC",), "FUNDAÇÃO"),
)


def preencher_categoria_gf(apps, schema_editor):
    Item = apps.get_model("planejamento", "ItemCronogramaSuprimento")
    Categoria = apps.get_model("cadastros", "CategoriaGrandeFornecedor")

    categorias = list(Categoria.objects.filter(ativo=True).order_by("ordem", "nome"))
    por_nome = {_normalizar(c.nome): c for c in categorias}

    def resolver(texto_origem):
        texto = _normalizar(texto_origem)
        if not texto:
            return None
        if texto in por_nome:
            return por_nome[texto]

        candidatos = []
        for nome_norm, categoria in por_nome.items():
            if nome_norm and (nome_norm in texto or texto in nome_norm):
                candidatos.append((len(nome_norm), categoria))
        if candidatos:
            candidatos.sort(key=lambda x: x[0], reverse=True)
            return candidatos[0][1]

        for termos, destino in ALIASES:
            if all(termo in texto for termo in termos):
                return por_nome.get(_normalizar(destino))
        return None

    for item in Item.objects.all().only("id", "categoria").iterator():
        categoria = resolver(item.categoria)
        if categoria:
            Item.objects.filter(pk=item.pk).update(categoria_grande_fornecedor_id=categoria.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0004_ficha_tecnica_base"),
        ("planejamento", "0014_reclassificar_fluxo_compra_por_categoria"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="categoria_grande_fornecedor",
            field=models.ForeignKey(
                blank=True,
                help_text="Categoria técnica de Grande Fornecedor identificada a partir da categoria do cronograma. É esta relação que conecta Planejamento, Ficha Técnica e Compras.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_cronograma_suprimentos",
                to="cadastros.categoriagrandefornecedor",
            ),
        ),
        migrations.RunPython(preencher_categoria_gf, migrations.RunPython.noop),
    ]
