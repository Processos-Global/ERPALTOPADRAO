from django.db import migrations, models


def migrar_status_antigos(apps, schema_editor):
    GrandeFornecedorItem = apps.get_model("compras", "GrandeFornecedorItem")

    # Itens que ainda estavam nas etapas iniciais passam a iniciar em
    # Aprovação de projeto. Etapas logísticas antigas passam para Produção.
    GrandeFornecedorItem.objects.filter(
        status__in=["AGUARDANDO", "CONFIRMADO"]
    ).update(status="APROVACAO_PROJETO")
    GrandeFornecedorItem.objects.filter(
        status__in=["PRONTO", "TRANSPORTE"]
    ).update(status="PRODUCAO")


def reverter_status(apps, schema_editor):
    GrandeFornecedorItem = apps.get_model("compras", "GrandeFornecedorItem")
    GrandeFornecedorItem.objects.filter(
        status__in=["APROVACAO_PROJETO", "LIBERADO_MEDICAO"]
    ).update(status="AGUARDANDO")


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0031_sincronizar_categoria_gf_definitivo"),
    ]

    operations = [
        migrations.RunPython(migrar_status_antigos, reverter_status),
        migrations.AlterField(
            model_name="grandefornecedoritem",
            name="status",
            field=models.CharField(
                choices=[
                    ("APROVACAO_PROJETO", "Aprovação de projeto"),
                    ("LIBERADO_MEDICAO", "Liberado p/ medição"),
                    ("PRODUCAO", "Produção"),
                    ("PARCIAL", "Entrega Parcial"),
                    ("ENTREGUE", "Entregue"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="APROVACAO_PROJETO",
                max_length=20,
            ),
        ),
    ]
