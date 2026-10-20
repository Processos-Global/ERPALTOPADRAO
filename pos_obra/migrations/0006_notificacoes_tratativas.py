from django.conf import settings
from django.db import migrations,models
import django.db.models.deletion
class Migration(migrations.Migration):
    dependencies=[('pos_obra','0005_fluxo_campo_documentos'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations=[
        migrations.CreateModel(name='NotificacaoOS',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),
            ('evento',models.CharField(max_length=48)),('destinatario',models.EmailField(max_length=254)),
            ('assunto',models.CharField(max_length=250)),('mensagem',models.TextField()),
            ('chave',models.CharField(max_length=160,unique=True)),
            ('situacao',models.CharField(max_length=16,default='PENDENTE',choices=[('PENDENTE','Pendente'),('ENVIADO','Enviado'),('ERRO','Erro')])),
            ('tentativas',models.PositiveIntegerField(default=0)),('ultimo_erro',models.TextField(blank=True)),
            ('criado_em',models.DateTimeField(auto_now_add=True)),('enviado_em',models.DateTimeField(null=True,blank=True)),
            ('chamado',models.ForeignKey(to='pos_obra.chamado',related_name='notificacoes',on_delete=django.db.models.deletion.CASCADE)),
        ],options={'ordering':['-criado_em']}),
        migrations.CreateModel(name='TratativaSatisfacao',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),('observacao',models.TextField()),('criado_em',models.DateTimeField(auto_now_add=True)),
            ('chamado',models.ForeignKey(to='pos_obra.chamado',related_name='tratativas_satisfacao',on_delete=django.db.models.deletion.PROTECT)),
            ('responsavel',models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,on_delete=django.db.models.deletion.SET_NULL)),
        ])
    ]
