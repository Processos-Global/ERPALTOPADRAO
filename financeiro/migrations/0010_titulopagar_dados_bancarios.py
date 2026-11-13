from django.db import migrations, models


def preencher_snapshot_titulos_existentes(apps, schema_editor):
    TituloPagar = apps.get_model("financeiro", "TituloPagar")

    for titulo in TituloPagar.objects.select_related("fornecedor").iterator():
        fornecedor = getattr(titulo, "fornecedor", None)
        if not fornecedor:
            continue

        campos = {
            "beneficiario_documento": titulo.beneficiario_documento or fornecedor.documento or "",
            "beneficiario_banco": fornecedor.banco or "",
            "beneficiario_agencia": fornecedor.agencia or "",
            "beneficiario_conta_corrente": fornecedor.conta_corrente or "",
            "beneficiario_operacao": fornecedor.operacao_bancaria or "",
            "beneficiario_pix": fornecedor.pix or "",
            "beneficiario_titular": fornecedor.titular_conta or "",
        }
        TituloPagar.objects.filter(pk=titulo.pk).update(**campos)


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0007_dados_bancarios_fornecedor"),
        ("financeiro", "0009_itemrelatoriopagamento_dados_bancarios"),
    ]

    operations = [
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_banco",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_agencia",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_conta_corrente",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_operacao",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_pix",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_titular",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(preencher_snapshot_titulos_existentes, migrations.RunPython.noop),
    ]
