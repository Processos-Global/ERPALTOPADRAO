from django.db import models
from django.conf import settings
from django.utils import timezone
from core.storage import PrivateMediaStorage

class Chamado(models.Model):
    STATUS=[(x,x.title().replace('_',' ')) for x in ('ABERTO','TRIAGEM','VISTORIA','AGUARDANDO_MATERIAL','AGUARDANDO_CLIENTE','EXECUCAO','FINALIZACAO','CONCLUIDO','REABERTO','CANCELADO')]
    PRIORIDADES=[('BAIXA','Baixa'),('NORMAL','Normal'),('ALTA','Alta'),('URGENTE','Urgente')]
    numero=models.CharField(max_length=32,unique=True,blank=True)
    empreendimento=models.ForeignKey('cadastros.EmpreendimentoPosObra',on_delete=models.PROTECT,related_name='chamados')
    cliente=models.ForeignKey('cadastros.Cliente',on_delete=models.PROTECT,related_name='chamados')
    tipo_problema=models.ForeignKey('cadastros.TipoProblema',on_delete=models.PROTECT)
    ambiente_padrao=models.CharField(max_length=100,blank=True)
    ambiente_ficha=models.ForeignKey('obras.AmbienteFichaTecnica',null=True,blank=True,on_delete=models.SET_NULL)
    ambiente_detalhe=models.CharField(max_length=255,blank=True)
    descricao=models.TextField()
    categoria_original=models.CharField(max_length=120,blank=True)
    tipo_original=models.CharField(max_length=150,blank=True)
    origem=models.CharField(max_length=12,choices=[('INTERNO','Interno'),('PORTAL','Portal')],default='INTERNO')
    status=models.CharField(max_length=30,choices=STATUS,default='ABERTO',db_index=True)
    prioridade=models.CharField(max_length=10,choices=PRIORIDADES,default='NORMAL')
    responsavel=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    garantia=models.CharField(max_length=100,blank=True)
    triagem=models.TextField(blank=True)
    diagnostico=models.TextField(blank=True)
    data_vistoria=models.DateField(null=True,blank=True)
    materiais_observacao=models.TextField(blank=True)
    execucao=models.TextField(blank=True)
    data_execucao=models.DateField(null=True,blank=True)
    conclusao=models.TextField(blank=True)
    prazo=models.DateField(null=True,blank=True)
    finalizado_em=models.DateTimeField(null=True,blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    atualizado_em=models.DateTimeField(auto_now=True)
    def save(self,*args,**kwargs):
        if not self.numero:
            import uuid
            self.numero='OS-'+timezone.now().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:8].upper()
        super().save(*args,**kwargs)
    def __str__(self):return self.numero

class MaterialOS(models.Model):
    material=models.ForeignKey('cadastros.Material',null=True,blank=True,on_delete=models.PROTECT,related_name='materiais_pos_obra')
    chamado=models.ForeignKey(Chamado,on_delete=models.CASCADE,related_name='materiais')
    descricao=models.CharField(max_length=255)
    unidade=models.CharField(max_length=30,default='UN')
    previsto=models.DecimalField(max_digits=12,decimal_places=3,default=0)
    utilizado=models.DecimalField(max_digits=12,decimal_places=3,default=0)
    custo_unitario=models.DecimalField(max_digits=14,decimal_places=4,default=0)
    observacoes=models.TextField(blank=True)
    @property
    def total(self):return self.utilizado*self.custo_unitario

class RegistroChamado(models.Model):
    chamado=models.ForeignKey(Chamado,on_delete=models.CASCADE,related_name='historico')
    usuario=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    status_anterior=models.CharField(max_length=30,blank=True)
    status_novo=models.CharField(max_length=30,blank=True)
    mensagem=models.TextField()
    publico=models.BooleanField(default=False)
    criado_em=models.DateTimeField(auto_now_add=True)
    class Meta:ordering=['-criado_em']

class AnexoChamado(models.Model):
    chamado=models.ForeignKey(Chamado,on_delete=models.CASCADE,related_name='anexos')
    etapa=models.CharField(max_length=30,choices=[(s,s.title()) for s in ('ABERTURA','TRIAGEM','VISTORIA','EXECUCAO','FINALIZACAO')])
    arquivo=models.FileField(storage=PrivateMediaStorage(),upload_to='pos_obra/%Y/%m/')
    publico=models.BooleanField(default=False)
    criado_em=models.DateTimeField(auto_now_add=True)

class PesquisaSatisfacao(models.Model):
    chamado=models.OneToOneField(Chamado,on_delete=models.CASCADE,related_name='pesquisa')
    atendimento=models.PositiveSmallIntegerField()
    prazo=models.PositiveSmallIntegerField()
    qualidade=models.PositiveSmallIntegerField()
    resolvido=models.CharField(max_length=12,choices=[('SIM','Sim'),('PARCIAL','Parcialmente'),('NAO','Não')])
    comentario=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
