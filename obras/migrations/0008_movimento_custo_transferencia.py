from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("obras", "0007_fotos_diario_fvs")]
    operations = [migrations.AddField(model_name="movimentoestoque", name="custo_unitario_transferencia", field=models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, help_text="Custo médio de compra no momento da transferência"))]
