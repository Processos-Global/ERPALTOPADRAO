from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compras", "0002_fluxo_comercial_completo")]

    operations = [
        migrations.AddConstraint(
            model_name="cotacaofornecedoritem",
            constraint=models.UniqueConstraint(fields=("cotacao", "necessidade"), name="comp_cot_item_uniq"),
        ),
    ]
