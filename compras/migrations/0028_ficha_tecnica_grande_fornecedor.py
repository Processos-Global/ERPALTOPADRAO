from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0027_cotacaofornecedor_desconto_proposta"),
        ("obras", "0002_ficha_tecnica"),
    ]

    operations = [
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="especificacao",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="item_ficha_tecnica",
            field=models.ForeignKey(blank=True, help_text="Origem técnica do item quando importado da Ficha Técnica da Obra.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="itens_compatibilizacao_gf", to="obras.itemfichatecnica"),
        ),
    ]
