from django.db import migrations, models
import django.db.models.deletion


def consolidar_pagamentos_duplicados(apps, schema_editor):
    Pagamento = apps.get_model("financeiro", "Pagamento")
    titulos = (
        Pagamento.objects.values_list("titulo_id", flat=True)
        .order_by()
        .distinct()
    )
    for titulo_id in titulos:
        pagamentos = list(Pagamento.objects.filter(titulo_id=titulo_id).order_by("-data_pagamento", "-id"))
        if len(pagamentos) <= 1:
            continue
        manter = pagamentos[0]
        Pagamento.objects.filter(titulo_id=titulo_id).exclude(pk=manter.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("financeiro", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(consolidar_pagamentos_duplicados, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="aprovacaotitulofinanceiro",
            name="fin_aprov_tit_ciclo_alc_uniq",
        ),
        migrations.RemoveField(
            model_name="aprovacaotitulofinanceiro",
            name="alcada",
        ),
        migrations.AddConstraint(
            model_name="aprovacaotitulofinanceiro",
            constraint=models.UniqueConstraint(fields=("titulo", "ciclo"), name="fin_aprov_tit_ciclo_uniq"),
        ),
        migrations.RemoveField(
            model_name="pagamento",
            name="lote",
        ),
        migrations.RemoveIndex(
            model_name="pagamento",
            name="fin_pag_conta_data_idx",
        ),
        migrations.RemoveField(
            model_name="pagamento",
            name="conta_bancaria",
        ),
        migrations.AlterField(
            model_name="pagamento",
            name="titulo",
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="pagamento", to="financeiro.titulopagar"),
        ),
        migrations.AlterField(
            model_name="titulopagar",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"),
                    ("DOCUMENTO_RECEBIDO", "Documento recebido"),
                    ("EM_CONFERENCIA", "Em conferência"),
                    ("AGUARDANDO_APROVACAO", "Aguardando aprovação"),
                    ("APROVADO", "Aprovado"),
                    ("PAGO", "Pago"),
                    ("BLOQUEADO", "Bloqueado"),
                    ("REJEITADO", "Rejeitado"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="RASCUNHO",
                max_length=30,
            ),
        ),
        migrations.DeleteModel(name="ItemLotePagamento"),
        migrations.DeleteModel(name="MovimentacaoBancaria"),
        migrations.DeleteModel(name="LotePagamento"),
        migrations.DeleteModel(name="ContaBancaria"),
        migrations.DeleteModel(name="AlcadaAprovacaoFinanceira"),
    ]
