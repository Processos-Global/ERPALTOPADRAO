from django.db import migrations


def limpar_colunas_legadas(apps, schema_editor):
    """
    Alinha fisicamente usuarios_permissaofinanceiro ao model atual.

    Algumas instalações antigas do ERP podem conservar colunas de versões
    anteriores (ex.: lancar). Como essas colunas podem ser NOT NULL e não
    possuir DEFAULT, elas impedem o get_or_create() do model atual.

    A migration remove apenas colunas extras desta tabela. Campos que ainda
    pertencem ao model atual são preservados.
    """
    PermissaoFinanceiro = apps.get_model("usuarios", "PermissaoFinanceiro")
    connection = schema_editor.connection
    tabela = PermissaoFinanceiro._meta.db_table

    if tabela not in set(connection.introspection.table_names()):
        return

    colunas_model = {
        field.column
        for field in PermissaoFinanceiro._meta.local_fields
    }

    with connection.cursor() as cursor:
        colunas_banco = {
            coluna.name
            for coluna in connection.introspection.get_table_description(cursor, tabela)
        }

    extras = sorted(colunas_banco - colunas_model)

    # Segurança: nunca remover identificadores estruturais, mesmo que haja
    # alguma divergência inesperada na introspecção.
    protegidas = {"id", "usuario_id"}
    extras = [nome for nome in extras if nome not in protegidas]

    quote = schema_editor.quote_name
    for nome in extras:
        schema_editor.execute(
            f"ALTER TABLE {quote(tabela)} DROP COLUMN {quote(nome)}"
        )


def noop(apps, schema_editor):
    # Não recriamos colunas legadas ao reverter esta migration.
    pass


class Migration(migrations.Migration):
    # ALTER TABLE no MySQL deve ocorrer fora de uma migration atômica.
    atomic = False

    dependencies = [
        ("usuarios", "0007_reparar_schema_permissaofinanceiro"),
    ]

    operations = [
        migrations.RunPython(limpar_colunas_legadas, noop),
    ]
