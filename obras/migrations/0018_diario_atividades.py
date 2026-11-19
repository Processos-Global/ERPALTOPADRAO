import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("obras", "0017_concretagem_mapa"),
        ("planejamento", "0017_reclassificar_categorias_gf_definitivo"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiarioAtividadeAdicional",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao", models.TextField()),
                ("justificativa", models.TextField()),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("diario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atividades_adicionais", to="obras.diarioobra")),
            ],
        ),
        migrations.CreateModel(
            name="DiarioAtividadePlanejada",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origem", models.CharField(choices=[("SEMANAL", "Cronograma semanal"), ("PRE_HABITESE", "Checklist Pré Habite-se"), ("POS_HABITESE", "Checklist Pós Habite-se")], max_length=20)),
                ("semana", models.PositiveIntegerField()),
                ("inicio_semana", models.DateField()),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atividade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="registros_diario", to="planejamento.atividadeplanejamento")),
                ("diario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atividades_planejadas", to="obras.diarioobra")),
            ],
        ),
        migrations.AddConstraint(
            model_name="diarioatividadeplanejada",
            constraint=models.UniqueConstraint(fields=("diario", "atividade"), name="obr_diario_atividade_uniq"),
        ),
    ]
