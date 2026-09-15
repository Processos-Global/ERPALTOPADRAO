from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0010_remover_insumos_do_cronograma_obra"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="tipo_fluxo_compra",
            field=models.CharField(
                choices=[("NORMAL", "Fluxo normal"), ("GRANDE_FORNECEDOR", "Grande fornecedor")],
                db_index=True,
                default="NORMAL",
                help_text="Define se o suprimento usa o fluxo comum ou a matriz de Grandes Fornecedores.",
                max_length=30,
            ),
        ),
    ]
