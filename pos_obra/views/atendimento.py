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
from ..services.notificacoes import enfileirar
from ..forms import AgendamentoForm,ChamadoForm,AtendimentoForm,MaterialForm,PesquisaForm,MaterialQuantidadeForm,AnexoForm
from ..access import interno,cliente,cliente_do_usuario,pode_acessar,acesso_interno
from usuarios.decorators import possui_permissao_acao
from usuarios.models import ModuloSistema

@interno
def painel(request):
    qs=Chamado.objects.all()
    return render(request,'pos_obra/painel.html',{'total':qs.count(),'abertos':qs.exclude(status__in=['CONCLUIDO','CANCELADO']).count(),'concluidos':qs.filter(status='CONCLUIDO').count(),'satisfacao':PesquisaSatisfacao.objects.aggregate(x=Avg('atendimento'))['x'],'compromissos':AgendamentoOS.objects.select_related('chamado__cliente','responsavel').filter(fim__gte=timezone.now(),situacao__in=['PROPOSTO','CONFIRMADO','REAGENDAMENTO']).exclude(chamado__status__in=['CONCLUIDO','CANCELADO']).order_by('inicio')[:6], 'chamados':qs.select_related('cliente','empreendimento__obra').order_by('-criado_em')[:12]})
def filtros_chamados(request, qs):
    for name in ('status', 'prioridade'):
        if request.GET.get(name):
            permitidos = dict(Chamado.STATUS if name == 'status' else Chamado.PRIORIDADES)
            if request.GET[name] in permitidos:
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
    ordenacoes={'recentes':'-criado_em','antigas':'criado_em','cliente':'cliente__nome','obra':'empreendimento__nome_historico'}
    ordenacao=request.GET.get('ordem','recentes')
    qs=qs.order_by(ordenacoes.get(ordenacao,'-criado_em'),'-pk')
    return render(request, 'pos_obra/lista.html', {
        'ordenacao':ordenacao,
        'chamados': Paginator(qs, 25).get_page(request.GET.get('page')),
        'status_choices': Chamado.STATUS, 'prioridade_choices': Chamado.PRIORIDADES,
        'status_atual': request.GET.get('status', ''), 'pagina_query': pagina_contexto(request)})

@interno
def kanban(request):
    qs = filtros_chamados(request, Chamado.objects.select_related(
        'cliente', 'empreendimento__obra', 'tipo_problema', 'responsavel')).order_by('-criado_em', '-pk')
    contagens = dict(qs.values('status').annotate(total=Count('pk')).values_list('status', 'total'))
    grupos = [{'codigo': key, 'nome': label, 'total': contagens.get(key, 0),
               'itens': list(qs.filter(status=key)[:30])} for key, label in Chamado.STATUS]
    return render(request, 'pos_obra/kanban.html', {'grupos': grupos, 'filtros_query': pagina_contexto(request), 'prioridade_choices': Chamado.PRIORIDADES})


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
        enfileirar(obj,'ABERTURA',obj.pk,f'SAARI | Chamado {obj.numero} recebido',f'Sua solicitação {obj.numero} foi registrada. Acompanhe pelo portal SAARI.')
    return obj

@interno
def novo(request):
    if request.method == 'POST' and not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'abrir_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    form = ChamadoForm(request.POST if request.method == 'POST' else None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = salvar_abertura(form, request.user, 'INTERNO')
        return redirect('pos_obra:detalhe', pk=obj.pk)
    return render(request, 'pos_obra/form_interno.html', {'form': form, 'titulo': 'Novo chamado'})



def etapa_pendente(c):
    """Primeira etapa incompleta; materiais são opcionais."""
    if not (c.triagem or '').strip() or not c.responsavel_id:
        return 'TRIAGEM'
    if not c.data_vistoria or not (c.diagnostico or '').strip():
        return 'VISTORIA'
    if not c.data_execucao or not (c.execucao or '').strip():
        return 'EXECUCAO'
    if not (c.conclusao or '').strip():
        return 'FINALIZACAO'
    return None


def pode_etapa(c, etapa):
    ordem = ('TRIAGEM', 'VISTORIA', 'EXECUCAO', 'FINALIZACAO')
    pendente = etapa_pendente(c)
    return etapa in ordem and (pendente is None or ordem.index(etapa) <= ordem.index(pendente))

