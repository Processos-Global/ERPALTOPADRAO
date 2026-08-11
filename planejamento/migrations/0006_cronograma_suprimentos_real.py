from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("obras", "0001_initial"),
        ("planejamento", "0005_insumoplanejamento_suprimentoatividade"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportacaoCronogramaSuprimentos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("PROCESSANDO", "Processando"), ("CONCLUIDA", "Concluída"), ("FALHOU", "Falhou")], db_index=True, default="PROCESSANDO", max_length=20)),
                ("ativa", models.BooleanField(db_index=True, default=False)),
                ("nome_arquivo", models.CharField(blank=True, max_length=255)),
                ("arquivo_drive_id", models.CharField(blank=True, db_index=True, max_length=255)),
                ("mime_type", models.CharField(blank=True, max_length=255)),
                ("data_modificacao_drive", models.DateTimeField(blank=True, null=True)),
                ("hash_arquivo", models.CharField(blank=True, db_index=True, max_length=64)),
                ("tamanho_arquivo_bytes", models.BigIntegerField(default=0)),
                ("total_abas_arquivo", models.PositiveIntegerField(default=0)),
                ("abas_importadas", models.PositiveIntegerField(default=0)),
                ("abas_ignoradas", models.PositiveIntegerField(default=0)),
                ("total_itens_importados", models.PositiveIntegerField(default=0)),
                ("mensagem", models.TextField(blank=True)),
                ("erro_detalhado", models.TextField(blank=True)),
                ("iniciou_em", models.DateTimeField(blank=True, null=True)),
                ("finalizou_em", models.DateTimeField(blank=True, null=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("executado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="importacoes_cronograma_suprimentos", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Importação do cronograma de suprimentos",
                "verbose_name_plural": "Importações do cronograma de suprimentos",
                "ordering": ("-criado_em",),
            },
        ),
        migrations.CreateModel(
            name="CronogramaSuprimentosObra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_aba", models.CharField(db_index=True, max_length=255)),
                ("codigo_aba", models.CharField(db_index=True, max_length=30)),
                ("data_inicio_obra", models.DateField(blank=True, null=True)),
                ("quantidade_itens", models.PositiveIntegerField(default=0)),
                ("ordem_aba", models.PositiveIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("importacao", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="obras_importadas", to="planejamento.importacaocronogramasuprimentos")),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cronogramas_suprimentos_importados", to="obras.obra")),
            ],
            options={
                "verbose_name": "Cronograma de suprimentos da obra",
                "verbose_name_plural": "Cronogramas de suprimentos das obras",
                "ordering": ("ordem_aba", "nome_aba"),
            },
        ),
        migrations.CreateModel(
            name="ItemCronogramaSuprimento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("categoria", models.CharField(blank=True, db_index=True, max_length=120)),
                ("situacao", models.CharField(blank=True, db_index=True, max_length=120)),
                ("data_cotacao", models.DateField(blank=True, db_index=True, null=True)),
                ("duracao_cotacao", models.PositiveIntegerField(blank=True, null=True)),
                ("data_compatibilizacao", models.DateField(blank=True, null=True)),
                ("duracao_compatibilizacao", models.PositiveIntegerField(blank=True, null=True)),
                ("data_negociacao", models.DateField(blank=True, null=True)),
                ("duracao_negociacao", models.PositiveIntegerField(blank=True, null=True)),
                ("prazo_limite_contratacao", models.DateField(blank=True, db_index=True, null=True)),
                ("item", models.CharField(db_index=True, max_length=500)),
                ("local", models.CharField(blank=True, max_length=500)),
                ("contratada_responsavel", models.CharField(blank=True, max_length=255)),
                ("dias_apos_inicio", models.IntegerField(blank=True, null=True)),
                ("mes_referencia", models.CharField(blank=True, max_length=50)),
                ("linha_origem", models.PositiveIntegerField(default=0)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("cronograma_obra", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="planejamento.cronogramasuprimentosobra")),
            ],
            options={
                "verbose_name": "Item do cronograma de suprimentos",
                "verbose_name_plural": "Itens do cronograma de suprimentos",
                "ordering": ("cronograma_obra", "ordem", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="cronogramasuprimentosobra",
            constraint=models.UniqueConstraint(fields=("importacao", "obra"), name="plan_cs_imp_obra_unica"),
        ),
        migrations.AddConstraint(
            model_name="cronogramasuprimentosobra",
            constraint=models.UniqueConstraint(fields=("importacao", "nome_aba"), name="plan_cs_imp_aba_unica"),
        ),
        migrations.AddIndex(model_name="importacaocronogramasuprimentos", index=models.Index(fields=["ativa", "status"], name="plan_cs_imp_ativa_idx")),
        migrations.AddIndex(model_name="importacaocronogramasuprimentos", index=models.Index(fields=["hash_arquivo"], name="plan_cs_imp_hash_idx")),
        migrations.AddIndex(model_name="cronogramasuprimentosobra", index=models.Index(fields=["importacao", "obra"], name="plan_cs_imp_obra_idx")),
        migrations.AddIndex(model_name="cronogramasuprimentosobra", index=models.Index(fields=["codigo_aba"], name="plan_cs_codigo_aba_idx")),
        migrations.AddIndex(model_name="itemcronogramasuprimento", index=models.Index(fields=["cronograma_obra", "categoria"], name="plan_cs_item_cat_idx")),
        migrations.AddIndex(model_name="itemcronogramasuprimento", index=models.Index(fields=["cronograma_obra", "situacao"], name="plan_cs_item_sit_idx")),
        migrations.AddIndex(model_name="itemcronogramasuprimento", index=models.Index(fields=["cronograma_obra", "prazo_limite_contratacao"], name="plan_cs_item_prazo_idx")),
    ]
