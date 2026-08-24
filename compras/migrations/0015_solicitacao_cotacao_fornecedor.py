from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def preencher_solicitacoes_existentes(apps, schema_editor):
    ProcessoCompra = apps.get_model("compras", "ProcessoCompra")
    CotacaoFornecedor = apps.get_model("compras", "CotacaoFornecedor")
    Solicitacao = apps.get_model("compras", "SolicitacaoCotacaoFornecedor")

    agora = timezone.now()

    for processo in ProcessoCompra.objects.all().iterator():
        cotacoes = {
            cotacao.fornecedor_id: cotacao
            for cotacao in CotacaoFornecedor.objects.filter(processo_id=processo.id)
        }
        ids_fornecedores = set(
            processo.fornecedores_sugeridos.values_list("id", flat=True)
        ) | set(cotacoes.keys())

        registros = []
        for fornecedor_id in ids_fornecedores:
            cotacao = cotacoes.get(fornecedor_id)
            if cotacao is not None:
                registros.append(
                    Solicitacao(
                        processo_id=processo.id,
                        fornecedor_id=fornecedor_id,
                        status="RESPONDIDA",
                        respondida_em=cotacao.criado_em or agora,
                    )
                )
            else:
                registros.append(
                    Solicitacao(
                        processo_id=processo.id,
                        fornecedor_id=fornecedor_id,
                        status="PENDENTE_ENVIO",
                    )
                )

        if registros:
            Solicitacao.objects.bulk_create(registros, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("compras", "0014_ajuste_labels_status_suprimentos"),
    ]

    operations = [
        migrations.CreateModel(
            name="SolicitacaoCotacaoFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PENDENTE_ENVIO", "Pendente de envio"), ("ENVIADA", "Aguardando proposta"), ("RESPONDIDA", "Proposta recebida"), ("CANCELADA", "Cancelada")], db_index=True, default="PENDENTE_ENVIO", max_length=20)),
                ("meio_envio", models.CharField(blank=True, choices=[("EMAIL", "E-mail"), ("WHATSAPP", "WhatsApp"), ("TELEFONE", "Telefone"), ("PORTAL", "Portal do fornecedor"), ("OUTRO", "Outro")], max_length=20)),
                ("observacao_envio", models.TextField(blank=True)),
                ("enviada_em", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("respondida_em", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("enviada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="solicitacoes_cotacao_enviadas", to=settings.AUTH_USER_MODEL)),
                ("fornecedor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="solicitacoes_cotacao", to="compras.fornecedorcompra")),
                ("processo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="solicitacoes_cotacao", to="compras.processocompra")),
            ],
            options={"ordering": ("fornecedor__nome", "id")},
        ),
        migrations.AddConstraint(
            model_name="solicitacaocotacaofornecedor",
            constraint=models.UniqueConstraint(fields=("processo", "fornecedor"), name="comp_solcot_proc_forn_uniq"),
        ),
        migrations.RunPython(preencher_solicitacoes_existentes, migrations.RunPython.noop),
    ]
