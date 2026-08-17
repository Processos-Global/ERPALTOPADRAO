from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0004_refatoracao_origem_itens_compra"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="processocompra",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"),
                    ("AGUARDANDO_COTACAO", "Aguardando cotação"),
                    ("EM_COTACAO", "Em cotação"),
                    ("AGUARDANDO_COMPATIBILIZACAO", "Aguardando análise técnica"),
                    ("EM_COMPATIBILIZACAO", "Em análise técnica"),
                    ("EM_NEGOCIACAO", "Em negociação"),
                    ("AGUARDANDO_APROVACAO", "Aguardando aprovação"),
                    ("AJUSTE_SOLICITADO", "Ajuste solicitado"),
                    ("APROVADO", "Aprovado"),
                    ("EM_CONTRATACAO", "Em contratação"),
                    ("CONTRATADO", "Contratado"),
                    ("REPROVADO", "Reprovado"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="RASCUNHO",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="adjudicacaocompra",
            name="desconto_final",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text="Desconto congelado para a quantidade adjudicada.",
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="pedidocompra",
            name="recebido_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="pedidocompra",
            name="recebido_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pedidos_compra_recebidos",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="pedidocompraitem",
            name="desconto",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.AddField(
            model_name="pedidocompraitem",
            name="quantidade_recebida",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=18,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))],
            ),
        ),
        migrations.CreateModel(
            name="RecebimentoPedido",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("pedido", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recebimentos", to="compras.pedidocompra")),
                ("usuario", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recebimentos_pedidos_compra", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-criado_em", "-id")},
        ),
        migrations.CreateModel(
            name="RecebimentoPedidoItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantidade", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("item_pedido", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recebimentos", to="compras.pedidocompraitem")),
                ("recebimento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="compras.recebimentopedido")),
            ],
        ),
        migrations.AddConstraint(
            model_name="recebimentopedidoitem",
            constraint=models.UniqueConstraint(fields=("recebimento", "item_pedido"), name="comp_rec_item_uniq"),
        ),
        migrations.AddIndex(
            model_name="pedidocompra",
            index=models.Index(fields=["obra", "status"], name="comp_ped_obra_st_idx"),
        ),
        migrations.AddIndex(
            model_name="pedidocompra",
            index=models.Index(fields=["processo", "fornecedor"], name="comp_ped_proc_forn_idx"),
        ),
    ]
