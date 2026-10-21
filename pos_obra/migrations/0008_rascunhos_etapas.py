from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('pos_obra', '0007_normalizar_estado_ids'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='RascunhoEtapaOS', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('etapa', models.CharField(max_length=20)),
        ('dados', models.JSONField(default=dict)),
        ('atualizado_em', models.DateTimeField(auto_now=True)),
        ('chamado', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rascunhos_etapas', to='pos_obra.chamado')),
        ('atualizado_por', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
    ]), migrations.AddConstraint(model_name='rascunhoetapaos', constraint=models.UniqueConstraint(fields=('chamado','etapa'), name='po_rascunho_os_etapa_unico'))]
