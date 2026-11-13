from django.conf import settings
from django.db import models


class VistoriaCautelar(models.Model):
    class Situacao(models.TextChoices):
        RASCUNHO = 'RASCUNHO', 'Em preenchimento'
        FINALIZADA = 'FINALIZADA', 'Finalizada'

    obra = models.ForeignKey('obras.Obra', on_delete=models.PROTECT, related_name='vistorias_cautelares')
    modelo = models.ForeignKey('cadastros.ModeloVistoria', on_delete=models.PROTECT)
    codigo = models.CharField(max_length=25)
    endereco = models.CharField(max_length=255, blank=True)
    posicao = models.CharField(max_length=80, blank=True)
    respostas = models.JSONField(default=dict, blank=True)
    esquema = models.JSONField(default=list, blank=True)
    situacao = models.CharField(max_length=12, choices=Situacao.choices, default=Situacao.RASCUNHO)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-criado_em', '-pk')
        constraints = [models.UniqueConstraint(fields=['obra', 'codigo'], name='unq_codigo_cautelar_obra')]

    def __str__(self):
        return f'{self.codigo} — {self.obra}'


class OcorrenciaCautelar(models.Model):
    vistoria = models.ForeignKey(VistoriaCautelar, related_name='ocorrencias', on_delete=models.CASCADE)
    ambiente = models.CharField(max_length=120)
    elemento = models.CharField(max_length=120, blank=True)
    manifestacao = models.CharField(max_length=120)
    localizacao = models.CharField(max_length=200, blank=True)
    descricao = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('pk',)


class FotoCautelar(models.Model):
    vistoria = models.ForeignKey(VistoriaCautelar, related_name='fotos', on_delete=models.CASCADE)
    ocorrencia = models.ForeignKey(OcorrenciaCautelar, related_name='fotos', on_delete=models.CASCADE, null=True, blank=True)
    imagem = models.ImageField(upload_to='vistorias/cautelares/%Y/%m/')
    legenda = models.CharField(max_length=255, blank=True)
    criada_em = models.DateTimeField(auto_now_add=True)
