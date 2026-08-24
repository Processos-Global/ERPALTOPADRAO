import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrar_permissoes_existentes(apps, schema_editor):
    PermissaoModulo = apps.get_model("usuarios", "PermissaoModulo")
    PermissaoCompras = apps.get_model("usuarios", "PermissaoCompras")

    configuracoes = {
        "LEITURA": {
            "visualizar": True,
        },
        "EDICAO": {
            "visualizar": True,
            "solicitar_compra": True,
            "executar_cotacao": True,
            "compatibilizar": True,
            "negociar": True,
            "gerenciar_pedidos": True,
            "receber_pedidos": True,
            "cancelar_pedidos": True,
        },
        "APROVACAO": {
            "visualizar": True,
            "solicitar_compra": True,
            "executar_cotacao": True,
            "compatibilizar": True,
            "negociar": True,
            "aprovar_compra": True,
            "gerenciar_pedidos": True,
            "receber_pedidos": True,
            "cancelar_pedidos": True,
        },
        "ADMINISTRADOR": {
            "visualizar": True,
            "solicitar_compra": True,
            "executar_cotacao": True,
            "compatibilizar": True,
            "negociar": True,
            "aprovar_compra": True,
            "gerenciar_pedidos": True,
            "receber_pedidos": True,
            "cancelar_pedidos": True,
            "administrar": True,
        },
    }

    permissoes_modulo = PermissaoModulo.objects.filter(modulo="COMPRAS")

    for permissao_modulo in permissoes_modulo.iterator():
        defaults = {
            "visualizar": False,
            "solicitar_compra": False,
            "executar_cotacao": False,
            "compatibilizar": False,
            "negociar": False,
            "aprovar_compra": False,
            "gerenciar_pedidos": False,
            "receber_pedidos": False,
            "cancelar_pedidos": False,
            "administrar": False,
            "ativo": permissao_modulo.ativo,
        }
        defaults.update(configuracoes.get(permissao_modulo.nivel, {}))

        PermissaoCompras.objects.update_or_create(
            usuario_id=permissao_modulo.usuario_id,
            defaults=defaults,
        )


def reverter_permissoes_migradas(apps, schema_editor):
    PermissaoCompras = apps.get_model("usuarios", "PermissaoCompras")
    PermissaoCompras.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PermissaoCompras",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("visualizar", models.BooleanField(default=True, verbose_name="Visualizar Compras")),
                ("solicitar_compra", models.BooleanField(default=False, verbose_name="Solicitar compra")),
                ("executar_cotacao", models.BooleanField(default=False, verbose_name="Executar cotação")),
                ("compatibilizar", models.BooleanField(default=False, verbose_name="Compatibilizar tecnicamente")),
                ("negociar", models.BooleanField(default=False, verbose_name="Negociar")),
                ("aprovar_compra", models.BooleanField(default=False, verbose_name="Aprovar compra")),
                ("gerenciar_pedidos", models.BooleanField(default=False, verbose_name="Gerenciar pedidos")),
                ("receber_pedidos", models.BooleanField(default=False, verbose_name="Registrar recebimentos")),
                ("cancelar_pedidos", models.BooleanField(default=False, verbose_name="Cancelar pedidos")),
                ("administrar", models.BooleanField(default=False, verbose_name="Administrar Compras")),
                ("ativo", models.BooleanField(default=True, verbose_name="Permissões de Compras ativas")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="Atualizado em")),
                (
                    "usuario",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permissao_compras_erp",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuário",
                    ),
                ),
            ],
            options={
                "verbose_name": "Permissão de Compras",
                "verbose_name_plural": "Permissões de Compras",
                "ordering": ["usuario__username"],
            },
        ),
        migrations.RunPython(
            migrar_permissoes_existentes,
            reverter_permissoes_migradas,
        ),
    ]
