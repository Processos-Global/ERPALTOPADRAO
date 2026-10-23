from django.db import models


class ModeloVistoria(models.Model):
    nome = models.CharField(max_length=160, unique=True)
    descricao = models.TextField(blank=True)
    versao = models.PositiveIntegerField(default=1)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome


class CampoModeloVistoria(models.Model):
    class Tipo(models.TextChoices):
        TEXTO = 'TEXTO', 'Texto curto'
        LONGO = 'LONGO', 'Texto longo'
        NUMERO = 'NUMERO', 'Número'
        DATA = 'DATA', 'Data'
        HORA = 'HORA', 'Hora'
        SELECAO = 'SELECAO', 'Seleção'
        MULTIPLA = 'MULTIPLA', 'Múltipla seleção'
        SIM_NAO = 'SIM_NAO', 'Sim / Não'

    modelo = models.ForeignKey(ModeloVistoria, on_delete=models.CASCADE, related_name='campos')
    secao = models.CharField(max_length=120)
    chave = models.SlugField(max_length=90)
    titulo = models.CharField(max_length=180)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.TEXTO)
    opcoes = models.TextField(blank=True, help_text='Uma opção por linha.')
    obrigatorio = models.BooleanField(default=False)
    ordem = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('ordem', 'pk')
        constraints = [models.UniqueConstraint(fields=['modelo', 'chave'], name='unq_modelo_vistoria_chave')]

    def __str__(self):
        return self.titulo

    def lista_opcoes(self):
        return [s.strip() for s in self.opcoes.splitlines() if s.strip()]
