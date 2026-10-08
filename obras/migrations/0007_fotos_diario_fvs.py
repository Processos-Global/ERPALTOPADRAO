from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("obras", "0006_fvs_ambientes_ficha")]
    operations = [
        migrations.CreateModel(name="FotoDiarioObra", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)), ("arquivo", models.ImageField(upload_to="obras/diarios/%Y/%m/")), ("enviado_em", models.DateTimeField(auto_now_add=True)), ("diario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fotos", to="obras.diarioobra"))], options={"ordering": ["id"]}),
        migrations.CreateModel(name="FotoFVSItem", fields=[("id", models.BigAutoField(primary_key=True, serialize=False)), ("arquivo", models.ImageField(upload_to="obras/fvs/%Y/%m/")), ("enviado_em", models.DateTimeField(auto_now_add=True)), ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fotos", to="obras.fvsitem"))], options={"ordering": ["id"]}),
    ]
