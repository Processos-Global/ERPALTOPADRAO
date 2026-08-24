from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def marcar_cotacoes_legadas_como_enviadas(apps, schema_editor):
    CotacaoFornecedor = apps.get_model("compras", "CotacaoFornecedor")
    CotacaoFornecedor.objects.filter(
        processo__etapa_atual__in=[
            "COMPATIBILIZACAO",
            "NEGOCIACAO",
            "APROVACAO",
            "CONTRATACAO",
            "CONTRATADO",
        ],
        itens__isnull=False,
        enviada_compatibilizacao_em__isnull=True,
    ).distinct().update(enviada_compatibilizacao_em=timezone.now())


def desfazer_marcacao_legada(apps, schema_editor):
    # Não limpamos automaticamente porque propostas novas podem ter sido
    # enviadas legitimamente depois da migração.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0010_alter_historicoprevisaopedido_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="fornecedorcompra",
            name="avaliacao",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Avaliação comercial do fornecedor, de 0 a 5.",
                max_digits=3,
                null=True,
                validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
            ),
        ),
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_compatibilizacao_em",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_compatibilizacao_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cotacoes_enviadas_compatibilizacao",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            marcar_cotacoes_legadas_como_enviadas,
            desfazer_marcacao_legada,
        ),
        migrations.AlterField(
            model_name="processocompra",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"),
                    ("PEDIDO_ENVIADO", "Pedido enviado"),
                    ("SOLICITACAO_COTACAO", "Solicitação de cotação"),
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
    ]
