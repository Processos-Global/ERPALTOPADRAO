from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.storage


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0010_titulopagar_dados_bancarios"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnexoTituloPagar",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arquivo", models.FileField(storage=core.storage.PrivateMediaStorage(), upload_to="financeiro/documentos_adicionais/%Y/%m/")),
                ("nome_original", models.CharField(blank=True, max_length=255)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("enviado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="anexos_titulos_financeiros_enviados", to=settings.AUTH_USER_MODEL)),
                ("titulo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="anexos", to="financeiro.titulopagar")),
            ],
            options={"ordering": ("criado_em", "id")},
        ),
    ]
