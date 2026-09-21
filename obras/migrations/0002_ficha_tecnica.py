from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0004_ficha_tecnica_base"),
        ("obras", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FichaTecnicaObra",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("RASCUNHO", "Rascunho"), ("EM_PREENCHIMENTO", "Em preenchimento"), ("CONCLUIDA", "Concluída")], db_index=True, default="RASCUNHO", max_length=20)),
                ("versao", models.PositiveIntegerField(default=1)),
                ("observacoes", models.TextField(blank=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("criado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fichas_tecnicas_criadas", to=settings.AUTH_USER_MODEL)),
                ("obra", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="ficha_tecnica", to="obras.obra")),
            ],
            options={"ordering": ("obra__nome",)},
        ),
        migrations.CreateModel(
            name="PavimentoFichaTecnica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome", models.CharField(max_length=120)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("ativo", models.BooleanField(default=True)),
                ("ficha", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pavimentos", to="obras.fichatecnicaobra")),
                ("tipo_pavimento", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="pavimentos_obras", to="cadastros.tipopavimento")),
            ],
            options={"ordering": ("ordem", "id")},
        ),
        migrations.CreateModel(
            name="AmbienteFichaTecnica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identificacao", models.CharField(max_length=160)),
                ("area_m2", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("ativo", models.BooleanField(default=True)),
                ("caracteristica", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ambientes_fichas_tecnicas", to="cadastros.caracteristicaambiente")),
                ("pavimento", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ambientes", to="obras.pavimentofichatecnica")),
                ("tipo_ambiente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ambientes_fichas_tecnicas", to="cadastros.tipoambiente")),
            ],
            options={"ordering": ("pavimento__ordem", "ordem", "identificacao")},
        ),
        migrations.CreateModel(
            name="CategoriaFichaTecnica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao", models.TextField(blank=True)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("ambiente", models.ForeignKey(blank=True, help_text="Vazio quando a categoria é aplicada à obra inteira.", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="categorias_gf", to="obras.ambientefichatecnica")),
                ("categoria", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="aplicacoes_ficha_tecnica", to="cadastros.categoriagrandefornecedor")),
                ("ficha", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="categorias_aplicadas", to="obras.fichatecnicaobra")),
            ],
            options={"ordering": ("categoria__ordem", "categoria__nome", "id")},
        ),
        migrations.CreateModel(
            name="ItemFichaTecnica",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("descricao_item", models.CharField(blank=True, help_text="Usado quando a categoria possui preenchimento descritivo ou não tem tipo pré-cadastrado.", max_length=180)),
                ("quantidade", models.DecimalField(decimal_places=2, default=Decimal("1.00"), max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("especificacao", models.TextField(blank=True)),
                ("observacao", models.TextField(blank=True)),
                ("ordem", models.PositiveIntegerField(default=0)),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("aplicacao_categoria", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="itens", to="obras.categoriafichatecnica")),
                ("opcao_especificacao", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="itens_fichas_tecnicas", to="cadastros.opcaoespecificacaograndefornecedor")),
                ("tipo_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="itens_fichas_tecnicas", to="cadastros.tipoitemgrandefornecedor")),
                ("unidade", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="itens_fichas_tecnicas", to="cadastros.unidademedida")),
            ],
            options={"ordering": ("aplicacao_categoria_id", "ordem", "id")},
        ),
        migrations.AddConstraint(
            model_name="pavimentofichatecnica",
            constraint=models.UniqueConstraint(fields=("ficha", "nome"), name="obras_ficha_pav_nome_uniq"),
        ),
        migrations.AddConstraint(
            model_name="ambientefichatecnica",
            constraint=models.UniqueConstraint(fields=("pavimento", "identificacao"), name="obras_ficha_amb_pav_ident_uniq"),
        ),
        migrations.AddConstraint(
            model_name="categoriafichatecnica",
            constraint=models.UniqueConstraint(fields=("ficha", "categoria", "ambiente"), name="obras_ficha_cat_amb_uniq"),
        ),
    ]
