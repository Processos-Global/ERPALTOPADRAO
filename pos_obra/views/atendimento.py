from pathlib import Path
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.db import transaction
from django.http import JsonResponse
from django.http import HttpResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from ..models import *
from ..forms import ChamadoForm,AtendimentoForm,MaterialForm,PesquisaForm,MaterialQuantidadeForm,AnexoForm
from ..access import interno,cliente,cliente_do_usuario,pode_acessar,acesso_interno

@interno
def painel(request):
    qs=Chamado.objects.all()
    return render(request,'pos_obra/painel.html',{'total':qs.count(),'abertos':qs.exclude(status__in=['CONCLUIDO','CANCELADO']).count(),'concluidos':qs.filter(status='CONCLUIDO').count(),'satisfacao':PesquisaSatisfacao.objects.aggregate(x=Avg('atendimento'))['x'],'chamados':qs.select_related('cliente','empreendimento__obra').order_by('-criado_em')[:12]})
def filtros_chamados(request, qs):
    for name in ('status', 'prioridade'):
        if request.GET.get(name):
            qs = qs.filter(**{name: request.GET[name]})
    termo = request.GET.get('q', '').strip()
    if termo:
        qs = qs.filter(Q(numero__icontains=termo) | Q(cliente__nome__icontains=termo) |
                       Q(empreendimento__obra__nome__icontains=termo) |
                       Q(empreendimento__nome_historico__icontains=termo))
    return qs

def pagina_contexto(request):
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()

@interno
def lista(request):
    qs = filtros_chamados(request, Chamado.objects.select_related(
        'cliente', 'empreendimento__obra', 'tipo_problema', 'responsavel')).order_by('-criado_em', '-pk')
    return render(request, 'pos_obra/lista.html', {
        'chamados': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_choices': Chamado.STATUS, 'prioridade_choices': Chamado.PRIORIDADES,
        'status_atual': request.GET.get('status', ''), 'pagina_query': pagina_contexto(request)})

@interno
def kanban(request):
    qs = filtros_chamados(request, Chamado.objects.select_related(
        'cliente', 'empreendimento__obra', 'tipo_problema')).order_by('-criado_em', '-pk')
    contagens = dict(qs.values('status').annotate(total=Count('pk')).values_list('status', 'total'))
    grupos = [{'codigo': key, 'nome': label, 'total': contagens.get(key, 0),
               'itens': list(qs.filter(status=key)[:30])} for key, label in Chamado.STATUS]
    return render(request, 'pos_obra/kanban.html', {'grupos': grupos, 'filtros_query': pagina_contexto(request)})


def registro(chamado,user,anterior,mensagem,publico=False):
    RegistroChamado.objects.create(chamado=chamado,usuario=user,status_anterior=anterior,status_novo=chamado.status,mensagem=mensagem,publico=publico)

def salvar_abertura(form, usuario, origem):
    with transaction.atomic():
        obj = form.save(commit=False)
        obj.origem = origem
        obj.categoria_original = obj.tipo_problema.categoria.nome
        obj.tipo_original = obj.tipo_problema.nome
        obj.save()
        arquivo = form.cleaned_data.get('arquivo')
        if arquivo:
            AnexoChamado.objects.create(chamado=obj, etapa='ABERTURA', arquivo=arquivo, publico=(origem == 'PORTAL'))
        registro(obj, usuario, '', 'Chamado recebido' if origem == 'PORTAL' else 'Chamado criado', True)
    return obj

@interno
def novo(request):
    form = ChamadoForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = salvar_abertura(form, request.user, 'INTERNO')
        return redirect('pos_obra:detalhe', pk=obj.pk)
    return render(request, 'pos_obra/form_interno.html', {'form': form, 'titulo': 'Novo chamado'})

