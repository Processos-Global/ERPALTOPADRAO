import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0037_grande_fornecedor_item_medidas"),
        ("obras", "0018_diario_atividades"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReservaEstoqueCompra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unidade", models.CharField(max_length=20)),
                ("especificacao", models.TextField(blank=True)),
                ("quantidade_original", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("quantidade_disponivel", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("status", models.CharField(choices=[("ATIVA", "Ativa"), ("CONSUMIDA", "Consumida"), ("LIBERADA", "Liberada")], db_index=True, default="ATIVA", max_length=20)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("criado_por", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reservas_estoque_criadas", to=settings.AUTH_USER_MODEL)),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservas_estoque_compra", to="cadastros.material")),
                ("necessidade", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="reserva_estoque", to="compras.necessidadecompra")),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reservas_estoque_compra", to="obras.obra")),
            ],
            options={"indexes": [models.Index(fields=["obra", "material", "status"], name="comp_res_obra_mat_st_idx")]},
        ),
    ]
