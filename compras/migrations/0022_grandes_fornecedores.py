from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import core.storage


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cadastros", "0002_alter_fornecedor_avaliacao"),
        ("planejamento", "0011_itemcronogramasuprimento_tipo_fluxo_compra"),
        ("compras", "0021_arquivos_privados"),
    ]

    operations = [
        migrations.AddField(
            model_name="processocompra",
            name="fluxo_grande_fornecedor",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Congela a classificação do suprimento no momento da abertura do processo.",
            ),
        ),
        migrations.CreateModel(
            name="GrandeFornecedorProcesso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fornecedor_confirmado_em", models.DateTimeField(blank=True, null=True)),
                ("condicao_pagamento_resumo", models.TextField(blank=True)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("fornecedor_escolhido", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="processos_grande_fornecedor_escolhidos", to="cadastros.fornecedor")),
                ("processo", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="grande_fornecedor", to="compras.processocompra")),
            ],
            options={"verbose_name": "Fluxo de grande fornecedor", "verbose_name_plural": "Fluxos de grandes fornecedores"},
        ),
        migrations.CreateModel(
            name="GrandeFornecedorParticipante",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("documento_contrato", models.FileField(blank=True, storage=core.storage.PrivateMediaStorage(), upload_to="compras/grandes_fornecedores/contratos/%Y/%m/")),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("fluxo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participantes", to="compras.grandefornecedorprocesso")),
                ("fornecedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participacoes_grande_fornecedor", to="cadastros.fornecedor")),
            ],
            options={"ordering": ("fornecedor__nome", "id")},
        ),
        migrations.CreateModel(
            name="GrandeFornecedorItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pavimento", models.CharField(blank=True, max_length=120)),
                ("local", models.CharField(blank=True, max_length=255)),
                ("item", models.CharField(max_length=500)),
                ("unidade", models.CharField(default="UN", max_length=20)),
                ("quantidade", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("status", models.CharField(choices=[("AGUARDANDO", "Aguardando fornecedor"), ("PRODUCAO", "Em produção"), ("PRONTO", "Pronto para expedição"), ("TRANSPORTE", "Em transporte"), ("PARCIAL", "Entrega parcial"), ("ENTREGUE", "Entregue"), ("CANCELADO", "Cancelado")], db_index=True, default="AGUARDANDO", max_length=20)),
                ("quantidade_recebida", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0"))])),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("fluxo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="compras.grandefornecedorprocesso")),
                ("necessidade_gerada", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="item_grande_fornecedor", to="compras.necessidadecompra")),
                ("pedido_item", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="item_grande_fornecedor", to="compras.pedidocompraitem")),
            ],
            options={"ordering": ("ordem", "id")},
        ),
        migrations.CreateModel(
            name="GrandeFornecedorOferta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valor_inicial", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("valor_atual", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ofertas_grandes_fornecedores_editadas", to=settings.AUTH_USER_MODEL)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ofertas", to="compras.grandefornecedoritem")),
                ("participante", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ofertas", to="compras.grandefornecedorparticipante")),
            ],
        ),
        migrations.CreateModel(
            name="HistoricoValorGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valor_anterior", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("valor_novo", models.DecimalField(decimal_places=4, max_digits=18)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("oferta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historico", to="compras.grandefornecedoroferta")),
                ("usuario", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historico_valores_grandes_fornecedores", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-criado_em", "-id")},
        ),
        migrations.CreateModel(
            name="ParcelaGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("descricao", models.CharField(max_length=255)),
                ("percentual", models.DecimalField(blank=True, decimal_places=4, max_digits=7, null=True)),
                ("valor", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("data_prevista", models.DateField(blank=True, null=True)),
                ("gatilho", models.CharField(choices=[("DATA", "Data"), ("ASSINATURA", "Assinatura"), ("PROJETO", "Aprovação de projeto"), ("FABRICACAO", "Fabricação"), ("ENTREGA", "Entrega"), ("INSTALACAO", "Instalação"), ("OUTRO", "Outro")], default="DATA", max_length=20)),
                ("status", models.CharField(choices=[("PREVISTO", "Previsto"), ("LIBERADO", "Liberado"), ("PAGO", "Pago"), ("CANCELADO", "Cancelado")], default="PREVISTO", max_length=20)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("fluxo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parcelas", to="compras.grandefornecedorprocesso")),
            ],
            options={"ordering": ("ordem", "id")},
        ),
        migrations.CreateModel(
            name="RateioParcelaGrandeFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("beneficiario_nome", models.CharField(max_length=255)),
                ("documento", models.CharField(blank=True, max_length=40)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("parcela", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rateios", to="compras.parcelagrandefornecedor")),
            ],
            options={"ordering": ("id",)},
        ),
        migrations.AddConstraint(
            model_name="grandefornecedorparticipante",
            constraint=models.UniqueConstraint(fields=("fluxo", "fornecedor"), name="comp_gf_part_fluxo_forn_uniq"),
        ),
        migrations.AddConstraint(
            model_name="grandefornecedoroferta",
            constraint=models.UniqueConstraint(fields=("item", "participante"), name="comp_gf_oferta_item_part_uniq"),
        ),
        migrations.AddIndex(
            model_name="grandefornecedoritem",
            index=models.Index(fields=["fluxo", "status"], name="comp_gf_item_status_idx"),
        ),
    ]
