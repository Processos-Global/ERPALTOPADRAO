from django.db import migrations


def reparar_schema_permissaofinanceiro(apps, schema_editor):
    PermissaoFinanceiro = apps.get_model("usuarios", "PermissaoFinanceiro")

    connection = schema_editor.connection
    table_name = PermissaoFinanceiro._meta.db_table

    with connection.cursor() as cursor:
        existentes = {
            coluna.name
            for coluna in connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }

    campos_ignorados = {
        "id",
        "usuario",
    }

    for field in PermissaoFinanceiro._meta.local_fields:
        if field.name in campos_ignorados:
            continue

        coluna = field.column

        if coluna in existentes:
            continue

        schema_editor.add_field(
            PermissaoFinanceiro,
            field,
        )

        existentes.add(coluna)


class Migration(migrations.Migration):

    # MySQL não suporta rollback de alterações de schema/DDL.
    # Como esta migration usa ALTER TABLE dinamicamente,
    # ela precisa executar fora de uma transação global.
    atomic = False

    dependencies = [
        ("usuarios", "0006_reparar_permissoes_financeiro"),
    ]

    operations = [
        migrations.RunPython(
            reparar_schema_permissaofinanceiro,
            migrations.RunPython.noop,
        ),
    ]