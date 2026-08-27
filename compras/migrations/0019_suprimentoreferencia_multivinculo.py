from django.db import migrations, models


def vincular_historicos_erp_existentes(apps, schema_editor):
    """
    Mantém compras já geradas automaticamente pelo ERP ligadas
    à nova referência canônica.

    Históricos LEGADO não são vinculados aqui porque o importador
    principal fará a associação correta, inclusive múltipla.
    """
    Historico = apps.get_model("compras", "HistoricoCompraSuprimento")
    Referencia = apps.get_model("compras", "SuprimentoReferencia")

    historicos = (
        Historico.objects
        .filter(origem="ERP")
        .exclude(suprimento_chave="")
        .order_by("id")
    )

    for historico in historicos.iterator():
        referencia, _ = Referencia.objects.get_or_create(
            chave=historico.suprimento_chave,
            defaults={
                "nome": historico.suprimento,
                "ativo": True,
            },
        )
        historico.suprimentos_referencia.add(referencia)


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0018_historicocomprasuprimento"),
    ]

    operations = [
        migrations.CreateModel(
            name="SuprimentoReferencia",
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
                ("nome", models.CharField(max_length=500)),
                (
                    "chave",
                    models.CharField(
                        db_index=True,
                        max_length=500,
                        unique=True,
                    ),
                ),
                (
                    "ativo",
                    models.BooleanField(
                        db_index=True,
                        default=True,
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Referência de suprimento",
                "verbose_name_plural": "Referências de suprimentos",
                "ordering": ("nome",),
            },
        ),
        migrations.AddField(
            model_name="historicocomprasuprimento",
            name="suprimentos_referencia",
            field=models.ManyToManyField(
                blank=True,
                related_name="historicos",
                to="compras.suprimentoreferencia",
            ),
        ),
        migrations.RunPython(
            vincular_historicos_erp_existentes,
            migrations.RunPython.noop,
        ),
    ]
