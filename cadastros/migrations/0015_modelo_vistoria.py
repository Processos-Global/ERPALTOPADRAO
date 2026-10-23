from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [('cadastros', '0014_dados_empresa')]
    operations = [
        migrations.CreateModel(name='ModeloVistoria', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('nome', models.CharField(max_length=160, unique=True)),
            ('descricao', models.TextField(blank=True)),
            ('versao', models.PositiveIntegerField(default=1)),
            ('ativo', models.BooleanField(default=True)),
        ]),
        migrations.CreateModel(name='CampoModeloVistoria', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('secao', models.CharField(max_length=120)),
            ('chave', models.SlugField(max_length=90)),
            ('titulo', models.CharField(max_length=180)),
            ('tipo', models.CharField(max_length=12, default='TEXTO', choices=[('TEXTO','Texto curto'),('LONGO','Texto longo'),('NUMERO','Número'),('DATA','Data'),('HORA','Hora'),('SELECAO','Seleção'),('MULTIPLA','Múltipla seleção'),('SIM_NAO','Sim / Não')])),
            ('opcoes', models.TextField(blank=True, help_text='Uma opção por linha.')),
            ('obrigatorio', models.BooleanField(default=False)),
            ('ordem', models.PositiveIntegerField(default=0)),
            ('modelo', models.ForeignKey(to='cadastros.modelovistoria', related_name='campos', on_delete=django.db.models.deletion.CASCADE)),
        ], options={'ordering': ('ordem','pk')}),
        migrations.AddConstraint(model_name='campomodelovistoria', constraint=models.UniqueConstraint(fields=('modelo','chave'), name='unq_modelo_vistoria_chave')),
    ]
