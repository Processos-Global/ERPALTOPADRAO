from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pos_obra", "0010_remove_anexochamado_via_assinada_conferida_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="registrochamado",
            name="via_assinada_conferida",
        ),
        migrations.AddField(
            model_name="anexochamado",
            name="via_assinada_conferida",
            field=models.BooleanField(
                default=False,
                help_text="Via assinada identificada e conferida por responsável interno.",
            ),
        ),
    ]
