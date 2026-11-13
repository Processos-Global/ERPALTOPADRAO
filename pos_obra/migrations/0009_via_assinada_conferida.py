from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies=[('pos_obra','0008_rascunhos_etapas')]
    operations=[migrations.AddField(model_name='anexochamado',name='via_assinada_conferida',field=models.BooleanField(default=False,help_text='Via assinada identificada e conferida por responsável interno.'))]
