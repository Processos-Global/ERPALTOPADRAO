import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("obras", "0019_item_ficha_descricao_medidas"),
        ("compras", "0038_reserva_estoque_compra"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimentoestoque",
            name="reserva",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimentos", to="compras.reservaestoquecompra"),
        ),
    ]
