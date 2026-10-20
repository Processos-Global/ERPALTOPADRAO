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
    preferencia_data=models.DateField(null=True,blank=True,verbose_name='Data preferencial')
    preferencia_periodo=models.CharField(max_length=12,blank=True,choices=[('MANHA','Manhã'),('TARDE','Tarde'),('HORARIO','Horário específico')],verbose_name='Período preferencial')
    preferencia_inicio=models.TimeField(null=True,blank=True,verbose_name='Disponível a partir de')
    preferencia_fim=models.TimeField(null=True,blank=True,verbose_name='Disponível até')
    preferencia_alternativa=models.DateField(null=True,blank=True,verbose_name='Segunda opção de data')
    horario_flexivel=models.BooleanField(default=False,verbose_name='Tenho flexibilidade de horário')
    orientacoes_acesso=models.TextField(blank=True,verbose_name='Orientações de acesso ao imóvel')
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


class AgendamentoOS(models.Model):
    TIPOS=[('VISTORIA','Vistoria'),('EXECUCAO','Execução'),('RETORNO','Retorno técnico'),('COMPLEMENTO','Complementação')]
    SITUACOES=[('PROPOSTO','Aguardando confirmação'),('CONFIRMADO','Confirmado'),('REAGENDAMENTO','Reagendamento solicitado'),('SUBSTITUIDO','Reagendado'),('CANCELADO','Cancelado'),('REALIZADO','Realizado'),('NAO_REALIZADO','Não realizado')]
    chamado=models.ForeignKey(Chamado,on_delete=models.PROTECT,related_name='agendamentos')
    tipo=models.CharField(max_length=20,choices=TIPOS)
    inicio=models.DateTimeField()
    fim=models.DateTimeField()
    responsavel=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='agendamentos_pos_obra')
    situacao=models.CharField(max_length=20,choices=SITUACOES,default='PROPOSTO')
    observacoes=models.TextField(blank=True)
    criado_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,related_name='+')
    criado_em=models.DateTimeField(auto_now_add=True)
    confirmado_em=models.DateTimeField(null=True,blank=True)
    respondido_por=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,related_name='+')
    class Meta:
        ordering=['inicio','pk']
    def __str__(self):return f'{self.chamado.numero} - {self.get_tipo_display()} - {self.inicio}'

class HistoricoAgendamento(models.Model):
    agendamento=models.ForeignKey(AgendamentoOS,on_delete=models.PROTECT,related_name='historico')
    usuario=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    de=models.CharField(max_length=20,blank=True)
    para=models.CharField(max_length=20)
    observacao=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)

class DocumentoOS(models.Model):
    chamado=models.ForeignKey(Chamado,on_delete=models.PROTECT,related_name='documentos_versionados')
    tipo=models.CharField(max_length=16,choices=[('EXECUCAO','Execução'),('OS','Ordem de serviço')])
    versao=models.PositiveIntegerField()
    arquivo=models.FileField(storage=PrivateMediaStorage(),upload_to='pos_obra/documentos/%Y/%m/')
    sha256=models.CharField(max_length=64)
    criado_por=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    criado_em=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['chamado','tipo','versao'],name='po_documento_versao_unica')]

class AceiteOS(models.Model):
    RESULTADOS=[('ACEITO','Aceito'),('RECUSADO','Recusado'),('RESSALVA','Aceito com ressalvas')]
    documento=models.OneToOneField(DocumentoOS,on_delete=models.PROTECT,related_name='aceite')
    signatario=models.CharField(max_length=180)
    representacao=models.CharField(max_length=180)
    resultado=models.CharField(max_length=12,choices=RESULTADOS)
    observacoes=models.TextField(blank=True)
    assinatura=models.FileField(storage=PrivateMediaStorage(),upload_to='pos_obra/assinaturas/%Y/%m/',blank=True)
    usuario_registro=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    criado_em=models.DateTimeField(auto_now_add=True)


class NotificacaoOS(models.Model):
    chamado=models.ForeignKey(Chamado,on_delete=models.CASCADE,related_name='notificacoes')
    evento=models.CharField(max_length=48)
    destinatario=models.EmailField()
    assunto=models.CharField(max_length=250)
    mensagem=models.TextField()
    chave=models.CharField(max_length=160,unique=True)
    situacao=models.CharField(max_length=16,default='PENDENTE',choices=[('PENDENTE','Pendente'),('ENVIADO','Enviado'),('ERRO','Erro')])
    tentativas=models.PositiveIntegerField(default=0)
    ultimo_erro=models.TextField(blank=True)
    criado_em=models.DateTimeField(auto_now_add=True)
    enviado_em=models.DateTimeField(null=True,blank=True)
    class Meta:
        ordering=['-criado_em']

class TratativaSatisfacao(models.Model):
    chamado=models.ForeignKey(Chamado,on_delete=models.PROTECT,related_name='tratativas_satisfacao')
    observacao=models.TextField()
    responsavel=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    criado_em=models.DateTimeField(auto_now_add=True)