@interno
@transaction.atomic
def detalhe(request, pk):
    if request.method == 'POST' and not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'editar_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
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
        # Rascunho persistente: aceita dados parciais, sem avançar status nem modificar a OS.
        if request.POST.get('acao_etapa') == 'rascunho' and etapa in forms_por_etapa:
            if encerrado or not pode_etapa(c, etapa):
                raise PermissionDenied('Não é possível salvar rascunho desta etapa.')
            if etapa == 'TRIAGEM' and not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'atribuir_responsavel'):
                raise PermissionDenied('Permissão insuficiente para triagem.')
            if etapa == 'TRIAGEM' and c.responsavel_id and (c.triagem or '').strip() or (etapa == 'VISTORIA' and c.data_vistoria and c.diagnostico.strip()) or (etapa == 'EXECUCAO' and c.data_execucao and c.execucao.strip()) or (etapa == 'FINALIZACAO' and c.conclusao.strip()):
                raise PermissionDenied('Etapa concluída não admite novos rascunhos.')
            dados = {nome: request.POST.get(nome, '') for nome in forms_por_etapa[etapa] if nome in request.POST}
            RascunhoEtapaOS.objects.update_or_create(chamado=c, etapa=etapa, defaults={'dados': dados, 'atualizado_por': request.user})
            messages.success(request, 'Rascunho salvo. A etapa continua aberta e o status não foi alterado.')
            return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#' + etapa.lower())
        if etapa not in forms_por_etapa:
            raise PermissionDenied('Etapa inválida.')
        if etapa == 'TRIAGEM' and 'responsavel' in request.POST and not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'atribuir_responsavel'):
            raise PermissionDenied('Você não pode atribuir responsáveis.')
        campos = forms_por_etapa[etapa]
        # Apenas os campos daquela etapa são editáveis e validados.
        for nome in list(form.fields):
            if nome not in campos:
                form.fields.pop(nome)
        # Bloqueia alteração das etapas já preenchidas (a correção exige fluxo específico auditado).
        concluida = {
            'TRIAGEM': bool(c.responsavel_id and (c.triagem or '').strip()),
            'VISTORIA': bool(c.data_vistoria and (c.diagnostico or '').strip()),
            'EXECUCAO': bool(c.data_execucao and (c.execucao or '').strip()),
            'FINALIZACAO': bool((c.conclusao or '').strip()),
        }.get(etapa, False)
        if concluida:
            form.add_error(None, 'Esta etapa já foi concluída e está bloqueada para edição. Solicite uma correção administrativa auditada.')
        if not pode_etapa(c, etapa):
            form.add_error(None, 'Conclua a etapa anterior antes de preencher esta etapa.')
        if form.is_valid() and not form.errors:
            novo = form.save(commit=False)
            if anterior == 'CANCELADO':
                form.add_error(None, 'Uma OS cancelada não pode ser alterada.')
            elif anterior == 'CONCLUIDO':
                form.add_error(None, 'Uma OS concluída não pode ser editada diretamente.')
            if not form.errors:
                if etapa == 'TRIAGEM' and (not novo.responsavel_id or not (novo.triagem or '').strip()):
                    form.add_error(None, 'Informe o responsável e o parecer da triagem.')
                if etapa == 'VISTORIA' and not (novo.data_vistoria and (novo.diagnostico or '').strip()):
                    form.add_error(None, 'Preencha a data e o diagnóstico da vistoria.')
                if etapa == 'EXECUCAO' and not (novo.data_execucao and (novo.execucao or '').strip()):
                    form.add_error(None, 'Preencha a data e os serviços executados.')
                if etapa == 'FINALIZACAO' and not (novo.conclusao or '').strip():
                    form.add_error(None, 'Preencha o parecer de conclusão.')
                # Impede avançar uma etapa sem evidência das anteriores.
                if etapa in ('EXECUCAO', 'FINALIZACAO') and not (novo.data_vistoria and (novo.diagnostico or '').strip()):
                    form.add_error(None, 'Registre a data e o diagnóstico da vistoria antes de avançar.')
                if etapa == 'FINALIZACAO' and not (novo.data_execucao and (novo.execucao or '').strip()):
                    form.add_error(None, 'Registre a data e o relatório da execução antes de finalizar.')
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
                RascunhoEtapaOS.objects.filter(chamado=novo, etapa=etapa).delete()
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
            formulario_etapas[chave] = AtendimentoForm(instance=c, auto_id=chave.lower()+'-%s')
            for nome in list(formulario_etapas[chave].fields):
                if nome not in campos:
                    formulario_etapas[chave].fields.pop(nome)
    rascunhos = {r.etapa: r for r in RascunhoEtapaOS.objects.filter(chamado=c)}
    for chave, formulario in formulario_etapas.items():
        if chave in rascunhos and not (request.method == 'POST' and etapa == chave):
            for campo, valor in rascunhos[chave].dados.items():
                if campo in formulario.fields:
                    formulario.initial[campo] = valor
    contexto = _contexto_detalhe(request,c,formulario_etapas,etapa,encerrado)
    contexto['rascunhos_etapas'] = rascunhos
    return render(request, 'pos_obra/detalhe.html', contexto)

