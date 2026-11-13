from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('cadastros', '0011_checklist_documental'), ('obras', '0009_vistorias'), ('usuarios', '0009_preferencias_email_compras')]
    operations = [
        migrations.CreateModel(name='Cliente', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('nome', models.CharField(max_length=255)),
            ('documento', models.CharField(max_length=20, blank=True, db_index=True)),
            ('email', models.EmailField(blank=True)),
            ('telefone', models.CharField(max_length=40, blank=True)),
            ('usuario', models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='cliente_saari')),
            ('ativo', models.BooleanField(default=True)),
            ('portal_habilitado', models.BooleanField(default=False)),
            ('criado_em', models.DateTimeField(auto_now_add=True))
        ]),
        migrations.CreateModel(name='EmpreendimentoPosObra', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('obra', models.OneToOneField('obras.Obra', null=True, blank=True, on_delete=models.PROTECT, related_name='empreendimento_pos_obra')),
            ('nome_historico', models.CharField(max_length=255, blank=True)),
            ('codigo_historico', models.CharField(max_length=80, blank=True)),
            ('endereco_historico', models.CharField(max_length=255, blank=True)),
            ('historica', models.BooleanField(default=False)),
            ('data_entrega', models.DateField(null=True, blank=True)),
            ('liberada', models.BooleanField(default=False)),
            ('liberado_por', models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)),
            ('liberado_em', models.DateTimeField(null=True, blank=True))
        ]),
        migrations.CreateModel(name='VinculoCliente', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('cliente', models.ForeignKey("cadastros.Cliente", on_delete=models.PROTECT, related_name='vinculos')),
            ('empreendimento', models.ForeignKey("cadastros.EmpreendimentoPosObra", on_delete=models.PROTECT, related_name='vinculos')),
            ('papel', models.CharField(max_length=20, choices=[('PROPRIETARIO', 'Proprietário'), ('AUTORIZADO', 'Pessoa autorizada')], default='PROPRIETARIO')),
            ('ativo', models.BooleanField(default=True))
        ]),
        migrations.CreateModel(name='CategoriaOcorrencia', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('nome', models.CharField(max_length=120, unique=True)),
            ('ordem', models.PositiveIntegerField(default=0)),
            ('ativa', models.BooleanField(default=True))
        ]),
        migrations.CreateModel(name='TipoProblema', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('categoria', models.ForeignKey("cadastros.CategoriaOcorrencia", on_delete=models.PROTECT, related_name='tipos')),
            ('nome', models.CharField(max_length=150)),
            ('ativo', models.BooleanField(default=True))
        ]),
    ]
