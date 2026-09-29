from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0006_alter_caracteristicaambiente_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="fornecedor",
            name="banco",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="fornecedor",
            name="agencia",
            field=models.CharField(blank=True, max_length=30, verbose_name="Agência"),
        ),
        migrations.AddField(
            model_name="fornecedor",
            name="conta_corrente",
            field=models.CharField(blank=True, max_length=40, verbose_name="Conta corrente"),
        ),
        migrations.AddField(
            model_name="fornecedor",
            name="operacao_bancaria",
            field=models.CharField(blank=True, max_length=30, verbose_name="Operação"),
        ),
        migrations.AddField(
            model_name="fornecedor",
            name="pix",
            field=models.CharField(blank=True, max_length=255, verbose_name="PIX"),
        ),
        migrations.AddField(
            model_name="fornecedor",
            name="titular_conta",
            field=models.CharField(blank=True, max_length=255, verbose_name="Titular"),
        ),
    ]
