from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0005_especificacao_pagamento"),
        ("cadastros", "0003_remover_atividade_subatividade_material"),
    ]

    operations = [
        migrations.AddField(
            model_name="titulopagar",
            name="materiais",
            field=models.ManyToManyField(
                blank=True,
                help_text="Materiais selecionados em solicitações avulsas do tipo material.",
                related_name="titulos_financeiros_manuais",
                to="cadastros.material",
            ),
        ),
    ]
