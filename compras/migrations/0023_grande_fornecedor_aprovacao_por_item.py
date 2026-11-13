from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0022_grandes_fornecedores"),
    ]

    operations = [
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="participante_aprovado",
            field=models.ForeignKey(
                blank=True,
                help_text="Fornecedor escolhido pelo gestor para este micro item.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_aprovados",
                to="compras.grandefornecedorparticipante",
            ),
        ),
        migrations.AlterField(
            model_name="grandefornecedoritem",
            name="quantidade",
            field=models.DecimalField(decimal_places=2, max_digits=18, validators=[MinValueValidator(Decimal("0.01"))]),
        ),
        migrations.AlterField(
            model_name="grandefornecedoritem",
            name="quantidade_recebida",
            field=models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18, validators=[MinValueValidator(Decimal("0"))]),
        ),
        migrations.AlterField(
            model_name="grandefornecedoroferta",
            name="valor_inicial",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AlterField(
            model_name="grandefornecedoroferta",
            name="valor_atual",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AlterField(
            model_name="historicovalorgrandefornecedor",
            name="valor_anterior",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AlterField(
            model_name="historicovalorgrandefornecedor",
            name="valor_novo",
            field=models.DecimalField(decimal_places=2, max_digits=18),
        ),
    ]
