from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('cadastros', '0012_pos_obra_cadastros'), ('obras', '0009_vistorias'), ('usuarios', '0009_preferencias_email_compras')]
    operations = [
        migrations.CreateModel(name='Chamado', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('numero', models.CharField(max_length=32, unique=True, blank=True)),
            ('empreendimento', models.ForeignKey('cadastros.EmpreendimentoPosObra', on_delete=models.PROTECT, related_name='chamados')),
            ('cliente', models.ForeignKey('cadastros.Cliente', on_delete=models.PROTECT, related_name='chamados')),
            ('tipo_problema', models.ForeignKey('cadastros.TipoProblema', on_delete=models.PROTECT)),
            ('ambiente_padrao', models.CharField(max_length=100, blank=True)),
            ('ambiente_ficha', models.ForeignKey('obras.AmbienteFichaTecnica', null=True, blank=True, on_delete=models.SET_NULL)),
            ('ambiente_detalhe', models.CharField(max_length=255, blank=True)),
            ('descricao', models.TextField()),
            ('categoria_original', models.CharField(max_length=120, blank=True)),
            ('tipo_original', models.CharField(max_length=150, blank=True)),
            ('origem', models.CharField(max_length=12, choices=[('INTERNO', 'Interno'), ('PORTAL', 'Portal')], default='INTERNO')),
            ('status', models.CharField(max_length=30, choices=[('ABERTO', 'Aberto'), ('TRIAGEM', 'Triagem'), ('VISTORIA', 'Vistoria'), ('AGUARDANDO_MATERIAL', 'Aguardando Material'), ('AGUARDANDO_CLIENTE', 'Aguardando Cliente'), ('EXECUCAO', 'Execucao'), ('FINALIZACAO', 'Finalizacao'), ('CONCLUIDO', 'Concluido'), ('REABERTO', 'Reaberto'), ('CANCELADO', 'Cancelado')], default='ABERTO', db_index=True)),
            ('prioridade', models.CharField(max_length=10, choices=[('BAIXA', 'Baixa'), ('NORMAL', 'Normal'), ('ALTA', 'Alta'), ('URGENTE', 'Urgente')], default='NORMAL')),
            ('responsavel', models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)),
            ('garantia', models.CharField(max_length=100, blank=True)),
            ('triagem', models.TextField(blank=True)),
            ('diagnostico', models.TextField(blank=True)),
            ('data_vistoria', models.DateField(null=True, blank=True)),
            ('materiais_observacao', models.TextField(blank=True)),
            ('execucao', models.TextField(blank=True)),
            ('data_execucao', models.DateField(null=True, blank=True)),
            ('conclusao', models.TextField(blank=True)),
            ('prazo', models.DateField(null=True, blank=True)),
            ('finalizado_em', models.DateTimeField(null=True, blank=True)),
            ('criado_em', models.DateTimeField(auto_now_add=True)),
            ('atualizado_em', models.DateTimeField(auto_now=True))
        ]),
        migrations.CreateModel(name='MaterialOS', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('chamado', models.ForeignKey("pos_obra.Chamado", on_delete=models.CASCADE, related_name='materiais')),
            ('descricao', models.CharField(max_length=255)),
            ('unidade', models.CharField(max_length=30, default='UN')),
            ('previsto', models.DecimalField(max_digits=12, decimal_places=3, default=0)),
            ('utilizado', models.DecimalField(max_digits=12, decimal_places=3, default=0)),
            ('custo_unitario', models.DecimalField(max_digits=14, decimal_places=4, default=0)),
            ('observacoes', models.TextField(blank=True))
        ]),
        migrations.CreateModel(name='RegistroChamado', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('chamado', models.ForeignKey("pos_obra.Chamado", on_delete=models.CASCADE, related_name='historico')),
            ('usuario', models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)),
            ('status_anterior', models.CharField(max_length=30, blank=True)),
            ('status_novo', models.CharField(max_length=30, blank=True)),
            ('mensagem', models.TextField()),
            ('publico', models.BooleanField(default=False)),
            ('criado_em', models.DateTimeField(auto_now_add=True))
        ]),
        migrations.CreateModel(name='AnexoChamado', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('chamado', models.ForeignKey("pos_obra.Chamado", on_delete=models.CASCADE, related_name='anexos')),
            ('etapa', models.CharField(max_length=30, choices=[(s, s.title()) for s in ('ABERTURA', 'TRIAGEM', 'VISTORIA', 'EXECUCAO', 'FINALIZACAO')])),
            ('arquivo', models.FileField(upload_to='private/pos_obra/%Y/%m/')),
            ('publico', models.BooleanField(default=False)),
            ('criado_em', models.DateTimeField(auto_now_add=True))
        ]),
        migrations.CreateModel(name='PesquisaSatisfacao', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('chamado', models.OneToOneField("pos_obra.Chamado", on_delete=models.CASCADE, related_name='pesquisa')),
            ('atendimento', models.PositiveSmallIntegerField()),
            ('prazo', models.PositiveSmallIntegerField()),
            ('qualidade', models.PositiveSmallIntegerField()),
            ('resolvido', models.CharField(max_length=12, choices=[('SIM', 'Sim'), ('PARCIAL', 'Parcialmente'), ('NAO', 'Não')])),
            ('comentario', models.TextField(blank=True)),
            ('criado_em', models.DateTimeField(auto_now_add=True))
        ]),
    ]
