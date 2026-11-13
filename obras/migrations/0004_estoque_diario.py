from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0004_ficha_tecnica_base"),
        ("obras", "0003_alter_fichatecnicaobra_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DiarioObra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data", models.DateField(db_index=True)),
                ("clima", models.CharField(blank=True, choices=[("ENSOLARADO", "Ensolarado"), ("PARCIALMENTE_NUBLADO", "Parcialmente nublado"), ("NUBLADO", "Nublado"), ("CHUVA_LEVE", "Chuva leve"), ("CHUVA_FORTE", "Chuva forte"), ("OUTRO", "Outro")], max_length=30)),
                ("efetivo", models.PositiveIntegerField(blank=True, null=True, verbose_name="Efetivo no dia")),
                ("servicos_executados", models.TextField(verbose_name="Serviços executados")),
                ("equipe_presente", models.TextField(blank=True, verbose_name="Equipe / terceiros presentes")),
                ("ocorrencias", models.TextField(blank=True, verbose_name="Ocorrências / impedimentos")),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="diarios", to="obras.obra")),
                ("registrado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="diarios_obra_registrados", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Diário de obra", "verbose_name_plural": "Diários de obra", "ordering": ("-data", "-id")},
        ),
        migrations.CreateModel(
            name="MovimentoEstoque",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("SAIDA", "Saída"), ("TRANSFERENCIA", "Transferência")], db_index=True, max_length=20)),
                ("descricao_item", models.CharField(max_length=500, verbose_name="Item")),
                ("unidade", models.CharField(max_length=20, verbose_name="Unidade")),
                ("quantidade", models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))])),
                ("data_movimento", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("finalidade", models.CharField(blank=True, max_length=255)),
                ("documento_referencia", models.CharField(blank=True, max_length=100)),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="movimentos_estoque_criados", to=settings.AUTH_USER_MODEL)),
                ("material", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimentos_estoque_obras", to="cadastros.material", verbose_name="Material")),
                ("obra_destino", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="movimentos_estoque_entrada", to="obras.obra", verbose_name="Obra de destino")),
                ("obra_origem", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimentos_estoque_saida", to="obras.obra", verbose_name="Obra de origem")),
            ],
            options={"verbose_name": "Movimento de estoque", "verbose_name_plural": "Movimentos de estoque", "ordering": ("-data_movimento", "-id")},
        ),
        migrations.AddConstraint(
            model_name="diarioobra",
            constraint=models.UniqueConstraint(fields=("obra", "data"), name="obras_diario_obra_data_uniq"),
        ),
        migrations.AddIndex(
            model_name="diarioobra",
            index=models.Index(fields=["obra", "data"], name="obras_diario_obra_dt_idx"),
        ),
        migrations.AddIndex(
            model_name="movimentoestoque",
            index=models.Index(fields=["obra_origem", "tipo", "data_movimento"], name="obr_mov_orig_tipo_dt_idx"),
        ),
        migrations.AddIndex(
            model_name="movimentoestoque",
            index=models.Index(fields=["obra_destino", "data_movimento"], name="obr_mov_dest_dt_idx"),
        ),
        migrations.AddIndex(
            model_name="movimentoestoque",
            index=models.Index(fields=["material", "unidade"], name="obr_mov_mat_un_idx"),
        ),
    ]
