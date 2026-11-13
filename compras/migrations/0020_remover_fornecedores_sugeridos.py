from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("compras", "0019_suprimentoreferencia_multivinculo")]

    operations = [
        migrations.RemoveField(
            model_name="processocompra",
            name="fornecedores_sugeridos",
        ),
    ]
