from django.db import migrations, models
import django.db.models.deletion


def preencher_processos(apps, schema_editor):
    Processo = apps.get_model("compras", "ProcessoCompra")
    for processo in (
        Processo.objects.filter(fluxo_grande_fornecedor=True)
        .select_related("item_cronograma")
        .iterator()
    ):
        categoria_id = getattr(processo.item_cronograma, "categoria_grande_fornecedor_id", None)
        if categoria_id:
            Processo.objects.filter(pk=processo.pk).update(
                categoria_grande_fornecedor_id=categoria_id
            )


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0004_ficha_tecnica_base"),
        ("planejamento", "0015_categoria_grande_fornecedor"),
        ("compras", "0028_ficha_tecnica_grande_fornecedor"),
    ]

    operations = [
        migrations.AddField(
            model_name="processocompra",
            name="categoria_grande_fornecedor",
            field=models.ForeignKey(
                blank=True,
                help_text="Categoria GF herdada do Cronograma de Suprimentos. Define quais itens da Ficha Técnica pertencem a este processo.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="processos_compra",
                to="cadastros.categoriagrandefornecedor",
            ),
        ),
        migrations.RunPython(preencher_processos, migrations.RunPython.noop),
    ]