def _contexto_detalhe(request, c, formulario_etapas, etapa=None, encerrado=False):
    from ..presentation import etapas_apresentacao, proximo_compromisso
    materiais=list(c.materiais.select_related('material'))
    agendamentos=list(c.agendamentos.select_related('responsavel'))
    form_agendamento=AgendamentoForm()
    responsaveis=list(form_agendamento.fields['responsavel'].choices)
    form_agendamento.fields['responsavel'].choices=responsaveis
    for a in agendamentos:
        a.form_reagendamento=AgendamentoForm(auto_id=f'reagendar-{a.pk}-%s')
        a.form_reagendamento.fields['responsavel'].choices=responsaveis
    contexto = {
        'chamado': c,
        'encerrado': encerrado,
        'etapa_pendente': etapa_pendente(c),
        'libera_vistoria': pode_etapa(c, 'VISTORIA'),
        'libera_materiais': pode_etapa(c, 'EXECUCAO'),
        'libera_execucao': pode_etapa(c, 'EXECUCAO'),
        'libera_finalizacao': pode_etapa(c, 'FINALIZACAO'),
        'aba_ativa': etapa.lower() if etapa else (etapa_pendente(c) or 'documentos').lower(),
        'total_materiais': sum(m.total for m in materiais),
        'total_estimado': sum(m.total_estimado for m in materiais),
        'form_triagem': formulario_etapas['TRIAGEM'],
        'form_vistoria': formulario_etapas['VISTORIA'],
        'form_execucao': formulario_etapas['EXECUCAO'],
        'form_finalizacao': formulario_etapas['FINALIZACAO'],
        'materiais': materiais,
        'material_form': MaterialForm(),
        'historico': Paginator(c.historico.select_related('usuario'), 25).get_page(request.GET.get('page')),
        'anexos_abertura': c.anexos.filter(etapa='ABERTURA'),
        'anexos_vistoria': c.anexos.filter(etapa='VISTORIA'),
        'anexos_execucao': c.anexos.filter(etapa='EXECUCAO'),
        'anexos_finalizacao': c.anexos.filter(etapa='FINALIZACAO'),
        'agendamentos': agendamentos,
        'form_agendamento': form_agendamento,
        'documentos': c.documentos_versionados.select_related('aceite').order_by('-criado_em', '-pk'),
        
        'aceite_valido': aceite_valido(c),
    }
    contexto.update({
        'concluida_triagem': bool(c.responsavel_id and c.triagem.strip()),
        'concluida_vistoria': bool(c.data_vistoria and c.diagnostico.strip()),
        'concluida_execucao': bool(c.data_execucao and c.execucao.strip()),
        'concluida_finalizacao': bool(c.conclusao.strip()),
    })
    contexto['pode_editar']=possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia')
    contexto['pode_finalizar']=possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'concluir_ocorrencia')
    contexto['pode_atribuir']=possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'atribuir_responsavel')
    contexto['pesquisa']=PesquisaSatisfacao.objects.filter(chamado=c).first()
    contexto['tratativas']=c.tratativas_satisfacao.select_related('responsavel')
    contexto['proximo_agendamento']=proximo_compromisso(agendamentos)
    contexto['etapas_ui']=etapas_apresentacao(c,contexto)
    contexto['proxima_acao_ui']={'TRIAGEM':'Definir responsável e registrar o parecer de triagem.','VISTORIA':'Registrar a data e o diagnóstico da vistoria.','EXECUCAO':'Registrar a data e os serviços executados.','FINALIZACAO':'Salvar o parecer de conclusão e conferir o aceite.'}.get(etapa_pendente(c),'Conferir o aceite e encerrar a ordem de serviço.')
    contexto['tem_via_assinada']=c.anexos.filter(etapa='FINALIZACAO',via_assinada_conferida=True).exists()
    contexto['pronto_finalizar']=not encerrado and contexto['concluida_triagem'] and contexto['concluida_vistoria'] and contexto['concluida_execucao'] and contexto['concluida_finalizacao'] and (contexto['aceite_valido'] or contexto['tem_via_assinada'])
    documentos=list(contexto['documentos']);vistos=set();limite=ultima_alteracao_tecnica(c)
    for doc in documentos:
        doc.elegivel_aceite=not encerrado and contexto['pode_editar'] and doc.tipo not in vistos and doc.criado_em>=limite and not hasattr(doc,'aceite')
        doc.desatualizado=doc.criado_em<limite
        vistos.add(doc.tipo)
    contexto['documentos']=documentos
    for etapa_form,campos in {'TRIAGEM':['responsavel','triagem'],'VISTORIA':['data_vistoria','diagnostico'],'EXECUCAO':['data_execucao','execucao'],'FINALIZACAO':['conclusao']}.items():
        for campo in campos:
            if campo in formulario_etapas[etapa_form].fields:
                formulario_etapas[etapa_form].fields[campo].required=True
    return contexto


def _erro_operacao(request, c, chave, form, aba, reagendamento_id=None):
    grupos={'TRIAGEM':['prioridade','responsavel','garantia','triagem'], 'VISTORIA':['data_vistoria','diagnostico'], 'EXECUCAO':['data_execucao','execucao','materiais_observacao'], 'FINALIZACAO':['conclusao']}
    forms={}
    for etapa, campos in grupos.items():
        f=AtendimentoForm(instance=c, auto_id=etapa.lower()+'-%s')
        f.fields={n:field for n,field in f.fields.items() if n in campos}
        forms[etapa]=f
    contexto=_contexto_detalhe(request,c,forms,encerrado=c.status in ('CONCLUIDO','CANCELADO'))
    contexto.update({chave:form,'aba_ativa':aba})
    if reagendamento_id:
        for agendamento in contexto['agendamentos']:
            if agendamento.pk == reagendamento_id:
                agendamento.form_reagendamento=form
    return render(request,'pos_obra/detalhe.html',contexto)



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
    if not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'editar_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    if not pode_etapa(c, 'EXECUCAO'):
        messages.error(request, 'Conclua a triagem e a vistoria antes de registrar materiais.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#vistoria')
    form = MaterialForm(request.POST)
    if form.is_valid():
        material = form.cleaned_data['material']
        preco, pedido_item = ultimo_preco_material(material)
        m = MaterialOS.objects.create(
            chamado=c, material=material,
            descricao=(material.especificacao or material.nome)[:255],
            unidade=material.unidade.sigla,
            previsto=form.cleaned_data['previsto'],
            utilizado=0,  # reservado para integração de consumo real do almoxarifado
            custo_unitario=preco or 0,
            observacoes=(f'Preço de referência: {pedido_item.pedido.numero} em {pedido_item.pedido.data:%d/%m/%Y}'
                         if pedido_item else 'Preço não encontrado no histórico de pedidos; verificar manualmente.'),
        )
        anterior_material = c.status
        # Planejar materiais não significa que exista pendência de compra/entrega.
        registro(c, request.user, anterior_material, f'Material {material.codigo} incluído na previsão da OS')
        messages.success(request, 'Material adicionado a partir do catálogo de Compras.')
    else:
        return _erro_operacao(request,c,'material_form',form,'materiais')
    return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#materiais')


