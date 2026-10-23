from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('obras','0011_alter_fotodiarioobra_id_alter_fotofvsitem_id_and_more'), ('cadastros','0015_modelo_vistoria'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='VistoriaCautelar', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('codigo', models.CharField(max_length=25)),
            ('endereco', models.CharField(max_length=255, blank=True)),
            ('posicao', models.CharField(max_length=80, blank=True)),
            ('respostas', models.JSONField(default=dict, blank=True)),
            ('esquema', models.JSONField(default=list, blank=True)),
            ('situacao', models.CharField(max_length=12, default='RASCUNHO', choices=[('RASCUNHO','Em preenchimento'),('FINALIZADA','Finalizada')])),
            ('criado_em', models.DateTimeField(auto_now_add=True)),
            ('atualizado_em', models.DateTimeField(auto_now=True)),
            ('finalizado_em', models.DateTimeField(null=True, blank=True)),
            ('obra', models.ForeignKey(to='obras.obra', on_delete=django.db.models.deletion.PROTECT, related_name='vistorias_cautelares')),
            ('modelo', models.ForeignKey(to='cadastros.modelovistoria', on_delete=django.db.models.deletion.PROTECT)),
            ('criado_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, related_name='+')),
        ], options={'ordering': ('-criado_em','-pk')}),
        migrations.AddConstraint(model_name='vistoriacautelar', constraint=models.UniqueConstraint(fields=('obra','codigo'), name='unq_codigo_cautelar_obra')),
        migrations.CreateModel(name='OcorrenciaCautelar', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('ambiente', models.CharField(max_length=120)),
            ('elemento', models.CharField(max_length=120, blank=True)),
            ('manifestacao', models.CharField(max_length=120)),
            ('localizacao', models.CharField(max_length=200, blank=True)),
            ('descricao', models.TextField(blank=True)),
            ('criado_em', models.DateTimeField(auto_now_add=True)),
            ('vistoria', models.ForeignKey(to='obras.vistoriacautelar', on_delete=django.db.models.deletion.CASCADE, related_name='ocorrencias')),
        ], options={'ordering': ('pk',)}),
        migrations.CreateModel(name='FotoCautelar', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('imagem', models.ImageField(upload_to='vistorias/cautelares/%Y/%m/')),
            ('legenda', models.CharField(max_length=255, blank=True)),
            ('criada_em', models.DateTimeField(auto_now_add=True)),
            ('ocorrencia', models.ForeignKey(to='obras.ocorrenciacautelar', on_delete=django.db.models.deletion.CASCADE, related_name='fotos', null=True, blank=True)),
            ('vistoria', models.ForeignKey(to='obras.vistoriacautelar', on_delete=django.db.models.deletion.CASCADE, related_name='fotos')),
        ]),
    ]
