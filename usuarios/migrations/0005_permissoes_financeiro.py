from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0004_permissoes_cadastros"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PermissaoFinanceiro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visualizar", models.BooleanField(default=True, verbose_name="Visualizar Financeiro")),
                ("lancar_titulos", models.BooleanField(default=False, verbose_name="Lançar títulos")),
                ("editar_titulos", models.BooleanField(default=False, verbose_name="Editar títulos")),
                ("aprovar_pagamentos", models.BooleanField(default=False, verbose_name="Aprovar pagamentos")),
                ("programar_pagamentos", models.BooleanField(default=False, verbose_name="Programar pagamentos")),
                ("registrar_pagamentos", models.BooleanField(default=False, verbose_name="Registrar pagamentos")),
                ("gerenciar_bancos", models.BooleanField(default=False, verbose_name="Gerenciar bancos")),
                ("conciliar", models.BooleanField(default=False, verbose_name="Conciliar movimentações")),
                ("administrar", models.BooleanField(default=False, verbose_name="Administrar Financeiro")),
                ("ativo", models.BooleanField(default=True, verbose_name="Permissões do Financeiro ativas")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="permissao_financeiro_erp", to=settings.AUTH_USER_MODEL, verbose_name="Usuário")),
            ],
            options={"verbose_name": "Permissão do Financeiro", "verbose_name_plural": "Permissões do Financeiro", "ordering": ["usuario__username"]},
        ),
        migrations.AlterField(
            model_name="notificacao",
            name="modulo",
            field=models.CharField(
                choices=[
                    ("SISTEMA", "Sistema"),
                    ("COMPRAS", "Compras"),
                    ("PLANEJAMENTO", "Planejamento"),
                    ("FINANCEIRO", "Financeiro"),
                ],
                db_index=True,
                default="SISTEMA",
                max_length=30,
                verbose_name="Módulo",
            ),
        ),
    ]
