from django.db import migrations, models
from django.db.models.functions import NullIf

from ._documentos_fornecedor import impedir_duplicados, verificar_collation


def diagnosticar_documentos(apps, schema_editor):
    fornecedor = apps.get_model("cadastros", "Fornecedor")
    verificar_collation(fornecedor, schema_editor.connection)
    impedir_duplicados(fornecedor, schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("cadastros", "0016_tipo_item_gf_ambientes_sugeridos")]

    operations = [
        migrations.RunPython(diagnosticar_documentos, migrations.RunPython.noop),
        migrations.AddField(
            model_name="fornecedor",
            name="documento_chave",
            field=models.GeneratedField(
                expression=NullIf("documento", models.Value("")),
                output_field=models.CharField(max_length=30),
                db_persist=False,
                null=True,
            ),
        ),
    ]
