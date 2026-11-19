from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0036_contratos"),
        ("obras", "0019_item_ficha_descricao_medidas"),
    ]

    operations = [
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="descricao_medidas",
            field=models.TextField(blank=True),
        ),
    ]
