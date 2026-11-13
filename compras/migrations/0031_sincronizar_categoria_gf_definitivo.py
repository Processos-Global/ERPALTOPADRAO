from django.db import migrations


def sincronizar(apps, schema_editor):
    Processo = apps.get_model("compras", "ProcessoCompra")

    for processo in (
        Processo.objects.filter(fluxo_grande_fornecedor=True)
        .select_related("item_cronograma")
        .iterator()
    ):
        categoria_id = None
        if processo.item_cronograma_id:
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
        ("planejamento", "0017_reclassificar_categorias_gf_definitivo"),
        ("compras", "0030_recalcular_categoria_gf_processos"),
    ]

    operations = [
        migrations.RunPython(sincronizar, migrations.RunPython.noop),
    ]
