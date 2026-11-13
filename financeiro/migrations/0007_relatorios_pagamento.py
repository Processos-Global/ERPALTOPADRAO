# Generated for Financeiro - relatórios de pagamentos aprovados.

from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0006_titulopagar_materiais"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RelatorioPagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(db_index=True, max_length=24, unique=True)),
                ("periodo_inicio", models.DateField(db_index=True)),
                ("periodo_fim", models.DateField(db_index=True)),
                ("quantidade_itens", models.PositiveIntegerField(default=0)),
                ("valor_total", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("emitido_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("emitido_por", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="relatorios_pagamento_emitidos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Relatório de pagamentos",
                "verbose_name_plural": "Relatórios de pagamentos",
                "ordering": ("-emitido_em", "-id"),
            },
        ),
        migrations.CreateModel(
            name="ItemRelatorioPagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_aprovacao", models.DateTimeField()),
                ("conta_numero", models.CharField(max_length=24)),
                ("pedido_numero", models.CharField(blank=True, max_length=80)),
                ("obra_nome", models.CharField(blank=True, max_length=255)),
                ("beneficiario_nome", models.CharField(max_length=255)),
                ("beneficiario_documento", models.CharField(blank=True, max_length=40)),
                ("descricao", models.CharField(max_length=300)),
                ("especificacao_pagamento", models.TextField(blank=True)),
                ("apropriacao", models.CharField(blank=True, max_length=350)),
                ("parcela", models.CharField(blank=True, max_length=30)),
                ("vencimento", models.DateField(blank=True, null=True)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=18)),
                ("origem", models.CharField(blank=True, max_length=120)),
                ("observacao", models.TextField(blank=True)),
                ("aprovacao", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="item_relatorio_pagamento", to="financeiro.aprovacaotitulofinanceiro")),
                ("relatorio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="financeiro.relatoriopagamento")),
                ("titulo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="itens_relatorio_pagamento", to="financeiro.titulopagar")),
            ],
            options={
                "verbose_name": "Item do relatório de pagamentos",
                "verbose_name_plural": "Itens do relatório de pagamentos",
                "ordering": ("data_aprovacao", "id"),
            },
        ),
    ]
