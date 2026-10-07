from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0010_modelos_fvs"),
        ("obras", "0004_estoque_diario"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FVS",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(blank=True, max_length=30, unique=True, verbose_name="Número")),
                ("modelo_nome", models.CharField(max_length=180, verbose_name="Modelo")),
                ("modelo_revisao", models.CharField(max_length=30, verbose_name="Revisão")),
                ("normas_referencias", models.TextField(blank=True, verbose_name="Normas / referências")),
                ("pavimento_etapa", models.CharField(blank=True, max_length=120, verbose_name="Pavimento / etapa")),
                ("empresa_executora", models.CharField(blank=True, max_length=180, verbose_name="Empresa executora")),
                ("responsavel_execucao", models.CharField(blank=True, max_length=180, verbose_name="Responsável pela execução")),
                ("responsavel_inspecao", models.CharField(blank=True, max_length=180, verbose_name="Responsável pela inspeção")),
                ("projeto_versao", models.CharField(blank=True, max_length=180, verbose_name="Projeto / versão")),
                ("data_abertura", models.DateField(auto_now_add=True, verbose_name="Data de abertura")),
                ("data_fechamento", models.DateField(blank=True, null=True, verbose_name="Data de fechamento")),
                ("status", models.CharField(choices=[("RASCUNHO", "Rascunho"), ("EM_PREENCHIMENTO", "Em preenchimento"), ("AGUARDANDO_APROVACAO", "Aguardando aprovação"), ("DEVOLVIDA", "Devolvida para correção"), ("APROVADA", "Aprovada pelo gestor")], default="RASCUNHO", max_length=30, verbose_name="Status")),
                ("parecer", models.CharField(blank=True, choices=[("APROVADA", "Aprovada"), ("APROVADA_RESTRICAO", "Aprovada com restrição"), ("REPROVADA", "Reprovada")], max_length=30, verbose_name="Parecer técnico")),
                ("observacao_final", models.TextField(blank=True, verbose_name="Observação final")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("enviado_aprovacao_em", models.DateTimeField(blank=True, null=True)),
                ("aprovado_em", models.DateTimeField(blank=True, null=True)),
                ("ambientes", models.ManyToManyField(related_name="fvs", to="obras.ambiente", verbose_name="Ambientes")),
                ("aprovado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="fvs_aprovadas", to=settings.AUTH_USER_MODEL)),
                ("criado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fvs_criadas", to=settings.AUTH_USER_MODEL, verbose_name="Criado por")),
                ("enviado_aprovacao_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="fvs_enviadas_aprovacao", to=settings.AUTH_USER_MODEL)),
                ("modelo_origem", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fvs_geradas", to="cadastros.modelofvs", verbose_name="Modelo de origem")),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="fvs", to="obras.obra", verbose_name="Obra")),
            ],
            options={
                "verbose_name": "FVS",
                "verbose_name_plural": "FVS",
                "ordering": ["-criado_em"],
                "permissions": [("aprovar_fvs", "Pode aprovar e devolver FVS")],
            },
        ),
        migrations.CreateModel(
            name="FVSItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ordem", models.PositiveIntegerField(default=1)),
                ("item_verificacao", models.CharField(max_length=255)),
                ("metodo_instrumento", models.CharField(blank=True, max_length=255)),
                ("criterio_aceite", models.TextField(blank=True)),
                ("tolerancia", models.TextField(blank=True)),
                ("obrigatorio", models.BooleanField(default=True)),
                ("resultado", models.CharField(blank=True, choices=[("C", "Conforme"), ("NC", "Não conforme"), ("NA", "Não aplicável")], max_length=2, verbose_name="Resultado")),
                ("data_verificacao", models.DateField(blank=True, null=True, verbose_name="Data da verificação")),
                ("observacao", models.TextField(blank=True, verbose_name="Observações / ações corretivas")),
                ("fvs", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="obras.fvs", verbose_name="FVS")),
            ],
            options={"verbose_name": "Item da FVS", "verbose_name_plural": "Itens da FVS", "ordering": ["ordem", "pk"]},
        ),
        migrations.CreateModel(
            name="FVSHistorico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("acao", models.CharField(choices=[("CRIADA", "Criada"), ("SALVA", "Preenchimento salvo"), ("ENVIADA", "Enviada para aprovação"), ("DEVOLVIDA", "Devolvida para correção"), ("APROVADA", "Aprovada pelo gestor")], max_length=20)),
                ("observacao", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("fvs", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historico", to="obras.fvs")),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="historico_fvs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Histórico da FVS", "verbose_name_plural": "Históricos da FVS", "ordering": ["-criado_em"]},
        ),
        migrations.AddIndex(model_name="fvs", index=models.Index(fields=["obra", "status"], name="obras_fvs_obra_status_idx")),
        migrations.AddIndex(model_name="fvs", index=models.Index(fields=["status", "criado_em"], name="obras_fvs_status_data_idx")),
    ]
