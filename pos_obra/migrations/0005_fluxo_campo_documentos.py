from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import core.storage

class Migration(migrations.Migration):
    dependencies = [('pos_obra','0004_alter_registrochamado_options'),migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='chamado', name='preferencia_data', field=models.DateField(blank=True, null=True, verbose_name='Data preferencial')),
        migrations.AddField(model_name='chamado', name='preferencia_periodo', field=models.CharField(blank=True, choices=[('MANHA','Manhã'),('TARDE','Tarde'),('HORARIO','Horário específico')], max_length=12, verbose_name='Período preferencial')),
        migrations.AddField(model_name='chamado', name='preferencia_inicio', field=models.TimeField(blank=True, null=True, verbose_name='Disponível a partir de')),
        migrations.AddField(model_name='chamado', name='preferencia_fim', field=models.TimeField(blank=True, null=True, verbose_name='Disponível até')),
        migrations.AddField(model_name='chamado', name='preferencia_alternativa', field=models.DateField(blank=True, null=True, verbose_name='Segunda opção de data')),
        migrations.AddField(model_name='chamado', name='horario_flexivel', field=models.BooleanField(default=False, verbose_name='Tenho flexibilidade de horário')),
        migrations.AddField(model_name='chamado', name='orientacoes_acesso', field=models.TextField(blank=True, verbose_name='Orientações de acesso ao imóvel')),

        migrations.CreateModel(name='AgendamentoOS',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),
            ('tipo',models.CharField(max_length=20,choices=[('VISTORIA','Vistoria'),('EXECUCAO','Execução'),('RETORNO','Retorno técnico'),('COMPLEMENTO','Complementação')])),
            ('inicio',models.DateTimeField()),('fim',models.DateTimeField()),
            ('situacao',models.CharField(max_length=20,default='PROPOSTO',choices=[('PROPOSTO','Aguardando confirmação'),('CONFIRMADO','Confirmado'),('REAGENDAMENTO','Reagendamento solicitado'),('SUBSTITUIDO','Reagendado'),('CANCELADO','Cancelado'),('REALIZADO','Realizado'),('NAO_REALIZADO','Não realizado')])),
            ('observacoes',models.TextField(blank=True)),('criado_em',models.DateTimeField(auto_now_add=True)),
            ('confirmado_em',models.DateTimeField(null=True,blank=True)),
            ('chamado',models.ForeignKey(to='pos_obra.chamado',related_name='agendamentos',on_delete=django.db.models.deletion.PROTECT)),
            ('responsavel',models.ForeignKey(to=settings.AUTH_USER_MODEL,related_name='agendamentos_pos_obra',on_delete=django.db.models.deletion.PROTECT)),
            ('criado_por',models.ForeignKey(to=settings.AUTH_USER_MODEL,related_name='+',null=True,on_delete=django.db.models.deletion.SET_NULL)),
            ('respondido_por',models.ForeignKey(to=settings.AUTH_USER_MODEL,related_name='+',null=True,blank=True,on_delete=django.db.models.deletion.SET_NULL)),
        ],options={'ordering':['inicio','pk']}),
        migrations.CreateModel(name='HistoricoAgendamento',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),('de',models.CharField(max_length=20,blank=True)),
            ('para',models.CharField(max_length=20)),('observacao',models.TextField(blank=True)),
            ('criado_em',models.DateTimeField(auto_now_add=True)),
            ('agendamento',models.ForeignKey(to='pos_obra.agendamentoos',related_name='historico',on_delete=django.db.models.deletion.PROTECT)),
            ('usuario',models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,on_delete=django.db.models.deletion.SET_NULL)),
        ]),
        migrations.CreateModel(name='DocumentoOS',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),('tipo',models.CharField(max_length=16,choices=[('EXECUCAO','Execução'),('OS','Ordem de serviço')])),
            ('versao',models.PositiveIntegerField()),('arquivo',models.FileField(storage=core.storage.PrivateMediaStorage(),upload_to='pos_obra/documentos/%Y/%m/')),
            ('sha256',models.CharField(max_length=64)),('criado_em',models.DateTimeField(auto_now_add=True)),
            ('chamado',models.ForeignKey(to='pos_obra.chamado',related_name='documentos_versionados',on_delete=django.db.models.deletion.PROTECT)),
            ('criado_por',models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,on_delete=django.db.models.deletion.SET_NULL)),
        ]),
        migrations.AddConstraint(model_name='documentoos',constraint=models.UniqueConstraint(fields=['chamado','tipo','versao'],name='po_documento_versao_unica')),
        migrations.CreateModel(name='AceiteOS',fields=[
            ('id',models.BigAutoField(primary_key=True,serialize=False)),('signatario',models.CharField(max_length=180)),
            ('representacao',models.CharField(max_length=180)),('resultado',models.CharField(max_length=12,choices=[('ACEITO','Aceito'),('RECUSADO','Recusado'),('RESSALVA','Aceito com ressalvas')])),
            ('observacoes',models.TextField(blank=True)),
            ('assinatura',models.FileField(storage=core.storage.PrivateMediaStorage(),upload_to='pos_obra/assinaturas/%Y/%m/',blank=True)),
            ('criado_em',models.DateTimeField(auto_now_add=True)),
            ('documento',models.OneToOneField(to='pos_obra.documentoos',related_name='aceite',on_delete=django.db.models.deletion.PROTECT)),
            ('usuario_registro',models.ForeignKey(to=settings.AUTH_USER_MODEL,null=True,on_delete=django.db.models.deletion.SET_NULL)),
        ]),
    ]
