from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0008_pedidocompraanexo"),
    ]

    operations = [
        migrations.AddField(
            model_name="recebimentopedido",
            name="arquivo_nota_fiscal",
            field=models.FileField(
                blank=True,
                upload_to="compras/notas_fiscais/%Y/%m/",
            ),
        ),
        migrations.AddField(
            model_name="recebimentopedido",
            name="numero_nota_fiscal",
            field=models.CharField(
                blank=True,
                max_length=80,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="recebimentopedido",
            name="valor_total_nota",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="recebimentopedidoitem",
            name="valor_recebido",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddConstraint(
            model_name="recebimentopedido",
            constraint=models.UniqueConstraint(
                fields=("pedido", "numero_nota_fiscal"),
                name="comp_rec_ped_nf_uniq",
            ),
        ),
    ]
