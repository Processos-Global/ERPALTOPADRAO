from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("compras", "0040_prazoentregapedido")]

    operations = [
        migrations.AddField(
            model_name="recebimentopedido",
            name="valor_frete_nota",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                editable=False,
                help_text="Frete discriminado na nota do fornecedor, cobrado à parte dos itens.",
                max_digits=18,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
    ]
