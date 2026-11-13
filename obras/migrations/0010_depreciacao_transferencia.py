from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("obras", "0009_vistorias")]
    operations = [
        migrations.AddField(model_name="movimentoestoque", name="depreciacao_percentual", field=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Depreciação aplicada uma única vez no relatório financeiro.")),
        migrations.AddField(model_name="movimentoestoque", name="depreciacao_registrada_em", field=models.DateTimeField(null=True, blank=True)),
    ]