@interno
@transaction.atomic
def detalhe(request, pk):
    qs = Chamado.objects.select_for_update() if request.method == 'POST' else Chamado.objects.all()
    c = get_object_or_404(qs, pk=pk)
    forms_por_etapa = {
        'TRIAGEM': ['prioridade', 'responsavel', 'garantia', 'triagem'],
        'VISTORIA': ['data_vistoria', 'diagnostico'],
        'EXECUCAO': ['data_execucao', 'execucao', 'materiais_observacao'],
        'FINALIZACAO': ['conclusao'],
    }
    anterior = c.status
    encerrado = anterior in ('CONCLUIDO', 'CANCELADO')
    form = AtendimentoForm(request.POST if request.method == 'POST' else None, instance=c)
    etapa = request.POST.get('etapa') if request.method == 'POST' else None
    if request.method == 'POST':
        if etapa not in forms_por_etapa:
            raise PermissionDenied('Etapa inválida.')
        campos = forms_por_etapa[etapa]
        # Apenas os campos daquela etapa são editáveis e validados.
        for nome in list(form.fields):
            if nome not in campos:
                form.fields.pop(nome)
        if form.is_valid():
            novo = form.save(commit=False)
            if anterior == 'CANCELADO':
                form.add_error(None, 'Uma OS cancelada não pode ser alterada.')
            elif anterior == 'CONCLUIDO':
                form.add_error(None, 'Uma OS concluída não pode ser editada diretamente.')
            if not form.errors:
                # Etapas normais avançam automaticamente, sem regressão ao editar dados antigos.
                progressao = {'ABERTO': 0, 'REABERTO': 0, 'TRIAGEM': 1,
                              'VISTORIA': 2, 'AGUARDANDO_MATERIAL': 3,
                              'AGUARDANDO_CLIENTE': 3, 'EXECUCAO': 4,
                              'FINALIZACAO': 5}
                status_etapa = {'TRIAGEM': 'TRIAGEM', 'VISTORIA': 'VISTORIA',
                                'EXECUCAO': 'EXECUCAO', 'FINALIZACAO': 'FINALIZACAO'}[etapa]
                if progressao.get(status_etapa, 0) > progressao.get(anterior, 0):
                    novo.status = status_etapa
                campos_salvos = campos + ['atualizado_em']
                if novo.status != anterior:
                    campos_salvos.append('status')
                novo.save(update_fields=campos_salvos)
                descricao = f'{etapa.title()}: informações salvas'
                if anterior != novo.status:
                    descricao += f' · status automático: {novo.get_status_display()}'
                registro(novo, request.user, anterior, descricao, anterior != novo.status)
                messages.success(request, 'Etapa salva com sucesso. Status atualizado automaticamente.' if anterior != novo.status else 'Etapa salva com sucesso.')
                return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#' + etapa.lower())
    if form.errors:
        c.refresh_from_db()
    # Um formulário por etapa evita um único POST gigante e permite salvamentos separados.
    formulario_etapas = {}
    for chave, campos in forms_por_etapa.items():
        if chave == etapa and request.method == 'POST':
            formulario_etapas[chave] = form
        else:
            formulario_etapas[chave] = AtendimentoForm(instance=c)
            for nome in list(formulario_etapas[chave].fields):
                if nome not in campos:
                    formulario_etapas[chave].fields.pop(nome)
    return render(request, 'pos_obra/detalhe.html', {
        'chamado': c,
        'encerrado': encerrado,
        'aba_ativa': etapa.lower() if etapa else 'triagem',
        'total_materiais': sum(m.total for m in c.materiais.all()),
        'form_triagem': formulario_etapas['TRIAGEM'],
        'form_vistoria': formulario_etapas['VISTORIA'],
        'form_execucao': formulario_etapas['EXECUCAO'],
        'form_finalizacao': formulario_etapas['FINALIZACAO'],
        'materiais': c.materiais.select_related('material').all(),
        'material_form': MaterialForm(),
        'historico': Paginator(c.historico.select_related('usuario'), 25).get_page(request.GET.get('page')),
        'anexos_abertura': c.anexos.filter(etapa='ABERTURA'),
        'anexos_vistoria': c.anexos.filter(etapa='VISTORIA'),
        'anexos_execucao': c.anexos.filter(etapa='EXECUCAO'),
        'anexos_finalizacao': c.anexos.filter(etapa='FINALIZACAO'),
    })


def ultimo_preco_material(material):
    """Último preço de pedido não cancelado com vínculo inequívoco ao catálogo."""
    from compras.models import PedidoCompraItem, PedidoCompra
    item = (PedidoCompraItem.objects
            .filter(necessidade__material=material)
            .exclude(pedido__status=PedidoCompra.Status.CANCELADO)
            .select_related('pedido')
            .order_by('-pedido__data', '-pedido__criado_em', '-pk')
            .first())
    return (item.valor_unitario if item else None, item)


@interno
@require_POST
@transaction.atomic
def adicionar_material(request, pk):
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    form = MaterialForm(request.POST)
    if form.is_valid():
        material = form.cleaned_data['material']
        preco, pedido_item = ultimo_preco_material(material)
        m = MaterialOS.objects.create(
            chamado=c, material=material,
            descricao=material.descricao_completa[:255],
            unidade=material.unidade.sigla,
            previsto=form.cleaned_data['previsto'],
            utilizado=form.cleaned_data['utilizado'] or 0,
            custo_unitario=preco or 0,
            observacoes=(f'Preço de referência: {pedido_item.pedido.numero} em {pedido_item.pedido.data:%d/%m/%Y}'
                         if pedido_item else 'Preço não encontrado no histórico de pedidos; verificar manualmente.'),
        )
        anterior_material = c.status
        if c.status in ('ABERTO', 'REABERTO', 'TRIAGEM', 'VISTORIA'):
            c.status = 'AGUARDANDO_MATERIAL'
            c.save(update_fields=['status', 'atualizado_em'])
        registro(c, request.user, anterior_material, f'Material {material.codigo} incluído na OS' + (' · status automático: aguardando material' if anterior_material != c.status else ''))
        messages.success(request, 'Material adicionado a partir do catálogo de Compras.')
    else:
        messages.error(request, 'Material inválido: verifique a seleção e as quantidades.')
    return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#materiais')