def ultima_alteracao_tecnica(c):
    # Conclusão administrativa não invalida relatório de execução já assinado.
    from datetime import datetime, timezone as dt_timezone
    registro=c.historico.filter(Q(mensagem__istartswith='Execucao:') | Q(mensagem__istartswith='Vistoria:') | Q(mensagem__startswith='Quantidade necessária de') | Q(mensagem__startswith='Quantidades de') | Q(mensagem__startswith='Material ')).order_by('-criado_em').first()
    datas=[registro.criado_em if registro else timezone.make_aware(datetime(2000,1,1))]
    anexo=c.anexos.exclude(etapa__in=['FINALIZACAO','TRIAGEM']).order_by('-criado_em').first()
    if anexo:datas.append(anexo.criado_em)
    visibilidade=c.historico.filter(mensagem__startswith='Visibilidade de evidência técnica:').order_by('-criado_em').first()
    if visibilidade:datas.append(visibilidade.criado_em)
    return max(datas)

def latest_document_version(c):
    return c.documentos_versionados.filter(tipo='EXECUCAO').order_by('-versao').values_list('versao',flat=True).first() or 0

def aceite_valido(c):
    limite=ultima_alteracao_tecnica(c)
    for tipo in ('EXECUCAO','OS'):
        doc=c.documentos_versionados.filter(tipo=tipo).order_by('-versao').first()
        if doc and doc.criado_em >= limite and AceiteOS.objects.filter(documento=doc,resultado__in=['ACEITO','RESSALVA']).exists():
            return True
    return False


