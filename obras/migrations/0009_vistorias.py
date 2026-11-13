from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("obras", "0008_movimento_custo_transferencia"),
        ("planejamento", "0017_reclassificar_categorias_gf_definitivo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="VistoriaItem", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("status", models.CharField(max_length=12, default="NAO_FEITO", choices=[("FEITO", "Feito"), ("NAO_FEITO", "Não feito")])),
            ("atualizado_em", models.DateTimeField(auto_now=True)),
            ("atividade", models.OneToOneField(to="planejamento.atividadeplanejamento", on_delete=django.db.models.deletion.PROTECT, related_name="vistoria_item")),
            ("atualizado_por", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL)),
        ], options={"verbose_name": "Item de vistoria", "verbose_name_plural": "Itens de vistoria"}),
        migrations.CreateModel(name="VistoriaHistorico", fields=[
            ("id", models.BigAutoField(primary_key=True, serialize=False)),
            ("status_anterior", models.CharField(max_length=12, blank=True)),
            ("status_novo", models.CharField(max_length=12)),
            ("data", models.DateTimeField(auto_now_add=True)),
            ("item", models.ForeignKey(to="obras.vistoriaitem", related_name="historico", on_delete=django.db.models.deletion.CASCADE)),
            ("usuario", models.ForeignKey(to=settings.AUTH_USER_MODEL, null=True, on_delete=django.db.models.deletion.SET_NULL)),
        ], options={"ordering": ("-data", "-id")}),
    ]
