import core.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0002_simplificar_financeiro")]

    operations = [
        migrations.AlterField(
            model_name="titulopagar",
            name="arquivo_documento",
            field=models.FileField(blank=True, storage=core.storage.PrivateMediaStorage(), upload_to="financeiro/documentos/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="pagamento",
            name="comprovante",
            field=models.FileField(blank=True, storage=core.storage.PrivateMediaStorage(), upload_to="financeiro/comprovantes/%Y/%m/"),
        ),
    ]
