from django.db import models
from django.core.validators import RegexValidator


class DadosEmpresa(models.Model):
    """Cadastro institucional único usado por documentos do SAARI ERP."""
    razao_social = models.CharField('Razão social', max_length=255)
    nome_fantasia = models.CharField(max_length=255, default='SAARI', blank=True)
    cnpj = models.CharField(max_length=18, blank=True, validators=[RegexValidator(r'^[0-9./-]{0,18}$', 'CNPJ inválido.')])
    inscricao_estadual = models.CharField(max_length=30, blank=True)
    inscricao_municipal = models.CharField(max_length=30, blank=True)
    cep = models.CharField(max_length=10, blank=True)
    logradouro = models.CharField('Endereço', max_length=255, blank=True)
    numero = models.CharField(max_length=30, blank=True)
    complemento = models.CharField(max_length=120, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    cidade = models.CharField(max_length=120, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    telefone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    responsavel = models.CharField(max_length=160, blank=True)
    logo = models.ImageField(upload_to='empresa/logo/', blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dados institucionais da empresa'
        verbose_name_plural = 'Dados institucionais da empresa'

    @classmethod
    def atual(cls):
        return cls.objects.order_by('pk').first()

    @property
    def endereco_completo(self):
        return ', '.join(filter(None, [self.logradouro, self.numero, self.complemento, self.bairro, self.cidade, self.uf, self.cep]))

    def __str__(self):
        return self.nome_fantasia or self.razao_social
