from django.db import migrations, models

from ._documentos_fornecedor import impedir_duplicados


def diagnosticar_chaves(apps, schema_editor):
    fornecedor = apps.get_model("cadastros", "Fornecedor")
    impedir_duplicados(fornecedor, schema_editor.connection.alias, campo="documento_chave")


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0017_fornecedor_documento_chave")]

    operations = [
        migrations.RunPython(diagnosticar_chaves, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="fornecedor",
            constraint=models.UniqueConstraint(
                fields=("documento_chave",),
                name="cad_for_doc_unico_uniq",
                violation_error_message="Já existe um fornecedor com este CPF/CNPJ.",
            ),
        ),
        migrations.RemoveConstraint(model_name="fornecedor", name="cad_for_doc_uniq"),
    ]
