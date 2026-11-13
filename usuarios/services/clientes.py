"""Persistência integrada de contas e clientes, sem inferir vínculos legados."""
import re
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Replace, Upper, Trim
from cadastros.models import Cliente, VinculoCliente, EmpreendimentoPosObra
from usuarios.models import PerfilUsuario, PermissaoModulo


def normalizar_documento(value):
    return re.sub(r'[^A-Z0-9]', '', (value or '').upper())


def clientes_com_documento(documento):
    expr=Upper(Trim('documento'))
    for caractere in ('.', '-', '/', ' ', '\t', '\n', '\r'):
        expr=Replace(expr, Value(caractere), Value(''))
    return Cliente.objects.annotate(documento_comparavel=expr).filter(documento_comparavel=documento)


@transaction.atomic
def salvar_usuario_integrado(*, usuario, dados):
    # Um lock estável serializa cadastros integrados, inclusive documentos ainda
    # inexistentes. Não altera o schema nem tenta deduplicar os dados legados.
    ct=ContentType.objects.get_for_model(Cliente)
    ContentType.objects.select_for_update().get(pk=ct.pk)
    User=get_user_model()
    if usuario.pk:
        User.objects.select_for_update().get(pk=usuario.pk)
    if User.objects.filter(username__iexact=usuario.username).exclude(pk=usuario.pk).exists():
        raise ValidationError({'username':'Este nome de usuário acabou de ser utilizado. Escolha outro.'})
    atual=Cliente.objects.select_for_update().filter(usuario_id=usuario.pk).first() if usuario.pk else None
    cliente=None
    if dados['tipo_acesso']=='CLIENTE':
        if usuario.is_staff or usuario.is_superuser or (usuario.pk and PermissaoModulo.objects.filter(usuario=usuario,ativo=True).exists()):
            raise ValidationError({'tipo_acesso':'Remova os privilégios internos antes de converter esta conta.'})
        selecionado=dados.get('cliente_vinculado')
        if atual and selecionado and atual.pk!=selecionado.pk:
            raise ValidationError({'cliente_vinculado':'A conta já pertence a outro cliente.'})
        cliente=atual or (Cliente.objects.select_for_update().get(pk=selecionado.pk) if selecionado else Cliente())
        if cliente.usuario_id and cliente.usuario_id!=usuario.pk:
            raise ValidationError({'cliente_vinculado':'Este cliente já possui uma conta. Atualize a página.'})
        documento=normalizar_documento(dados.get('cliente_documento'))
        if documento and clientes_com_documento(documento).exclude(pk=cliente.pk).exists():
            raise ValidationError({'cliente_documento':'Documento já cadastrado. Selecione explicitamente o cliente legado ou revise a duplicidade.'})
        obras=list(dados.get('empreendimentos_cliente') or [])
        ids={e.pk for e in obras}
        liberadas=set(EmpreendimentoPosObra.objects.select_for_update().filter(pk__in=ids,liberada=True).values_list('pk',flat=True))
        existentes=set(VinculoCliente.objects.filter(cliente=cliente,ativo=True).values_list('empreendimento_id',flat=True)) if cliente.pk else set()
        if cliente.pk and atual is None:
            # Associar uma conta a um legado nunca revoga vínculos preexistentes.
            # A manutenção explícita ocorre depois, na edição da conta associada.
            ids |= existentes
            obras=list(EmpreendimentoPosObra.objects.filter(pk__in=ids))
        if ids-liberadas-existentes:
            raise ValidationError({'empreendimentos_cliente':'Uma obra selecionada não está mais liberada.'})
        if dados.get('portal_habilitado') and not ids:
            raise ValidationError({'empreendimentos_cliente':'Selecione ao menos uma obra para habilitar o portal.'})
    elif atual:
        raise ValidationError({'tipo_acesso':'Contas de cliente não podem ser convertidas em internas.'})
    usuario.save()
    perfil,_=PerfilUsuario.objects.get_or_create(usuario=usuario)
    perfil.cargo=PerfilUsuario.Cargo.OUTRO if cliente is not None else dados['cargo']
    perfil.telefone=dados.get('telefone','')
    perfil.ativo=usuario.is_active
    perfil.save()
    if cliente is not None:
        cliente.usuario=usuario
        for campo in ('nome','documento','email','telefone','ativo'):
            setattr(cliente,campo,dados.get('cliente_'+campo,''))
        cliente.documento=documento
        cliente.portal_habilitado=bool(dados.get('portal_habilitado'))
        cliente.full_clean()
        cliente.save()
        VinculoCliente.objects.filter(cliente=cliente).exclude(empreendimento_id__in=ids).update(ativo=False)
        for obra in obras:
            VinculoCliente.objects.update_or_create(cliente=cliente,empreendimento=obra,defaults={'ativo':True})
    return usuario
