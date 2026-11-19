from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0011_migrar_permissoes_anteriores"),
    ]

    operations = [
        migrations.AddField(
            model_name="permissaocompras",
            name="excecao_estoque",
            field=models.BooleanField(default=False, verbose_name="Autorizar exceção de estoque"),
        ),
    ]
