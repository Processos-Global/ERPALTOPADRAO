from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0003_notificacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="permissaomodulo",
            name="modulo",
            field=models.CharField(
                choices=[
                    ("OBRAS", "Obras"),
                    ("PLANEJAMENTO", "Planejamento"),
                    ("SUPRIMENTOS", "Suprimentos"),
                    ("COMPRAS", "Compras"),
                    ("CONTRATOS", "Contratos"),
                    ("FINANCEIRO", "Financeiro"),
                    ("ALMOXARIFADO", "Almoxarifado"),
                    ("PROJETOS", "Projetos"),
                    ("VISTORIAS", "Vistorias"),
                    ("DIARIO_OBRA", "Diário de obra"),
                    ("POS_OBRA", "Pós-obra"),
                    ("RELATORIOS", "Relatórios"),
                    ("INTEGRACOES", "Integrações"),
                    ("CADASTROS", "Cadastros"),
                    ("USUARIOS", "Usuários e permissões"),
                ],
                max_length=30,
                verbose_name="Módulo",
            ),
        ),
        migrations.CreateModel(
            name="PermissaoCadastros",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visualizar", models.BooleanField(default=True, verbose_name="Visualizar Cadastros")),
                ("criar", models.BooleanField(default=False, verbose_name="Criar cadastros")),
                ("editar", models.BooleanField(default=False, verbose_name="Editar cadastros")),
                ("excluir", models.BooleanField(default=False, verbose_name="Excluir cadastros")),
                ("administrar", models.BooleanField(default=False, verbose_name="Administrar Cadastros")),
                ("ativo", models.BooleanField(default=True, verbose_name="Permissões de Cadastros ativas")),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="permissao_cadastros_erp", to=settings.AUTH_USER_MODEL, verbose_name="Usuário")),
            ],
            options={"verbose_name": "Permissão de Cadastros", "verbose_name_plural": "Permissões de Cadastros"},
        ),
    ]
