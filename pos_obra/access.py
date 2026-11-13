from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Cliente,VinculoCliente
from usuarios.decorators import possui_permissao_acao
from usuarios.models import ModuloSistema

def cliente_do_usuario(user):
    return Cliente.objects.filter(usuario=user,ativo=True,portal_habilitado=True).first() if user.is_authenticated else None

def acesso_interno(user):
    if not user.is_authenticated or Cliente.objects.filter(usuario=user).exists(): return False
    if user.is_superuser: return True
    perfil=getattr(user,'perfil_erp',None)
    return bool(perfil and perfil.ativo and perfil.cargo in ['POS_OBRA','DIRETORIA','GERENCIA'])

def interno(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not acesso_interno(request.user) or not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'visualizar'):
            raise PermissionDenied('Acesso restrito ao Pós-Obra.')
        return view(request,*args,**kwargs)
    return wrapped

def cliente(view):
    @login_required
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if not cliente_do_usuario(request.user):raise PermissionDenied('Acesso exclusivo de cliente.')
        return view(request,*args,**kwargs)
    return wrapped

def pode_acessar(cliente_obj,chamado):
    return chamado.cliente_id==cliente_obj.id and VinculoCliente.objects.filter(cliente=cliente_obj,empreendimento=chamado.empreendimento,ativo=True).exists()
