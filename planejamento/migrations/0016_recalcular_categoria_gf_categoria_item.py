import unicodedata

from django.db import migrations


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
    (("METAL",), "LOUÇAS E METAIS"),
    (("MARCENARIA", "DECORAT"), "MARCENARIA DECORATIVA"),
    (("MARCENARIA",), "MARCENARIA DECORATIVA"),
    (("ARMARIO",), "MARCENARIA DECORATIVA"),
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


def recalcular(apps, schema_editor):
    Item = apps.get_model("planejamento", "ItemCronogramaSuprimento")
    Categoria = apps.get_model("cadastros", "CategoriaGrandeFornecedor")

    categorias = list(Categoria.objects.filter(ativo=True).order_by("ordem", "nome"))
    por_nome = {_normalizar(c.nome): c for c in categorias}

    def resolver(categoria_origem, item_origem):
        texto = _normalizar(f"{categoria_origem or ''} {item_origem or ''}")
        if not texto:
            return None

        for termos, destino in ALIASES:
            if all(termo in texto for termo in termos):
                categoria = por_nome.get(_normalizar(destino))
                if categoria:
                    return categoria

        if texto in por_nome:
            return por_nome[texto]

        candidatos = []
        for nome_norm, categoria in por_nome.items():
            if nome_norm and (nome_norm in texto or texto in nome_norm):
                candidatos.append((len(nome_norm), categoria))
        if candidatos:
            candidatos.sort(key=lambda x: x[0], reverse=True)
            return candidatos[0][1]
        return None

    for item in Item.objects.all().only("id", "categoria", "item").iterator():
        categoria = resolver(item.categoria, item.item)
        Item.objects.filter(pk=item.pk).update(
            categoria_grande_fornecedor_id=categoria.pk if categoria else None
        )


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0015_categoria_grande_fornecedor"),
    ]

    operations = [
        migrations.RunPython(recalcular, migrations.RunPython.noop),
    ]
