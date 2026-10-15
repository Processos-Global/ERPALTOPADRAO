from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


def usuarios_para_portal():
    """Contas sem atribuições internas, disponíveis para o portal de clientes."""
    from django.contrib.auth import get_user_model
    from usuarios.models import PerfilUsuario
    cargos_internos = [cargo for cargo, _ in PerfilUsuario.Cargo.choices if cargo != PerfilUsuario.Cargo.OUTRO]
    return (get_user_model().objects.filter(is_staff=False, is_superuser=False)
            .exclude(perfil_erp__cargo__in=cargos_internos)
            .exclude(permissoes_modulos_erp__ativo=True))

class Cliente(models.Model):
    nome=models.CharField(max_length=255)
    documento=models.CharField(max_length=20,blank=True,db_index=True)
    email=models.EmailField(blank=True)
    telefone=models.CharField(max_length=40,blank=True)
    usuario=models.OneToOneField(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='cliente_saari')
    ativo=models.BooleanField(default=True)
    portal_habilitado=models.BooleanField(default=False)
    criado_em=models.DateTimeField(auto_now_add=True)
    def clean(self):
        super().clean()
        if self.usuario_id and not usuarios_para_portal().filter(pk=self.usuario_id).exists():
            raise ValidationError({'usuario': 'Use uma conta exclusiva de cliente, sem cargo ou permissões internas.'})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):return self.nome

class EmpreendimentoPosObra(models.Model):
    obra=models.OneToOneField('obras.Obra',null=True,blank=True,on_delete=models.PROTECT,related_name='empreendimento_pos_obra')
    nome_historico=models.CharField(max_length=255,blank=True)
    codigo_historico=models.CharField(max_length=80,blank=True)
    endereco_historico=models.CharField(max_length=255,blank=True)
    historica=models.BooleanField(default=False)
    data_entrega=models.DateField(null=True,blank=True)
    liberada=models.BooleanField(default=False)
    liberado_por=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    liberado_em=models.DateTimeField(null=True,blank=True)
    def clean(self):
        super().clean()
        errors = {}
        if self.historica:
            if self.obra_id:
                errors['obra'] = 'Um imóvel histórico não pode referenciar uma obra do sistema.'
            if not self.nome_historico.strip():
                errors['nome_historico'] = 'Informe o nome do imóvel histórico.'
        elif not self.obra_id:
            errors['obra'] = 'Selecione a obra atual.'
        elif self.obra.status != 'CONCLUIDA':
            # Uma mudança posterior do status da obra não impede manter o cadastro existente.
            original = type(self).objects.filter(pk=self.pk, obra_id=self.obra_id).first() if self.pk else None
            if not original or not original.liberada:
                errors['obra'] = 'A obra precisa estar concluída.'
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()
            mudou_identidade = original and (original.obra_id != self.obra_id or original.historica != self.historica)
            if mudou_identidade and (original.liberada or original.vinculos.exists() or original.chamados.exists()):
                errors['obra'] = 'Não é possível trocar a obra de um imóvel liberado ou com vínculos/chamados. Cadastre outro imóvel.'
                errors['historica'] = 'A origem deste imóvel já está em uso e não pode ser alterada.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):return self.obra.nome if self.obra_id else self.nome_historico

class VinculoCliente(models.Model):
    PAPEIS=[('PROPRIETARIO','Proprietário'),('AUTORIZADO','Pessoa autorizada')]
    cliente=models.ForeignKey(Cliente,on_delete=models.PROTECT,related_name='vinculos')
    empreendimento=models.ForeignKey(EmpreendimentoPosObra,on_delete=models.PROTECT,related_name='vinculos')
    papel=models.CharField(max_length=20,choices=PAPEIS,default='PROPRIETARIO')
    ativo=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['cliente','empreendimento'],name='cad_pos_vinculo_unico')]
    def __str__(self):return f'{self.cliente} — {self.empreendimento}'

class CategoriaOcorrencia(models.Model):
    nome=models.CharField(max_length=120,unique=True)
    ordem=models.PositiveIntegerField(default=0)
    ativa=models.BooleanField(default=True)
    class Meta:ordering=['ordem','nome']
    def __str__(self):return self.nome

class TipoProblema(models.Model):
    categoria=models.ForeignKey(CategoriaOcorrencia,on_delete=models.PROTECT,related_name='tipos')
    nome=models.CharField(max_length=150)
    ativo=models.BooleanField(default=True)
    class Meta:constraints=[models.UniqueConstraint(fields=['categoria','nome'],name='cad_pos_tipo_unico')]
    def __str__(self):return f'{self.categoria} — {self.nome}'
