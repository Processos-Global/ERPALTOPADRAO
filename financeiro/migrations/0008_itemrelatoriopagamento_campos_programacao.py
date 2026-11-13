from django.db import migrations, models


def preencher_campos_existentes(apps, schema_editor):
    Item = apps.get_model("financeiro", "ItemRelatorioPagamento")

    for item in Item.objects.select_related("titulo__plano_financeiro").iterator():
        titulo = item.titulo
        plano = getattr(titulo, "plano_financeiro", None)
        item.documento_numero = titulo.documento_numero or ""
        item.competencia = titulo.competencia
        item.centro_custo_codigo = plano.codigo if plano else ""
        item.centro_custo_descricao = plano.nome if plano else ""
        item.forma_pagamento = titulo.condicao_pagamento or ""
        item.save(
            update_fields=[
                "documento_numero",
                "competencia",
                "centro_custo_codigo",
                "centro_custo_descricao",
                "forma_pagamento",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("financeiro", "0007_relatorios_pagamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="documento_numero",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="competencia",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="centro_custo_codigo",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="centro_custo_descricao",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="forma_pagamento",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(preencher_campos_existentes, migrations.RunPython.noop),
    ]
