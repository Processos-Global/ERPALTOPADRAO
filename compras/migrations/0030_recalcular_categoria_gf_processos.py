from django.db import migrations


def recalcular_processos(apps, schema_editor):
    Processo = apps.get_model("compras", "ProcessoCompra")

    for processo in (
        Processo.objects.filter(fluxo_grande_fornecedor=True)
        .select_related("item_cronograma")
        .iterator()
    ):
        categoria_id = getattr(
            processo.item_cronograma,
            "categoria_grande_fornecedor_id",
            None,
        )
        Processo.objects.filter(pk=processo.pk).update(
            categoria_grande_fornecedor_id=categoria_id
        )


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0016_recalcular_categoria_gf_categoria_item"),
        ("compras", "0029_categoria_grande_fornecedor_processo"),
    ]

    operations = [
        migrations.RunPython(recalcular_processos, migrations.RunPython.noop),
    ]