@interno
@require_POST
@transaction.atomic
def finalizar_os(request, pk):
    if not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'concluir_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS já encerrada.')
    if etapa_pendente(c) is not None:
        messages.error(request, 'Preencha vistoria, execução e relatório de conclusão antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    if not (c.anexos.filter(etapa='FINALIZACAO',via_assinada_conferida=True).exists() or aceite_valido(c)):
        messages.error(request, 'Registre o aceite eletrônico ou anexe a via assinada antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    if request.POST.get('confirmacao_assinatura') != 'on':
        messages.error(request, 'Confirme que a via assinada foi conferida antes de finalizar.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
    anterior = c.status
    c.status = 'CONCLUIDO'
    c.finalizado_em = timezone.now()
    c.save(update_fields=['status','finalizado_em','atualizado_em'])
    registro(c, request.user, anterior, 'OS finalizada com documento assinado anexado', True)
    enfileirar(c,'CONCLUSAO',c.pk,f'SAARI | Chamado {c.numero} concluído',f'O atendimento da OS {c.numero} foi concluído. Seus documentos e pesquisa de satisfação estão disponíveis no portal.')
    enfileirar(c,'PESQUISA',c.pk,f'SAARI | Avalie o atendimento {c.numero}',f'Sua avaliação da OS {c.numero} está disponível no portal do cliente.')
    messages.success(request, 'OS finalizada com sucesso.')
    return redirect('pos_obra:detalhe', pk=pk)

@interno
@require_POST
@transaction.atomic
def upload(request, pk):
    if not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'editar_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    etapa_anexo = request.POST.get('etapa', '').upper()
    if etapa_anexo in ('VISTORIA', 'EXECUCAO', 'FINALIZACAO') and not pode_etapa(c, etapa_anexo):
        messages.error(request, 'Conclua a etapa anterior antes de anexar documentos desta etapa.')
        return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#' + etapa_pendente(c).lower())
    form = AnexoForm(request.POST, request.FILES)
    if form.is_valid():
        dados_anexo = form.cleaned_data.copy()
        if etapa_anexo != 'FINALIZACAO':
            dados_anexo['via_assinada_conferida'] = False
        if etapa_anexo == 'FINALIZACAO' and not dados_anexo['via_assinada_conferida']:
            messages.error(request, 'Para anexar via física de aceite, confirme que o documento está assinado e foi conferido.')
            return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#finalizacao')
        a = AnexoChamado.objects.create(chamado=c, **dados_anexo)
        registro(c, request.user, c.status, f'Arquivo anexado na etapa {a.get_etapa_display()}.')
        messages.success(request, 'Arquivo anexado.')
    else:
        messages.error(request, ' '.join(error for errors in form.errors.values() for error in errors))
        aba=etapa_anexo.lower() if etapa_anexo in ('ABERTURA','VISTORIA','EXECUCAO','FINALIZACAO') else 'abertura'
        return _erro_operacao(request,c,'upload_form',form,aba)
    aba = request.POST.get('etapa', '').lower()
    if aba not in ('vistoria', 'execucao', 'finalizacao'):
        aba = 'triagem'
    return redirect(reverse('pos_obra:detalhe', args=[pk]) + '#' + aba)

@interno
@require_POST
@transaction.atomic
def publicar_anexo(request, pk):
    if not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'editar_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    a = get_object_or_404(AnexoChamado, pk=pk)
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=a.chamado_id)
    # Compartilhamento não altera o conteúdo de uma OS encerrada.
    a.publico = request.POST.get('publico') == '1'
    a.save(update_fields=['publico'])
    prefixo='Visibilidade de evidência técnica: ' if a.etapa in ('ABERTURA','VISTORIA','EXECUCAO') else 'Visibilidade de anexo: '
    registro(c, request.user, c.status, prefixo + ('cliente' if a.publico else 'interno'))
    messages.success(request, 'Visibilidade do documento atualizada.')
    return redirect(reverse('pos_obra:detalhe', args=[c.pk]) + '#' + (a.etapa.lower() if a.etapa in ('VISTORIA', 'EXECUCAO', 'FINALIZACAO') else 'triagem'))

@interno
@require_POST
@transaction.atomic
def editar_material(request, pk, item_pk):
    if not possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'editar_ocorrencia'):
        raise PermissionDenied('Permissão insuficiente para esta operação no Pós-obra.')
    c = get_object_or_404(Chamado.objects.select_for_update(), pk=pk)
    if c.status in ('CONCLUIDO', 'CANCELADO'):
        raise PermissionDenied('OS encerrada.')
    if not pode_etapa(c, 'EXECUCAO'):
        raise PermissionDenied('Conclua a vistoria antes de alterar materiais.')
    item = get_object_or_404(MaterialOS, pk=item_pk, chamado=c)
    if request.POST.get('acao') == 'excluir':
        descricao = item.descricao
        item.delete()
        registro(c, request.user, c.status, f'Material removido: {descricao}')
        messages.success(request, 'Material removido.')
    else:
        anterior = str(item.previsto)
        form = MaterialQuantidadeForm(request.POST, instance=item, auto_id=f'material-{item.pk}-%s')
        if form.is_valid():
            form.save()
            registro(c, request.user, c.status, f'Quantidade necessária de {item.descricao}: {anterior} → {item.previsto}')
            messages.success(request, 'Quantidades atualizadas; preço de referência preservado.')
        else:
            return _erro_operacao(request,c,'material_quantidade_form',form,'materiais')
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
    elif not (acesso_interno(request.user) and possui_permissao_acao(request.user, ModuloSistema.POS_OBRA, 'visualizar')):raise PermissionDenied
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
    return render(request,'pos_obra/portal_detalhe.html',{'chamado':c,'historico':c.historico.filter(publico=True),'agendamentos':c.agendamentos.all(),'pesquisa':PesquisaSatisfacao.objects.filter(chamado=c).first(),'anexos':c.anexos.filter(publico=True)})
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
        if p.resolvido=='NAO' or min(p.atendimento,p.prazo,p.qualidade)<=2:registro(c,request.user,c.status,'Avaliação crítica do cliente — requer tratativa administrativa',False)
        return redirect('pos_obra:portal_detalhe',pk=pk)
    return render(request,'pos_obra/form.html',{'form':f,'titulo':'Pesquisa de satisfação','eh_pesquisa':True})
# Links legados movidos para Cadastros
@interno
def cadastros(request,modelo):
    if modelo not in ('categorias','problemas'):
        if request.method not in ('GET','HEAD'):raise PermissionDenied
        return redirect('usuarios:lista_usuarios' if modelo in ('clientes','vinculos') else 'cadastros:pos_obra_lista', **({} if modelo in ('clientes','vinculos') else {'modelo':modelo}))
    Model=CategoriaOcorrencia if modelo=='categorias' else TipoProblema
    qs=Model.objects.all()
    if modelo=='problemas':qs=qs.select_related('categoria')
    termo=request.GET.get('q','').strip()
    if termo:qs=qs.filter(nome__icontains=termo)
    return render(request,'pos_obra/cadastros.html',{'modelo':modelo,'itens':Paginator(qs.order_by('nome'),25).get_page(request.GET.get('page')),'pagina_query':pagina_contexto(request)})
@interno
def cadastrar(request,modelo,pk=None):
    if modelo in ('clientes','vinculos'):
        if request.method not in ('GET','HEAD'):raise PermissionDenied('Use Usuários para manter clientes e vínculos.')
        return redirect('usuarios:lista_usuarios')
    if modelo not in ('categorias','problemas'):
        if request.method not in ('GET','HEAD'):raise PermissionDenied
        return redirect('cadastros:pos_obra_editar',modelo=modelo,pk=pk) if pk else redirect('cadastros:pos_obra_novo',modelo=modelo)
    from ..forms import CategoriaForm,TipoProblemaForm
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    F=CategoriaForm if modelo=='categorias' else TipoProblemaForm
    obj=get_object_or_404(F._meta.model,pk=pk) if pk else None
    form=F(request.POST if request.method=='POST' else None,instance=obj)
    if request.method=='POST' and form.is_valid():
        form.save();messages.success(request,'Catálogo atualizado.')
        return redirect('pos_obra:cadastros',modelo=modelo)
    return render(request,'pos_obra/catalogo_form.html',{'form':form,'modelo':modelo})
@interno
def obra_historica(request):return redirect('cadastros:pos_obra_novo',modelo='empreendimentos')


@interno
@require_POST
@transaction.atomic
def agendar(request,pk):
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    c=get_object_or_404(Chamado.objects.select_for_update(),pk=pk)
    if c.status in ('CANCELADO','CONCLUIDO'):raise PermissionDenied('OS encerrada.')
    from django.contrib.auth import get_user_model
    responsavel_id=request.POST.get('responsavel','')
    if responsavel_id.isdigit():
        get_user_model().objects.select_for_update().filter(pk=responsavel_id).first()
    f=AgendamentoForm(request.POST)
    if f.is_valid():
        a=f.save(commit=False);a.chamado=c;a.criado_por=request.user;a.save()
        HistoricoAgendamento.objects.create(agendamento=a,usuario=request.user,para=a.situacao,observacao='Proposta criada')
        registro(c,request.user,c.status,'Proposta de agendamento cadastrada',True)
        enfileirar(c,'AGENDAMENTO',a.pk,f'SAARI | Confirme seu atendimento {c.numero}',f'Nova proposta de {a.get_tipo_display()} para {timezone.localtime(a.inicio):%d/%m/%Y %H:%M}. Confirme ou solicite reagendamento pelo portal.')
        messages.success(request,'Proposta registrada. Aguarda confirmação do cliente pelo portal.')
    else:
        return _erro_operacao(request,c,'form_agendamento',f,'agendamentos')
    return redirect(reverse('pos_obra:detalhe',args=[pk])+'#agendamentos')

@cliente
@require_POST
@transaction.atomic
def responder_agendamento(request,pk):
    a=get_object_or_404(AgendamentoOS.objects.select_for_update().select_related('chamado'),pk=pk)
    if not pode_acessar(cliente_do_usuario(request.user),a.chamado):raise PermissionDenied
    if a.chamado.status in ('CONCLUIDO','CANCELADO'):raise PermissionDenied('OS encerrada.')
    if a.situacao!='PROPOSTO':raise PermissionDenied('A proposta não está disponível.')
    resposta=request.POST.get('resposta')
    if resposta not in ('CONFIRMADO','REAGENDAMENTO'):raise PermissionDenied('Resposta inválida.')
    a.situacao=resposta;a.confirmado_em=timezone.now() if resposta=='CONFIRMADO' else None
    a.respondido_por=request.user;a.save(update_fields=['situacao','confirmado_em','respondido_por'])
    HistoricoAgendamento.objects.create(agendamento=a,usuario=request.user,de='PROPOSTO',para=resposta,observacao=request.POST.get('observacao','')[:2000])
    registro(a.chamado,request.user,a.chamado.status,'Cliente respondeu ao agendamento',True)
    enfileirar(a.chamado,'RESPOSTA_AGENDAMENTO',f'{a.pk}:{resposta}',f'SAARI | Resposta ao agendamento {a.chamado.numero}',f'Sua resposta ao agendamento foi registrada: {a.get_situacao_display()}.')
    return redirect('pos_obra:portal_detalhe',pk=a.chamado_id)

@interno
@require_POST
@transaction.atomic
def emitir_documento(request,pk):
    import hashlib
    from django.core.files.base import ContentFile
    from ..relatorios import gerar_relatorio
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    c=get_object_or_404(Chamado.objects.select_for_update(),pk=pk)
    if c.status in ('CONCLUIDO','CANCELADO') or not(c.data_execucao and (c.execucao or '').strip()):
        raise PermissionDenied('Registre a execução antes de emitir uma versão assinável.')
    tipo=request.POST.get('tipo','EXECUCAO')
    if tipo not in ('EXECUCAO','OS'):raise PermissionDenied
    response=gerar_relatorio(c,tipo.lower(),publico=True)
    conteudo=response.content
    anterior=c.documentos_versionados.filter(tipo=tipo).order_by('-versao').first()
    versao=anterior.versao+1 if anterior else 1
    doc=DocumentoOS(chamado=c,tipo=tipo,versao=versao,sha256=hashlib.sha256(conteudo).hexdigest(),criado_por=request.user)
    doc.arquivo.save(f'{c.numero}-{tipo}-v{versao}.pdf',ContentFile(conteudo),save=False)
    doc.save()
    registro(c,request.user,c.status,f'Documento {tipo} v{versao} emitido; SHA-256 {doc.sha256}')
    messages.success(request,'Versão imutável do documento emitida. Confira antes de solicitar assinatura.')
    return redirect(reverse('pos_obra:detalhe',args=[pk])+'#documentos')

@login_required
def baixar_documento(request,pk):
    doc=get_object_or_404(DocumentoOS.objects.select_related('chamado'),pk=pk)
    cliente_atual=cliente_do_usuario(request.user)
    if cliente_atual:
        if not pode_acessar(cliente_atual,doc.chamado) or not hasattr(doc,'aceite'):raise PermissionDenied
    elif not (acesso_interno(request.user) and possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'visualizar')):
        raise PermissionDenied
    return FileResponse(doc.arquivo.open('rb'),content_type='application/pdf',as_attachment=False,filename=f'{doc.chamado.numero}-{doc.tipo}-v{doc.versao}.pdf')

