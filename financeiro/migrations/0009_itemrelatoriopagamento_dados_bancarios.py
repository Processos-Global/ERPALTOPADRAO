from django.db import migrations, models


def preencher_dados_bancarios_existentes(apps, schema_editor):
    Item = apps.get_model("financeiro", "ItemRelatorioPagamento")

    for item in Item.objects.select_related("titulo__fornecedor").iterator():
        titulo = item.titulo
        fornecedor = getattr(titulo, "fornecedor", None)
        if not fornecedor:
            continue

        item.beneficiario_banco = fornecedor.banco or ""
        item.beneficiario_agencia = fornecedor.agencia or ""
        item.beneficiario_conta_corrente = fornecedor.conta_corrente or ""
        item.beneficiario_operacao = fornecedor.operacao_bancaria or ""
        item.beneficiario_pix = fornecedor.pix or ""
        item.beneficiario_titular = fornecedor.titular_conta or ""
        if not item.beneficiario_documento:
            item.beneficiario_documento = fornecedor.documento or ""
        item.save(update_fields=[
            "beneficiario_banco",
            "beneficiario_agencia",
            "beneficiario_conta_corrente",
            "beneficiario_operacao",
            "beneficiario_pix",
            "beneficiario_titular",
            "beneficiario_documento",
        ])


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0007_dados_bancarios_fornecedor"),
        ("financeiro", "0008_itemrelatoriopagamento_campos_programacao"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_banco",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_agencia",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_conta_corrente",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_operacao",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_pix",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="itemrelatoriopagamento",
            name="beneficiario_titular",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(preencher_dados_bancarios_existentes, migrations.RunPython.noop),
    ]
