# Generated for the ERP Alto Padrão central de cadastros.
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions.text


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AtividadeMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(db_index=True, max_length=150)),
            ],
            options={"verbose_name": "Atividade de material", "verbose_name_plural": "Atividades de materiais", "ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="Fornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("codigo", models.CharField(blank=True, db_index=True, editable=False, max_length=20, null=True, unique=True)),
                ("nome", models.CharField(db_index=True, max_length=255, verbose_name="Razão social / nome")),
                ("nome_fantasia", models.CharField(blank=True, db_index=True, max_length=255)),
                ("documento", models.CharField(blank=True, db_index=True, max_length=30, verbose_name="CPF / CNPJ")),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("telefone", models.CharField(blank=True, max_length=40)),
                ("contato", models.CharField(blank=True, max_length=150, verbose_name="Pessoa de contato")),
                ("cidade", models.CharField(blank=True, max_length=120)),
                ("estado", models.CharField(blank=True, max_length=2)),
                ("avaliacao", models.DecimalField(blank=True, decimal_places=2, help_text="Avaliação comercial de 0 a 5.", max_digits=3, null=True)),
                ("observacao", models.TextField(blank=True)),
            ],
            options={"verbose_name": "Fornecedor", "verbose_name_plural": "Fornecedores", "ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="UnidadeMedida",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("sigla", models.CharField(db_index=True, max_length=20, unique=True)),
                ("descricao", models.CharField(max_length=100)),
            ],
            options={"verbose_name": "Unidade de medida", "verbose_name_plural": "Unidades de medida", "ordering": ("sigla",)},
        ),
        migrations.CreateModel(
            name="SubatividadeMaterial",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("nome", models.CharField(db_index=True, max_length=150)),
                ("atividade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subatividades", to="cadastros.atividadematerial")),
            ],
            options={"verbose_name": "Subatividade de material", "verbose_name_plural": "Subatividades de materiais", "ordering": ("atividade__nome", "nome")},
        ),
        migrations.CreateModel(
            name="MaoObra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("codigo", models.CharField(blank=True, db_index=True, editable=False, max_length=20, null=True, unique=True)),
                ("descricao", models.CharField(db_index=True, max_length=255)),
                ("categoria", models.CharField(blank=True, db_index=True, max_length=150)),
                ("observacao", models.TextField(blank=True)),
                ("unidade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="itens_mao_obra", to="cadastros.unidademedida")),
            ],
            options={"verbose_name": "Mão de obra", "verbose_name_plural": "Mão de obra", "ordering": ("categoria", "descricao")},
        ),
        migrations.CreateModel(
            name="Material",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ativo", models.BooleanField(db_index=True, default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("codigo", models.CharField(blank=True, db_index=True, editable=False, max_length=20, null=True, unique=True)),
                ("nome", models.CharField(db_index=True, max_length=255)),
                ("especificacao", models.CharField(blank=True, db_index=True, max_length=255)),
                ("observacao", models.TextField(blank=True)),
                ("atividade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="materiais", to="cadastros.atividadematerial")),
                ("subatividade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="materiais", to="cadastros.subatividadematerial")),
                ("unidade", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="materiais", to="cadastros.unidademedida")),
            ],
            options={"verbose_name": "Material", "verbose_name_plural": "Materiais", "ordering": ("atividade__nome", "subatividade__nome", "nome", "especificacao")},
        ),
        migrations.AddConstraint(model_name="atividadematerial", constraint=models.UniqueConstraint(django.db.models.functions.text.Lower("nome"), name="cad_ativmat_nome_ci_uniq")),
        migrations.AddConstraint(model_name="subatividadematerial", constraint=models.UniqueConstraint("atividade", django.db.models.functions.text.Lower("nome"), name="cad_subativ_ativ_nome_ci_uniq")),
        migrations.AddConstraint(model_name="material", constraint=models.UniqueConstraint(fields=("atividade", "subatividade", "nome", "especificacao", "unidade"), name="cad_material_catalogo_uniq")),
        migrations.AddConstraint(model_name="fornecedor", constraint=models.UniqueConstraint(condition=models.Q(("documento", ""), _negated=True), fields=("documento",), name="cad_for_doc_uniq")),
        migrations.AddConstraint(model_name="maoobra", constraint=models.UniqueConstraint(fields=("descricao", "categoria", "unidade"), name="cad_maoobra_catalogo_uniq")),
        migrations.AddIndex(model_name="material", index=models.Index(fields=["ativo", "nome"], name="cad_mat_ativo_nome_idx")),
        migrations.AddIndex(model_name="material", index=models.Index(fields=["atividade", "subatividade"], name="cad_mat_ativ_sub_idx")),
        migrations.AddIndex(model_name="fornecedor", index=models.Index(fields=["ativo", "nome"], name="cad_for_ativo_nome_idx")),
    ]
