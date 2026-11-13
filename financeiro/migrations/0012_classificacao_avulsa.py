from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('financeiro', '0011_anexotitulopagar')]
    operations = [migrations.AddField(model_name='titulopagar', name='classificacao', field=models.CharField(choices=[('OUTRO','Outro pagamento'),('MATERIAL','Materiais'),('SERVICO','Serviços'),('REEMBOLSO','Reembolso')], db_index=True, default='OUTRO', max_length=16))]
