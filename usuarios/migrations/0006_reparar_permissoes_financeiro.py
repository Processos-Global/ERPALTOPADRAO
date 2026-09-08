from django.db import migrations


CAMPOS_OBRIGATORIOS = {
    "visualizar": "TINYINT(1) NOT NULL DEFAULT 1",
    "lancar_titulos": "TINYINT(1) NOT NULL DEFAULT 0",
    "editar_titulos": "TINYINT(1) NOT NULL DEFAULT 0",
    "aprovar_pagamentos": "TINYINT(1) NOT NULL DEFAULT 0",
    "registrar_pagamentos": "TINYINT(1) NOT NULL DEFAULT 0",
    "administrar": "TINYINT(1) NOT NULL DEFAULT 0",
    "ativo": "TINYINT(1) NOT NULL DEFAULT 1",
}

CAMPOS_OBSOLETOS = (
    "programar_pagamentos",
    "gerenciar_bancos",
    "conciliar",
)


def reparar_tabela(apps, schema_editor):
    connection = schema_editor.connection
    tabela = "usuarios_permissaofinanceiro"
    tabelas = set(connection.introspection.table_names())
    if tabela not in tabelas:
        return

    with connection.cursor() as cursor:
        colunas = {
            item.name
            for item in connection.introspection.get_table_description(cursor, tabela)
        }

    quote = schema_editor.quote_name
    for nome, definicao in CAMPOS_OBRIGATORIOS.items():
        if nome not in colunas:
            schema_editor.execute(
                f"ALTER TABLE {quote(tabela)} ADD COLUMN {quote(nome)} {definicao}"
            )

    # Campos removidos do novo fluxo. A exclusão é tolerante porque a tabela
    # pode vir de versões anteriores diferentes do Financeiro.
    with connection.cursor() as cursor:
        colunas = {
            item.name
            for item in connection.introspection.get_table_description(cursor, tabela)
        }
    for nome in CAMPOS_OBSOLETOS:
        if nome in colunas:
            schema_editor.execute(
                f"ALTER TABLE {quote(tabela)} DROP COLUMN {quote(nome)}"
            )


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0005_permissoes_financeiro"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(reparar_tabela, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.RemoveField(model_name="permissaofinanceiro", name="programar_pagamentos"),
                migrations.RemoveField(model_name="permissaofinanceiro", name="gerenciar_bancos"),
                migrations.RemoveField(model_name="permissaofinanceiro", name="conciliar"),
            ],
        ),
    ]
