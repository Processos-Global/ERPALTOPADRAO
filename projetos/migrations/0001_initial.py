from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cadastros", "0009_seed_checklist_compatibilizacao"),
        ("obras", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="AlteracaoProjeto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao", models.TextField()),
                ("arquivo", models.FileField(upload_to="projetos/alteracoes/%Y/%m/")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="alteracoes_projeto_criadas", to=settings.AUTH_USER_MODEL)),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alteracoes_projeto", to="obras.obra")),
            ],
            options={"ordering": ["-criado_em", "-id"]},
        ),
        migrations.CreateModel(
            name="ChecklistProjetoResposta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("NAO_RECEBIDO", "Não Recebido"), ("PARCIALMENTE", "Parcialmente"), ("RECEBIDO", "Recebido"), ("NAO_SE_APLICA", "Não se aplica")], default="NAO_RECEBIDO", max_length=20)),
                ("observacao", models.TextField(blank=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="checklists_projetos_atualizados", to=settings.AUTH_USER_MODEL)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="respostas_obras", to="cadastros.checklistprojetoitem")),
                ("obra", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="respostas_checklist_projetos", to="obras.obra")),
            ],
            options={"ordering": ["item__grupo__ordem", "item__ordem", "item__id"]},
        ),
        migrations.CreateModel(
            name="ChecklistProjetoHistorico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("campo", models.CharField(choices=[("STATUS", "Status"), ("OBSERVACAO", "Observação")], max_length=20)),
                ("valor_anterior", models.TextField(blank=True)),
                ("valor_novo", models.TextField(blank=True)),
                ("alterado_em", models.DateTimeField(auto_now_add=True)),
                ("alterado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="historicos_checklist_projetos", to=settings.AUTH_USER_MODEL)),
                ("resposta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="historico", to="projetos.checklistprojetoresposta")),
            ],
            options={"ordering": ["-alterado_em", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="checklistprojetoresposta",
            constraint=models.UniqueConstraint(fields=("obra", "item"), name="projetos_checklist_resposta_obra_item_uniq"),
        ),
        migrations.AddIndex(
            model_name="checklistprojetoresposta",
            index=models.Index(fields=["obra", "status"], name="proj_chk_obra_status_idx"),
        ),
        migrations.AddIndex(
            model_name="checklistprojetoresposta",
            index=models.Index(fields=["item", "status"], name="proj_chk_item_status_idx"),
        ),
        migrations.AddIndex(
            model_name="checklistprojetohistorico",
            index=models.Index(fields=["resposta", "campo", "-alterado_em"], name="proj_chk_hist_idx"),
        ),
        migrations.AddIndex(
            model_name="alteracaoprojeto",
            index=models.Index(fields=["obra", "-criado_em"], name="proj_alt_obra_data_idx"),
        ),
    ]
