from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0013_meio_pagamento"),
        ("compras", "0038_reserva_estoque_compra"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LiberacaoFinanceiraPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("referencia", models.CharField(max_length=160, unique=True)),
                ("tipo", models.CharField(max_length=20, choices=[("RECEBIMENTO", "Recebimento"), ("ANTECIPACAO", "Antecipação"), ("PARCELA", "Parcela contratual"), ("MEDICAO", "Medição"), ("CONDICAO", "Condição contratual")])),
                ("status", models.CharField(max_length=20, choices=[("PENDENTE", "Pendente de liberação"), ("DIVERGENTE", "Divergente"), ("AUTORIZADA", "Liberada"), ("COMPENSADA", "Coberta por antecipação"), ("CANCELADA", "Cancelada")], default="PENDENTE", db_index=True)),
                ("valor", models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"), validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("valor_origem", models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))),
                ("valor_compensado", models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))),
                ("justificativa", models.TextField(blank=True)),
                ("divergencia", models.TextField(blank=True)),
                ("motivo_cancelamento", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("autorizado_em", models.DateTimeField(blank=True, null=True)),
                ("cancelado_em", models.DateTimeField(blank=True, null=True)),
                ("pedido", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="liberacoes_financeiras", to="compras.pedidocompra")),
                ("recebimento", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="liberacao_financeira", to="compras.recebimentopedido")),
                ("parcela", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="liberacoes_financeiras", to="compras.parcelaprevistapedido")),
                ("titulo", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="liberacao_pedido", to="financeiro.titulopagar")),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="liberacoes_pedido_criadas", to=settings.AUTH_USER_MODEL)),
                ("autorizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="liberacoes_pedido_autorizadas", to=settings.AUTH_USER_MODEL)),
                ("cancelado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="liberacoes_pedido_canceladas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-criado_em", "-id")},
        ),
        migrations.AddIndex(model_name="liberacaofinanceirapedido", index=models.Index(fields=["pedido", "status"], name="fin_lib_ped_st_idx")),
    ]
