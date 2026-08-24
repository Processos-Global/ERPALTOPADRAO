from django.db import migrations, models


def copiar_fornecedor_antigo(apps, schema_editor):
    ProcessoCompra = apps.get_model("compras", "ProcessoCompra")
    through = ProcessoCompra.fornecedores_sugeridos.through
    registros = []
    for processo in ProcessoCompra.objects.exclude(fornecedor_sugerido_id__isnull=True).iterator():
        registros.append(
            through(
                processocompra_id=processo.id,
                fornecedorcompra_id=processo.fornecedor_sugerido_id,
            )
        )
    if registros:
        through.objects.bulk_create(registros, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0012_processo_fornecedor_sugerido"),
    ]

    operations = [
        migrations.AddField(
            model_name="processocompra",
            name="fornecedores_sugeridos",
            field=models.ManyToManyField(
                blank=True,
                help_text="Fornecedores indicados no pedido inicial para orientar o Suprimentos.",
                related_name="processos_compra_sugeridos",
                to="compras.fornecedorcompra",
            ),
        ),
        migrations.RunPython(copiar_fornecedor_antigo, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="processocompra",
            name="fornecedor_sugerido",
        ),
    ]
