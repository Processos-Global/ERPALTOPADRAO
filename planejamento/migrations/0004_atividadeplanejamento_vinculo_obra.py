import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("obras", "0001_initial"),
        ("planejamento", "0003_registrocronograma_chave_atividade_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AtividadePlanejamento",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("chave", models.CharField(db_index=True, max_length=64, unique=True)),
                ("projeto_origem", models.CharField(blank=True, db_index=True, max_length=255)),
                ("disciplina", models.CharField(blank=True, db_index=True, max_length=255)),
                ("local_tarefa", models.TextField(blank=True)),
                ("nome_tarefa", models.TextField(blank=True)),
                ("ativa", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "obra",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="atividades_planejamento",
                        to="obras.obra",
                    ),
                ),
            ],
            options={
                "verbose_name": "Atividade de planejamento",
                "verbose_name_plural": "Atividades de planejamento",
                "ordering": ("obra", "disciplina", "local_tarefa", "nome_tarefa"),
                "indexes": [
                    models.Index(fields=["obra", "ativa"], name="plan_atv_obra_ativa_idx"),
                    models.Index(fields=["obra", "disciplina"], name="plan_atv_obra_disc_idx"),
                ],
            },
        ),
        migrations.AddField(
            model_name="registrocronograma",
            name="obra",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="registros_cronograma_planejamento",
                to="obras.obra",
            ),
        ),
        migrations.AddField(
            model_name="registrocronograma",
            name="atividade_planejamento",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="snapshots",
                to="planejamento.atividadeplanejamento",
            ),
        ),
        migrations.AddIndex(
            model_name="registrocronograma",
            index=models.Index(
                fields=["importacao", "obra", "semana"],
                name="plan_imp_obra_sem_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="registrocronograma",
            index=models.Index(
                fields=["importacao", "atividade_planejamento", "semana"],
                name="plan_imp_atv_sem_idx",
            ),
        ),
    ]