@interno
@require_POST
@transaction.atomic
def registrar_aceite(request,pk):
    import base64
    from django.core.files.base import ContentFile
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    doc=get_object_or_404(DocumentoOS,pk=pk)
    c=get_object_or_404(Chamado.objects.select_for_update(),pk=doc.chamado_id)
    doc=get_object_or_404(DocumentoOS.objects.select_for_update().select_related('chamado'),pk=pk)
    if doc.criado_em < ultima_alteracao_tecnica(c):raise PermissionDenied('O documento está desatualizado. Emita uma nova versão.')
    if doc.chamado.status in ('CONCLUIDO','CANCELADO') or doc.versao != (doc.chamado.documentos_versionados.filter(tipo=doc.tipo).order_by('-versao').values_list('versao',flat=True).first()) or AceiteOS.objects.filter(documento=doc).exists():raise PermissionDenied
    nome=request.POST.get('signatario','').strip()[:180]
    vinculo=request.POST.get('representacao','').strip()[:180]
    resultado=request.POST.get('resultado')
    if not nome or not vinculo or resultado not in ('ACEITO','RECUSADO','RESSALVA'):raise PermissionDenied('Dados de aceite incompletos.')
    if request.POST.get('ciencia') != 'on':raise PermissionDenied('É necessário registrar a ciência do conteúdo apresentado.')
    raw=request.POST.get('assinatura','')
    if resultado in ('ACEITO','RESSALVA'):
        if len(raw)>700_000 or not raw.startswith('data:image/png;base64,'):raise PermissionDenied('Assinatura não informada ou muito grande.')
        try: dados=base64.b64decode(raw.split(',',1)[1],validate=True)
        except (ValueError,base64.binascii.Error):raise PermissionDenied('Assinatura inválida.')
        if len(dados)>500_000 or not dados.startswith(b'\x89PNG\r\n\x1a\n'):raise PermissionDenied('Imagem da assinatura inválida.')
        from io import BytesIO
        from PIL import Image
        try:
            with Image.open(BytesIO(dados)) as imagem:
                if imagem.format!='PNG' or imagem.width*imagem.height>4_000_000:
                    raise ValueError('Dimensões inválidas')
                imagem.verify()
        except (OSError,ValueError,Image.DecompressionBombError):
            raise PermissionDenied('Imagem da assinatura inválida.')
    a=AceiteOS(documento=doc,signatario=nome,representacao=vinculo,resultado=resultado,observacoes=request.POST.get('observacoes','')[:4000],usuario_registro=request.user)
    if resultado in ('ACEITO','RESSALVA'):
        a.assinatura.save(f'assinatura-os-{doc.chamado_id}-v{doc.versao}.png',ContentFile(dados),save=False)
    a.save()
    registro(doc.chamado,request.user,doc.chamado.status,f'Aceite {resultado} do documento {doc.tipo} v{doc.versao} registrado; signatário: {nome}')
    messages.success(request,'Resposta vinculada à versão do documento.')
    return redirect(reverse('pos_obra:detalhe',args=[doc.chamado_id])+'#documentos')


