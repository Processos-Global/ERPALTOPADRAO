from django.db import migrations, models


def normalizar_dados(apps, schema_editor):
    TituloPagar = apps.get_model("financeiro", "TituloPagar")
    PrevisaoFinanceira = apps.get_model("financeiro", "PrevisaoFinanceira")

    mapa_status = {
        "RASCUNHO": "PREVISTA",
        "DOCUMENTO_RECEBIDO": "AGUARDANDO_APROVACAO",
        "EM_CONFERENCIA": "AGUARDANDO_APROVACAO",
        "BLOQUEADO": "PREVISTA",
    }
    mapa_origem = {
        "MEDICAO": "MAO_OBRA",
    }

    for titulo in TituloPagar.objects.select_related("fornecedor").all().iterator():
        campos = []
        novo_status = mapa_status.get(titulo.status)
        if novo_status:
            titulo.status = novo_status
            campos.append("status")
        nova_origem = mapa_origem.get(titulo.origem)
        if nova_origem:
            titulo.origem = nova_origem
            campos.append("origem")
        if not titulo.beneficiario_nome and titulo.fornecedor_id:
            fornecedor = titulo.fornecedor
            nome = getattr(fornecedor, "nome_fantasia", "") or getattr(fornecedor, "nome", "") or str(fornecedor)
            titulo.beneficiario_nome = nome
            campos.append("beneficiario_nome")
        if campos:
            titulo.save(update_fields=campos)

    # Compras passam a ser previstas pelas próprias Contas a Pagar.
    PrevisaoFinanceira.objects.filter(origem="COMPRA").update(ativa=False)


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0003_arquivos_privados"),
    ]

    operations = [
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_documento",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="beneficiario_nome",
            field=models.CharField(blank=True, db_index=True, max_length=255),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="condicao_pagamento",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="gatilho_pagamento",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="origem_detalhe",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="parcela_descricao",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="parcela_ordem",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="parcela_total",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="titulopagar",
            name="referencia_externa",
            field=models.CharField(blank=True, help_text="Chave idempotente da origem integrada, ex.: COMPRA_PARCELA:123.", max_length=120, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name="titulopagar",
            name="origem",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Lançamento manual"),
                    ("COMPRA", "Compras"),
                    ("MAO_OBRA", "Mão de obra"),
                    ("GRANDE_FORNECEDOR", "Grande fornecedor"),
                    ("CONTRATO", "Contrato (legado)"),
                    ("MEDICAO", "Medição (legado)"),
                    ("DESPESA", "Despesa (legado)"),
                    ("IMPOSTO", "Imposto (legado)"),
                    ("ADIANTAMENTO", "Adiantamento (legado)"),
                    ("REEMBOLSO", "Reembolso (legado)"),
                    ("FOLHA", "Folha (legado)"),
                    ("OUTRO", "Outro (legado)"),
                ],
                db_index=True,
                default="MANUAL",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="titulopagar",
            name="status",
            field=models.CharField(
                choices=[
                    ("PREVISTA", "Prevista"),
                    ("AGUARDANDO_APROVACAO", "Aguardando aprovação"),
                    ("APROVADO", "Aprovado"),
                    ("PAGO", "Pago"),
                    ("REJEITADO", "Rejeitado"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="PREVISTA",
                max_length=30,
            ),
        ),
        migrations.AddIndex(
            model_name="titulopagar",
            index=models.Index(fields=["origem", "status"], name="fin_tit_orig_st_idx"),
        ),
        migrations.RunPython(normalizar_dados, migrations.RunPython.noop),
    ]
