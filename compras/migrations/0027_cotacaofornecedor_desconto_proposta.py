from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0026_grande_fornecedor_status_previsao"),
    ]

    operations = [
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="desconto_proposta",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Desconto geral aplicado uma única vez sobre o valor total da proposta.",
                max_digits=18,
                validators=[MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
