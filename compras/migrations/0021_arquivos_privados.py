import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compras", "0020_remover_fornecedores_sugeridos")]

    operations = [
        migrations.AlterField(
            model_name="cotacaofornecedor",
            name="documento",
            field=models.FileField(blank=True, null=True, storage=core.storage.PrivateMediaStorage(), upload_to="compras/cotacoes/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="contratacaocompra",
            name="documento",
            field=models.FileField(blank=True, null=True, storage=core.storage.PrivateMediaStorage(), upload_to="compras/contratacoes/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="recebimentopedido",
            name="arquivo_nota_fiscal",
            field=models.FileField(blank=True, storage=core.storage.PrivateMediaStorage(), upload_to="compras/notas_fiscais/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="pedidocompraanexo",
            name="arquivo",
            field=models.FileField(storage=core.storage.PrivateMediaStorage(), upload_to="compras/pedidos/%Y/%m/"),
        ),
    ]
