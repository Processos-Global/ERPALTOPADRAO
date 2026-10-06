from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0007_dados_bancarios_fornecedor"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChecklistProjetoGrupo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("COMPATIBILIZACAO", "Checklist de verificação de compatibilização")], max_length=30)),
                ("nome", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=140)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("ativo", models.BooleanField(default=True)),
            ],
            options={"ordering": ["tipo", "ordem", "nome", "id"]},
        ),
        migrations.CreateModel(
            name="ChecklistProjetoItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("etapa", models.CharField(blank=True, max_length=40)),
                ("codigo", models.CharField(blank=True, max_length=40)),
                ("entrega_atividade", models.CharField(max_length=500)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("ativo", models.BooleanField(default=True)),
                ("grupo", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="cadastros.checklistprojetogrupo")),
            ],
            options={"ordering": ["grupo__ordem", "ordem", "id"]},
        ),
        migrations.AddConstraint(
            model_name="checklistprojetogrupo",
            constraint=models.UniqueConstraint(fields=("tipo", "slug"), name="cad_chk_grupo_tipo_slug_uniq"),
        ),
        migrations.AddIndex(
            model_name="checklistprojetoitem",
            index=models.Index(fields=["grupo", "ativo", "ordem"], name="cad_chk_item_ordem_idx"),
        ),
    ]
