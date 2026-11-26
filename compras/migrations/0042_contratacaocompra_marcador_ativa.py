from django.db import migrations, models


def verificar_contratacoes_ativas(apps, schema_editor):
    ContratacaoCompra = apps.get_model("compras", "ContratacaoCompra")
    alias = schema_editor.connection.alias
    duplicadas = (
        ContratacaoCompra.objects.using(alias)
        .filter(cancelada=False)
        .values("processo_id", "fornecedor_id")
        .annotate(total=models.Count("pk"))
        .filter(total__gt=1)
    )
    if duplicadas.exists():
        raise RuntimeError(
            "Há pares processo/fornecedor com mais de uma contratação ativa. "
            f"Execute diagnosticar_contratacoes_duplicadas --database {alias} "
            "para identificar os registros que precisam de revisão."
        )


class Migration(migrations.Migration):
    dependencies = [("compras", "0041_recebimentopedido_valor_frete_nota")]

    operations = [
        migrations.RunPython(verificar_contratacoes_ativas, migrations.RunPython.noop),
        migrations.AddField(
            model_name="contratacaocompra",
            name="marcador_ativa",
            field=models.GeneratedField(
                expression=models.Case(models.When(cancelada=False, then=models.Value(1))),
                output_field=models.SmallIntegerField(),
                db_persist=False,
                null=True,
            ),
        ),
    ]
