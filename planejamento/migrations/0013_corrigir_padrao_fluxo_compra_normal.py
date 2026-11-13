from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0012_alter_itemcronogramasuprimento_tipo_fluxo_compra"),
    ]

    operations = [
        migrations.AlterField(
            model_name="itemcronogramasuprimento",
            name="tipo_fluxo_compra",
            field=models.CharField(
                choices=[
                    ("NORMAL", "Fluxo normal"),
                    ("GRANDE_FORNECEDOR", "Grande fornecedor"),
                ],
                db_index=True,
                default="NORMAL",
                help_text=(
                    "Define se o suprimento usa o fluxo comum ou o fluxo paralelo de Grandes Fornecedores. "
                    "Cronogramas sem classificação explícita usam o fluxo normal principal como padrão."
                ),
                max_length=30,
            ),
        ),
    ]
