from django.db.models import Count, Sum


def verificar_collation(fornecedor, connection):
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT col.COLLATION_NAME, tab.TABLE_COLLATION
            FROM information_schema.COLUMNS col
            JOIN information_schema.TABLES tab USING (TABLE_SCHEMA, TABLE_NAME)
            WHERE col.TABLE_SCHEMA = DATABASE()
              AND col.TABLE_NAME = %s AND col.COLUMN_NAME = %s
            """,
            [fornecedor._meta.db_table, fornecedor._meta.get_field("documento").column],
        )
        collations = cursor.fetchone()
    if collations is None or collations[0] != collations[1]:
        raise RuntimeError(
            "Não foi possível confirmar que documento e a tabela de fornecedores "
            "usam a mesma collation. A chave gerada herdaria a collation da tabela."
        )


def contar_duplicados(fornecedor, using, *, campo="documento"):
    documentos = fornecedor.objects.using(using).order_by().filter(**{f"{campo}__isnull": False})
    if campo == "documento":
        documentos = documentos.exclude(documento="")
    grupos = (
        documentos.values(campo).annotate(total=Count("pk")).filter(total__gt=1)
    )
    contagem = grupos.aggregate(grupos=Count("*"), fornecedores=Sum("total", default=0))
    return contagem["grupos"], contagem["fornecedores"]


def resumo_duplicados(grupos, fornecedores):
    return f"{grupos} grupos de documentos duplicados em {fornecedores} fornecedores."


def impedir_duplicados(fornecedor, using, *, campo="documento"):
    grupos, fornecedores = contar_duplicados(fornecedor, using, campo=campo)
    if grupos:
        raise RuntimeError(
            f"{resumo_duplicados(grupos, fornecedores)} "
            "Revise a duplicidade de CPF/CNPJ antes de prosseguir com a migração."
        )
