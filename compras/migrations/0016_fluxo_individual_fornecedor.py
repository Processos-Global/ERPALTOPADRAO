from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("compras", "0015_solicitacao_cotacao_fornecedor"),
    ]

    operations = [
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_negociacao_em",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_negociacao_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cotacoes_enviadas_negociacao", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_aprovacao_em",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="cotacaofornecedor",
            name="enviada_aprovacao_por",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cotacoes_enviadas_aprovacao", to=settings.AUTH_USER_MODEL),
        ),
    ]