@interno
@require_POST
@transaction.atomic
def finalizar_os(request, pk):
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS já encerrada.')
    if not (c.data_vistoria and c.diagnostico.strip() and c.data_execucao and c.execucao.strip() and c.conclusao.strip()):
        messages.error(request, 'Preencha vistoria, execução e relatório de conclusão antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    if not c.anexos.filter(etapa='FINALIZACAO').exists():
        messages.error(request, 'Anexe a via assinada da OS antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    if request.POST.get('confirmacao_assinatura') != 'on':
        messages.error(request, 'Confirme que a via assinada foi conferida antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    anterior = c.status
    c.status = 'CONCLUIDO'
    c.finalizado_em = timezone.now()
    c.save(update_fields=['status','finalizado_em','atualizado_em'])
    registro(c, request.user, anterior, 'OS finalizada com documento assinado anexado', True)
    messages.success(request, 'OS finalizada com sucesso.')
    return redirect('pos_obra:detalhe', pk=pk)

@interno
@require_POST
@transaction.atomic
def upload(request, pk):
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    form = AnexoForm(request.POST, request.FILES)
    if form.is_valid():
        a = AnexoChamado.objects.create(chamado=c, **form.cleaned_data)
        registro(c, request.user, c.status, f'Arquivo anexado na etapa {a.get_etapa_display()}.')
        messages.success(request, 'Arquivo anexado.')
    else:
        messages.error(request, ' '.join(error for errors in form.errors.values() for error in errors))
    aba = request.POST.get('etapa', '').lower()
    if aba not in ('vistoria', 'execucao', 'finalizacao'):
        aba = 'triagem'
    return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#' + aba)

@interno
@require_POST
@transaction.atomic
def publicar_anexo(request, pk):
    a = get_object_or_404(AnexoChamado, pk=pk)
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=a.chamado_id)
    # Compartilhamento não altera o conteúdo de uma OS encerrada.
    a.publico = request.POST.get('publico') == '1'
    a.save(update_fields=['publico'])
    registro(c, request.user, c.status, 'Visibilidade de anexo: ' + ('cliente' if a.publico else 'interno'))
    messages.success(request, 'Visibilidade do documento atualizada.')
    return redirect(reverse('pos_obra:detalhe', args=[c.pk]) + '#' + (a.etapa.lower() if a.etapa in ('VISTORIA', 'EXECUCAO', 'FINALIZACAO') else 'triagem'))

@interno
@require_POST
@transaction.atomic
def editar_material(request, pk, item_pk):
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    item = get_object_or_404(MaterialOS, pk=item_pk, chamado=c)
    if request.POST.get('acao') == 'excluir':
        descricao = item.descricao
        item.delete()
        registro(c, request.user, c.status, f'Material removido: {descricao}')
        messages.success(request, 'Material removido.')
    else:
        anterior = f'{item.previsto} / {item.utilizado}'
        form = MaterialQuantidadeForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            registro(c, request.user, c.status, f'Quantidades de {item.descricao}: {anterior} → {item.previsto} / {item.utilizado}')
            messages.success(request, 'Quantidades atualizadas; preço de referência preservado.')
        else:
            messages.error(request, 'Quantidades inválidas. Necessário deve ser maior que zero e utilizado não pode ser negativo.')
    return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#materiais')

@login_required
def ambientes(request):
    from obras.models import AmbienteFichaTecnica
    cl = cliente_do_usuario(request.user)
    if not cl and not acesso_interno(request.user):
        raise PermissionDenied
    qs = EmpreendimentoPosObra.objects.filter(liberada=True)
    if cl:
        qs = qs.filter(vinculos__cliente=cl, vinculos__ativo=True)
    raw = request.GET.get('empreendimento', '')
    if not raw.isdigit():
        return JsonResponse({'historica': None, 'ambientes': []})
    e = get_object_or_404(qs, pk=raw)
    itens = [] if e.historica else AmbienteFichaTecnica.objects.filter(
        ativo=True, pavimento__ficha__obra_id=e.obra_id).select_related('pavimento__ficha')
    clientes = [] if cl else [{'id': c.pk, 'nome': c.nome} for c in Cliente.objects.filter(
        ativo=True, vinculos__empreendimento=e, vinculos__ativo=True).order_by('nome')]
    return JsonResponse({'historica': e.historica,
                         'ambientes': [{'id': a.pk, 'nome': str(a)} for a in itens], 'clientes': clientes})

@login_required
def anexo(request,pk):
    a=get_object_or_404(AnexoChamado.objects.select_related('chamado'),pk=pk)
    cl=cliente_do_usuario(request.user)
    if cl:
        if not (a.publico and pode_acessar(cl,a.chamado)):raise PermissionDenied
    elif not acesso_interno(request.user):raise PermissionDenied
    try:
        arquivo = a.arquivo.open('rb')
    except FileNotFoundError:
        raise Http404('Arquivo não encontrado. Contate a equipe de atendimento.')
    return FileResponse(arquivo, as_attachment=True, filename=Path(a.arquivo.name).name)

def gerar_pdf(c, tipo, publico=False):
    from ..relatorios import gerar_relatorio
    return gerar_relatorio(c, tipo, publico=publico)

@interno
def relatorio(request,pk,tipo):return gerar_pdf(get_object_or_404(Chamado,pk=pk),tipo)
@cliente
def portal(request):
    cl = cliente_do_usuario(request.user)
    qs = Chamado.objects.filter(cliente=cl, empreendimento__vinculos__cliente=cl,
        empreendimento__vinculos__ativo=True).select_related('tipo_problema', 'empreendimento__obra').distinct().order_by('-criado_em', '-pk')
    return render(request, 'pos_obra/portal.html', {
        'cliente': cl, 'total_chamados': qs.count(),
        'em_andamento': qs.exclude(status__in=['CONCLUIDO', 'CANCELADO']).count(),
        'chamados': Paginator(qs, 15).get_page(request.GET.get('page')),
        'imoveis': EmpreendimentoPosObra.objects.filter(vinculos__cliente=cl, vinculos__ativo=True, liberada=True).select_related('obra'),
    })

@cliente
def portal_novo(request):
    cl = cliente_do_usuario(request.user)
    dados = request.POST.copy() if request.method == 'POST' else None
    if dados is not None:
        dados['cliente'] = str(cl.pk)
    form = ChamadoForm(dados, request.FILES or None, cliente_portal=cl)
    if request.method == 'POST' and form.is_valid():
        obj = salvar_abertura(form, request.user, 'PORTAL')
        return redirect('pos_obra:portal_detalhe', pk=obj.pk)
    return render(request, 'pos_obra/form.html', {'titulo': 'Nova solicitação', 'form': form})

@cliente
def portal_detalhe(request,pk):
    c=get_object_or_404(Chamado.objects.select_related('empreendimento__obra','tipo_problema'),pk=pk)
    if not pode_acessar(cliente_do_usuario(request.user),c):raise PermissionDenied
    return render(request,'pos_obra/portal_detalhe.html',{'chamado':c,'historico':c.historico.filter(publico=True),'pesquisa':PesquisaSatisfacao.objects.filter(chamado=c).first(),'anexos':c.anexos.filter(publico=True)})
@cliente
def portal_pdf(request,pk,tipo):
    c=get_object_or_404(Chamado,pk=pk)
    if not pode_acessar(cliente_do_usuario(request.user),c):raise PermissionDenied
    if c.status!='CONCLUIDO':raise PermissionDenied('Documento ainda não autorizado.')
    return gerar_pdf(c,tipo,publico=True)
@cliente
@transaction.atomic
def responder_pesquisa(request,pk):
    c=get_object_or_404(Chamado.objects.select_for_update(),pk=pk)
    if not pode_acessar(cliente_do_usuario(request.user),c) or c.status!='CONCLUIDO':raise PermissionDenied
    if PesquisaSatisfacao.objects.filter(chamado=c).exists():return redirect('pos_obra:portal_detalhe',pk=pk)
    f=PesquisaForm(request.POST or None)
    if request.method=='POST' and f.is_valid():
        p=f.save(commit=False)
        if not all(1<=getattr(p,key)<=5 for key in ('atendimento','prazo','qualidade')):raise PermissionDenied
        p.chamado=c;p.save()
        if p.resolvido=='NAO':registro(c,request.user,c.status,'Cliente sinalizou problema não resolvido',False)
        return redirect('pos_obra:portal_detalhe',pk=pk)
    return render(request,'pos_obra/form.html',{'form':f,'titulo':'Pesquisa de satisfação','eh_pesquisa':True})
# Links legados movidos para Cadastros
@interno
def cadastros(request,modelo):return redirect('cadastros:pos_obra_lista',modelo=modelo)
@interno
def cadastrar(request,modelo,pk=None):return redirect('cadastros:pos_obra_editar',modelo=modelo,pk=pk) if pk else redirect('cadastros:pos_obra_novo',modelo=modelo)
@interno
def obra_historica(request):return redirect('cadastros:pos_obra_novo',modelo='empreendimentos')
