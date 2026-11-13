from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from django.db.models import Q
from cadastros.models.pos_obra import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
from pos_obra.access import acesso_interno
from pos_obra.forms import ClienteForm, EmpreendimentoForm, VinculoForm, CategoriaForm, TipoProblemaForm

FORMULARIOS = {
    'clientes': ClienteForm, 'empreendimentos': EmpreendimentoForm,
    'vinculos': VinculoForm, 'categorias': CategoriaForm, 'problemas': TipoProblemaForm,
}

MAPA={'clientes':(Cliente,['nome','documento','email','telefone','usuario','ativo','portal_habilitado']), 'empreendimentos':(EmpreendimentoPosObra,['obra','nome_historico','codigo_historico','endereco_historico','historica','data_entrega']), 'vinculos':(VinculoCliente,['cliente','empreendimento','papel','ativo']), 'categorias':(CategoriaOcorrencia,['nome','ordem','ativa']), 'problemas':(TipoProblema,['categoria','nome','ativo'])}
def permission(request):
    from usuarios.decorators import possui_permissao_acao
    from usuarios.models import ModuloSistema
    from usuarios.services import pode_acao_cadastros
    acao='editar' if request.method=='POST' else 'visualizar'
    if not (pode_acao_cadastros(request.user,acao) or possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'gerenciar_clientes')):raise PermissionDenied('Permissão insuficiente para manutenção de obras.')
    if not acesso_interno(request.user):raise PermissionDenied('Cadastros de Pós-Obra são internos.')
def config(modelo):
    if modelo not in MAPA:raise PermissionDenied('Cadastro inválido.')
    return MAPA[modelo]
@login_required
def lista(request,modelo):
    permission(request)
    if modelo in ('categorias','problemas'):
        if request.method not in ('GET','HEAD'):raise PermissionDenied('Mantenha o catálogo no Pós-Obra.')
        return redirect('pos_obra:cadastros',modelo=modelo)
    if modelo in ('clientes', 'vinculos'):
        if request.method not in ('GET', 'HEAD'):
            raise PermissionDenied('Clientes e vínculos são mantidos exclusivamente em Usuários.')
        messages.info(request, 'Gerencie os imóveis vinculados diretamente em Usuários.')
        return redirect('usuarios:lista_usuarios')
    Model,_=config(modelo)
    from django.core.paginator import Paginator
    qs = Model.objects.all()
    if modelo == 'clientes':
        qs = qs.select_related('usuario')
    elif modelo == 'empreendimentos':
        qs = qs.select_related('obra')
    elif modelo in ('clientes', 'vinculos'):
        qs = qs.select_related('cliente', 'empreendimento__obra')
    elif modelo == 'problemas':
        qs = qs.select_related('categoria')
    termo = request.GET.get('q', '').strip()
    if termo:
        if modelo in ('clientes', 'vinculos'):
            qs = qs.filter(Q(cliente__nome__icontains=termo) | Q(empreendimento__nome_historico__icontains=termo) | Q(empreendimento__obra__nome__icontains=termo))
        elif modelo == 'empreendimentos':
            qs = qs.filter(Q(nome_historico__icontains=termo) | Q(obra__nome__icontains=termo))
        else:
            qs = qs.filter(nome__icontains=termo)
    objs=Paginator(qs.order_by('-pk'),25).get_page(request.GET.get('page'))
    return render(request,'cadastros/pos_obra/lista.html',{'titulo':modelo.title(),'modelo':modelo,'objetos':objs})
@login_required
def editar(request,modelo,pk=None):
    permission(request)
    if modelo in ('categorias','problemas'):
        if request.method not in ('GET','HEAD'):raise PermissionDenied('Mantenha o catálogo no Pós-Obra.')
        return redirect('pos_obra:cadastros',modelo=modelo)
    if modelo in ('clientes', 'vinculos'):
        if request.method not in ('GET', 'HEAD'):
            raise PermissionDenied('Clientes e vínculos são mantidos exclusivamente em Usuários.')
        messages.info(request, 'Gerencie vínculos no cadastro ou manutenção do usuário.')
        return redirect('usuarios:lista_usuarios')
    Model,fields=config(modelo)
    obj=get_object_or_404(Model,pk=pk) if pk else None
    F = FORMULARIOS[modelo]
    form=F(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save()
        messages.success(request, 'Cadastro salvo.')
        return redirect('cadastros:pos_obra_lista', modelo=modelo)
    return render(request,'cadastros/pos_obra/form.html',{'form':form,'titulo':modelo.title(),'modelo':modelo})
@login_required
def liberar(request,pk):
    permission(request)
    if request.method!='POST':raise PermissionDenied('Operação requer POST.')
    e=get_object_or_404(EmpreendimentoPosObra,pk=pk)
    if e.obra_id and e.obra.status!='CONCLUIDA':raise PermissionDenied('Obra ainda não concluída.')
    if not e.liberada:
        e.liberada=True;e.liberado_por=request.user;e.liberado_em=timezone.now();e.save(update_fields=['liberada','liberado_por','liberado_em'])
    return redirect('cadastros:pos_obra_lista',modelo='empreendimentos')
