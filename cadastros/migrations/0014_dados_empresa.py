from django.db import migrations, models
import django.core.validators

class Migration(migrations.Migration):
    dependencies = [('cadastros', '0013_alter_categoriaocorrencia_options_and_more')]
    operations = [migrations.CreateModel(name='DadosEmpresa', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('razao_social', models.CharField(max_length=255, verbose_name='Razão social')),
        ('nome_fantasia', models.CharField(blank=True, default='SAARI', max_length=255)),
        ('cnpj', models.CharField(blank=True, max_length=18, validators=[django.core.validators.RegexValidator('^[0-9./-]{0,18}$','CNPJ inválido.')])),
        ('inscricao_estadual', models.CharField(blank=True,max_length=30)),
        ('inscricao_municipal', models.CharField(blank=True,max_length=30)),
        ('cep', models.CharField(blank=True,max_length=10)),
        ('logradouro', models.CharField(blank=True,max_length=255,verbose_name='Endereço')),
        ('numero', models.CharField(blank=True,max_length=30)),
        ('complemento', models.CharField(blank=True,max_length=120)),
        ('bairro', models.CharField(blank=True,max_length=120)),
        ('cidade', models.CharField(blank=True,max_length=120)),
        ('uf', models.CharField(blank=True,max_length=2)),
        ('telefone', models.CharField(blank=True,max_length=40)),
        ('email', models.EmailField(blank=True,max_length=254)),
        ('responsavel', models.CharField(blank=True,max_length=160)),
        ('logo', models.ImageField(blank=True,upload_to='empresa/logo/')),
        ('atualizado_em', models.DateTimeField(auto_now=True)),
    ],options={'verbose_name':'Dados institucionais da empresa','verbose_name_plural':'Dados institucionais da empresa'})]
