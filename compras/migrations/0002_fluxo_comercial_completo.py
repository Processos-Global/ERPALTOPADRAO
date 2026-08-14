import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AlcadaAprovacaoCompra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("valor_minimo", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=18)),
                ("valor_maximo", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("cargo", models.CharField(blank=True, max_length=30)),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("obra", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="alcadas_compras", to="obras.obra")),
                ("usuario", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alcadas_aprovacao_compras", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("ordem", "valor_minimo", "id")},
        ),
        migrations.CreateModel(
            name="HistoricoNegociacaoItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valor_unitario_negociado", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("frete_negociado", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("prazo_entrega_dias_negociado", models.PositiveIntegerField(blank=True, null=True)),
                ("condicao_pagamento_negociada", models.CharField(blank=True, max_length=255)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("item_cotado", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="historico_negociacoes", to="compras.cotacaofornecedoritem")),
                ("usuario", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historico_negociacoes_compras", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-criado_em", "-id")},
        ),
        migrations.CreateModel(
            name="ContratacaoCompra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_formalizacao", models.CharField(choices=[("PEDIDO", "Pedido"), ("CONTRATO", "Contrato"), ("PEDIDO_E_CONTRATO", "Pedido e contrato")], default="PEDIDO", max_length=30)),
                ("condicao_pagamento", models.CharField(blank=True, max_length=255)),
                ("prazo_entrega_dias", models.PositiveIntegerField(blank=True, null=True)),
                ("previsao_entrega", models.DateField(blank=True, null=True)),
                ("local_entrega", models.CharField(blank=True, max_length=500)),
                ("referencia_contrato", models.CharField(blank=True, max_length=120)),
                ("documento", models.FileField(blank=True, null=True, upload_to="compras/contratacoes/%Y/%m/")),
                ("observacoes", models.TextField(blank=True)),
                ("formalizado_em", models.DateTimeField(auto_now_add=True)),
                ("cancelada", models.BooleanField(db_index=True, default=False)),
                ("cancelada_em", models.DateTimeField(blank=True, null=True)),
                ("motivo_cancelamento", models.TextField(blank=True)),
                ("cancelada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contratacoes_compras_canceladas", to=settings.AUTH_USER_MODEL)),
                ("fornecedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contratacoes", to="compras.fornecedorcompra")),
                ("formalizado_por", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="contratacoes_compras_formalizadas", to=settings.AUTH_USER_MODEL)),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="contratacoes", to="compras.processocompra")),
            ],
        ),
        migrations.AddField(
            model_name="adjudicacaocompra",
            name="cancelada_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="adjudicacaocompra",
            name="cancelada_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="adjudicacoes_compras_canceladas", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="adjudicacaocompra",
            name="motivo_cancelamento",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="aprovacaocompra",
            name="alcada",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="decisoes", to="compras.alcadaaprovacaocompra"),
        ),
        migrations.AddConstraint(
            model_name="contratacaocompra",
            constraint=models.UniqueConstraint(condition=models.Q(("cancelada", False)), fields=("processo", "fornecedor"), name="comp_contrat_proc_forn_ativa_uniq"),
        ),
        migrations.AlterModelOptions(name="aprovacaocompra", options={"ordering": ("-criado_em", "-id")}),
        migrations.AlterModelOptions(name="compatibilizacaoitem", options={"ordering": ("-data", "-id")}),
    ]