@interno
def agenda(request):
    from datetime import datetime, timedelta
    from django.utils.dateparse import parse_date
    try:
        base=parse_date(request.GET.get('data','')) or timezone.localdate()
    except ValueError:
        base=timezone.localdate()
        messages.warning(request, 'Data inválida. Exibindo o período atual.')
    modo=request.GET.get('modo','semana')
    if modo=='dia':inicio=fim=base
    elif modo=='mes':inicio=base.replace(day=1);fim=(inicio.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    else:inicio=base-timedelta(days=base.weekday());fim=inicio+timedelta(days=6);modo='semana'
    qs=AgendamentoOS.objects.select_related('chamado__cliente','chamado__empreendimento__obra','responsavel').filter(inicio__date__gte=inicio,inicio__date__lte=fim).order_by('inicio')
    estado=request.GET.get('situacao','');responsavel=request.GET.get('responsavel','');busca=request.GET.get('q','').strip()
    if estado:qs=qs.filter(situacao=estado)
    if responsavel.isdigit():qs=qs.filter(responsavel_id=responsavel)
    if busca:qs=qs.filter(Q(chamado__numero__icontains=busca)|Q(chamado__cliente__nome__icontains=busca)|Q(chamado__empreendimento__nome_historico__icontains=busca)|Q(chamado__empreendimento__obra__nome__icontains=busca))
    from django.contrib.auth import get_user_model
    from calendar import monthrange
    # Grade com dias completos, inclusive a borda da primeira/última semana.
    inicio_grade=inicio-timedelta(days=inicio.weekday())
    fim_grade=fim+timedelta(days=6-fim.weekday())
    eventos=list(qs.filter(inicio__date__gte=inicio_grade,inicio__date__lte=fim_grade)[:2000])
    por_dia={}
    for evento in eventos:
        chave=timezone.localtime(evento.inicio).date()
        por_dia.setdefault(chave,[]).append(evento)
    semanas=[];dia=inicio_grade
    while dia<=fim_grade:
        semana=[]
        for _ in range(7):
            semana.append({'data':dia,'atual':inicio<=dia<=fim,'eventos':por_dia.get(dia,[])})
            dia+=timedelta(days=1)
        semanas.append(semana)
    passo=timedelta(days=1 if modo=='dia' else 7 if modo=='semana' else 30)
    anterior_data=(inicio-timedelta(days=1)) if modo=='mes' else base-passo
    proxima_data=(fim+timedelta(days=1)) if modo=='mes' else base+passo
    return render(request,'pos_obra/agenda.html',{'pagina_query':pagina_contexto(request),'semanas_calendario':semanas,'data_anterior':anterior_data,'data_proxima':proxima_data,'agendamentos':Paginator(qs,50).get_page(request.GET.get('page')),'inicio':inicio,'fim':fim,'base':base,'modo':modo,'situacao':estado,'responsavel_atual':responsavel,'busca':busca,'situacoes':AgendamentoOS.SITUACOES,'responsaveis':get_user_model().objects.filter(is_active=True,cliente_saari__isnull=True).order_by('first_name','username')})

@interno
@require_POST
@transaction.atomic
def alterar_agendamento(request,pk):
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    a=get_object_or_404(AgendamentoOS.objects.select_for_update().select_related('chamado'),pk=pk)
    if a.chamado.status in ('CONCLUIDO','CANCELADO'):raise PermissionDenied('OS encerrada.')
    acao=request.POST.get('acao')
    anterior=a.situacao
    if anterior not in ('PROPOSTO','CONFIRMADO','REAGENDAMENTO'):raise PermissionDenied('Este compromisso já está encerrado.')
    if acao=='REAGENDAR':
        from django.contrib.auth import get_user_model
        raw=request.POST.get('responsavel','')
        if raw.isdigit():get_user_model().objects.select_for_update().filter(pk=raw).first()
        f=AgendamentoForm(request.POST,instance=a,auto_id=f'reagendar-{a.pk}-%s')
        if not f.is_valid():
            messages.error(request,' '.join(str(e) for erros in f.errors.values() for e in erros))
            return _erro_operacao(request,a.chamado,'form_reagendamento_invalido',f,'agendamentos',reagendamento_id=a.pk)
        a.situacao='SUBSTITUIDO';a.save(update_fields=['situacao'])
        novo=AgendamentoOS(**{k:v for k,v in f.cleaned_data.items()});novo.chamado=a.chamado;novo.criado_por=request.user;novo.save()
        HistoricoAgendamento.objects.create(agendamento=novo,usuario=request.user,para='PROPOSTO',observacao=f'Reagendamento do compromisso #{a.pk}')
        enfileirar(a.chamado,'REAGENDAMENTO',novo.pk,f'SAARI | Novo horário {a.chamado.numero}',f'Proposta de atendimento para {timezone.localtime(novo.inicio):%d/%m/%Y %H:%M}. Confirme no portal.')
    elif acao in ('CANCELADO','REALIZADO','NAO_REALIZADO'):
        if acao=='REALIZADO' and a.situacao!='CONFIRMADO':raise PermissionDenied('Atendimento ainda não confirmado.')
        a.situacao=acao;a.save(update_fields=['situacao'])
        enfileirar(a.chamado,'ALTERACAO_AGENDAMENTO',f'{a.pk}:{acao}',f'SAARI | Atualização de atendimento {a.chamado.numero}',f'O agendamento da OS {a.chamado.numero} foi atualizado: {a.get_situacao_display()}.')
    else:raise PermissionDenied('Ação inválida')
    HistoricoAgendamento.objects.create(agendamento=a,usuario=request.user,de=anterior,para=a.situacao,observacao=request.POST.get('observacao','')[:2000])
    registro(a.chamado,request.user,a.chamado.status,f'Agendamento {a.pk}: {anterior} → {a.situacao}',True)
    messages.success(request,'Agendamento atualizado e histórico preservado.')
    return redirect(reverse('pos_obra:detalhe',args=[a.chamado_id])+'#agendamentos')

@interno
@require_POST
def registrar_tratativa(request,pk):
    if not possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'editar_ocorrencia'):raise PermissionDenied
    c=get_object_or_404(Chamado,pk=pk)
    obs=request.POST.get('observacao','').strip()
    if len(obs)<5:
        return _erro_operacao(request,c,'tratativa_erro',{'valor':obs,'mensagem':'Informe uma tratativa com pelo menos 5 caracteres.'},'satisfacao')
    TratativaSatisfacao.objects.create(chamado=c,responsavel=request.user,observacao=obs[:5000])
    registro(c,request.user,c.status,'Tratativa administrativa registrada para avaliação do cliente.')
    return redirect(reverse('pos_obra:detalhe',args=[pk])+'#satisfacao')


@login_required
def comprovante_aceite(request,pk):
    """PDF consolidado: documento original + registro de aceite. Não substitui assinatura certificada."""
    import hashlib
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from pypdf import PdfReader, PdfWriter
    a=get_object_or_404(AceiteOS.objects.select_related('documento__chamado'),pk=pk)
    cl=cliente_do_usuario(request.user)
    if cl:
        if not pode_acessar(cl,a.documento.chamado):raise PermissionDenied
    elif not (acesso_interno(request.user) and possui_permissao_acao(request.user,ModuloSistema.POS_OBRA,'visualizar')):raise PermissionDenied
    with a.documento.arquivo.open('rb') as arquivo:original=arquivo.read()
    if hashlib.sha256(original).hexdigest()!=a.documento.sha256:raise Http404('Falha na verificação de integridade do documento.')
    writer=PdfWriter();writer.append(PdfReader(BytesIO(original)))
    from ..relatorios import gerar_termo_aceite
    writer.append(PdfReader(BytesIO(gerar_termo_aceite(a))))
    resultado=BytesIO();writer.write(resultado)
    return HttpResponse(resultado.getvalue(),content_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{a.documento.chamado.numero}-aceite-v{a.documento.versao}.pdf"'})
