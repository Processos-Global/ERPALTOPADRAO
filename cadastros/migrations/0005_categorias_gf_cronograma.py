from django.db import migrations


def criar_categorias(apps, schema_editor):
    Categoria = apps.get_model("cadastros", "CategoriaGrandeFornecedor")

    existentes = {c.nome: c for c in Categoria.objects.all()}
    maior_ordem = max([c.ordem for c in existentes.values()] or [0])

    novas = [
        ("PROJETO ESTRUTURAL", "DESCRITIVO", False),
        ("PROJETOS COMPLEMENTARES", "DESCRITIVO", False),
        ("CONJUNTO DE AÇO", "DESCRITIVO", False),
        ("ESCORAMENTO", "DESCRITIVO", False),
        ("FOTOVOLTAICA", "DESCRITIVO", False),
        ("MOBILIÁRIO", "DESCRITIVO", False),
    ]

    ordem = maior_ordem
    for nome, tipo_preenchimento, somente_area_molhada in novas:
        ordem += 1
        Categoria.objects.get_or_create(
            nome=nome,
            defaults={
                "tipo_preenchimento": tipo_preenchimento,
                "somente_area_molhada": somente_area_molhada,
                "ordem": ordem,
                "ativo": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0004_ficha_tecnica_base"),
    ]

    operations = [
        migrations.RunPython(criar_categorias, migrations.RunPython.noop),
    ]
