from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0006_atividade_origem_opcional"),
    ]

    operations = [
        migrations.AddField(
            model_name="cotacaofornecedoritem",
            name="atualizado_em",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
    ]
