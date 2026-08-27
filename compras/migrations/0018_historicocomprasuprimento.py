import re
import unicodedata

import django.db.models.deletion
from django.db import migrations, models


def _normalizar(valor):
    texto = str(valor or "").strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", texto).strip()


def preencher_processos_ja_contratados(apps, schema_editor):
    Historico = apps.get_model("compras", "HistoricoCompraSuprimento")
    Processo = apps.get_model("compras", "ProcessoCompra")
    Pedido = apps.get_model("compras", "PedidoCompra")

    status_confirmados = {
        "CONFIRMADO",
        "EM_PRODUCAO",
        "PRONTO_EXPEDICAO",
        "EM_TRANSPORTE",
        "ENTREGA_PARCIAL",
        "ENTREGUE",
    }

    processos = (
        Processo.objects
        .filter(status="CONTRATADO")
        .select_related("obra", "item_cronograma", "item_cronograma__cronograma_obra")
    )

    for processo in processos.iterator():
        item = processo.item_cronograma
        cronograma_obra = getattr(item, "cronograma_obra", None)
        codigo = (getattr(cronograma_obra, "codigo_aba", "") or "").strip()
        data = processo.data_contratacao_concluida.date() if processo.data_contratacao_concluida else None

        pedidos = (
            Pedido.objects
            .filter(processo=processo, status__in=status_confirmados)
            .select_related("fornecedor")
        )
        for pedido in pedidos.iterator():
            Historico.objects.update_or_create(
                pedido_id=pedido.pk,
                defaults={
                    "suprimento": item.item,
                    "suprimento_chave": _normalizar(item.item),
                    "obra_id": processo.obra_id,
                    "obra_codigo": codigo,
                    "obra_nome": str(processo.obra),
                    "fornecedor_id": pedido.fornecedor_id,
                    "fornecedor_nome": pedido.fornecedor.nome,
                    "valor": pedido.valor_total,
                    "data_fechamento": data,
                    "origem": "ERP",
                    "processo_id": processo.pk,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0017_central_cadastros_materiais_fornecedores"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoricoCompraSuprimento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("suprimento", models.CharField(db_index=True, max_length=500)),
                ("suprimento_chave", models.CharField(db_index=True, max_length=500)),
                ("obra_codigo", models.CharField(blank=True, db_index=True, max_length=50)),
                ("obra_nome", models.CharField(blank=True, max_length=255)),
                ("fornecedor_nome", models.CharField(max_length=255)),
                ("valor", models.DecimalField(decimal_places=2, max_digits=18)),
                ("data_fechamento", models.DateField(blank=True, db_index=True, null=True)),
                ("origem", models.CharField(choices=[("LEGADO", "Histórico importado"), ("ERP", "ERP Alto Padrão")], db_index=True, default="ERP", max_length=10)),
                ("arquivo_origem", models.CharField(blank=True, max_length=255)),
                ("aba_origem", models.CharField(blank=True, max_length=255)),
                ("linha_origem", models.PositiveIntegerField(blank=True, null=True)),
                ("chave_importacao", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("fornecedor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historico_compras_suprimentos", to="cadastros.fornecedor")),
                ("obra", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historico_compras_suprimentos", to="obras.obra")),
                ("pedido", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historico_suprimento", to="compras.pedidocompra")),
                ("processo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="registros_historico_suprimento", to="compras.processocompra")),
            ],
            options={
                "verbose_name": "Histórico de compra de suprimento",
                "verbose_name_plural": "Histórico de compras de suprimentos",
                "ordering": ("-data_fechamento", "-id"),
                "indexes": [
                    models.Index(fields=["suprimento_chave", "data_fechamento"], name="comp_hist_sup_data_idx"),
                    models.Index(fields=["obra", "suprimento_chave"], name="comp_hist_obra_sup_idx"),
                    models.Index(fields=["origem", "processo"], name="comp_hist_orig_proc_idx"),
                ],
            },
        ),
        migrations.RunPython(preencher_processos_ja_contratados, migrations.RunPython.noop),
    ]
