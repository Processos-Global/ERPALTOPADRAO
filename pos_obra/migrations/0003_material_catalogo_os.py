from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('pos_obra', '0002_private_anexos'), ('cadastros', '0012_pos_obra_cadastros')]
    operations = [migrations.AddField(model_name='materialos', name='material', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='materiais_pos_obra', to='cadastros.material'))]
