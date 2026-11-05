"""Dashboards gerenciais do SAARI; todas as operações são somente leitura."""
from datetime import date, timedelta, datetime, time, timezone as datetime_timezone
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, Q, Sum, DecimalField, ExpressionWrapper, Case, When, CharField, DateTimeField
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.http import HttpResponse
import csv
from django.utils import timezone
from usuarios.models import ModuloSistema, PermissaoModulo
from obras.models import Obra, FVS, FVSItem, VistoriaItem, DiarioObra, MovimentoEstoque
from projetos.models import ChecklistProjetoResposta, AlteracaoProjeto
from compras.models import ProcessoCompra, PedidoCompra
from pos_obra.models import Chamado, MaterialOS, PesquisaSatisfacao
from relatorios.services import analises


def _auth(user):
    if not (user.is_superuser or PermissaoModulo.objects.filter(usuario=user, modulo=ModuloSistema.RELATORIOS, ativo=True).exists()):
        raise PermissionDenied('Sem acesso ao módulo Indicadores.')


def _date(raw):
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _filters(request, empreendimento=False):
    start, end = _date(request.GET.get('inicio')), _date(request.GET.get('fim'))
    if start and end and start > end:
        start, end = end, start
    obra_raw = request.GET.get('obra', '')
    obra = int(obra_raw) if obra_raw.isdigit() and Obra.objects.filter(pk=int(obra_raw)).exists() else None
    empr_raw = request.GET.get('empreendimento', '')
    empr = int(empr_raw) if empr_raw.isdigit() and Chamado.objects.filter(empreendimento_id=int(empr_raw)).exists() else None
    return {'inicio':start, 'fim':end,'obra_id':obra, 'empreendimento_id':empr,
            'obras_filtro':Obra.objects.order_by('nome').values('id','nome'),
            'empreendimentos_filtro':_empreendimentos() if empreendimento else [],
            'filtro_empreendimento':empreendimento}


def _empreendimentos():
    rows=Chamado.objects.values('empreendimento_id', 'empreendimento__obra__nome', 'empreendimento__nome_historico').distinct()
    return sorted([{'id':r['empreendimento_id'],'nome':r['empreendimento__obra__nome'] or r['empreendimento__nome_historico'] or 'Sem nome'} for r in rows], key=lambda r:r['nome'].casefold())


def _apply(qs, f, campo, obra_field=None, pos=False):
    if campo.endswith('__date'):
        base = campo[:-6]
        if f['inicio']: qs = qs.filter(**{base+'__gte':timezone.make_aware(datetime.combine(f['inicio'],time.min))})
        if f['fim']: qs = qs.filter(**{base+'__lt':timezone.make_aware(datetime.combine(f['fim']+timedelta(days=1),time.min))})
    else:
        if f['inicio']: qs = qs.filter(**{campo+'__gte':f['inicio']})
        if f['fim']: qs = qs.filter(**{campo+'__lte':f['fim']})
    if pos and f['empreendimento_id']: qs = qs.filter(empreendimento_id=f['empreendimento_id'])
    if obra_field and f['obra_id']: qs = qs.filter(**{obra_field:f['obra_id']})
    return qs


def _money(value):
    return f'{Decimal(value or 0):,.2f}'.replace(',','@').replace('.',',').replace('@','.')


def _card(label, value, subtitle='', money=False):
    return {'label':label, 'value':('R$ '+_money(value)) if money else str(value), 'subtitle':subtitle}


def _group(qs, field, label=None, limit=8, money=False):
    if money:
        data=list(qs.values(field).annotate(total=Sum(money)).order_by('-total')[:limit])
    else:
        data=list(qs.values(field).annotate(total=Count('pk')).order_by('-total')[:limit])
    peak=max((float(r['total'] or 0) for r in data),default=0)
    return [{'label':str(r[field] if r[field] not in (None,'') else 'Não informado').replace('_',' ').title(),
            'value':_money(r['total']) if money else str(r['total']),
            'width':round(float(r['total'] or 0)*100/peak,1) if peak else 0} for r in data]


def _series(qs, field, money=None):
    # DateField não aceita tzinfo; DateTimeField aceita e usa UTC para
    # evitar conversões para fusos nomeados no MySQL sem tabelas de timezone.
    field_obj = qs.model._meta.get_field(field)
    trunc = (TruncMonth(field, tzinfo=datetime_timezone.utc)
             if isinstance(field_obj, DateTimeField)
             else TruncMonth(field))
    query=qs.annotate(mes=trunc).values('mes')
    rows=query.annotate(total=Sum(money) if money else Count('pk')).order_by('mes')
    data=[{'label':row['mes'].strftime('%m/%Y'),'value':_money(row['total']) if money else str(row['total']),
           'raw':float(row['total'] or 0)} for row in rows if row['mes']]
    peak=max((r['raw'] for r in data),default=0)
    for row in data: row['width']=round(row['raw']*100/peak,1) if peak else 0
    return data[-12:]


def _panel(title, rows, caption=''):
    # Séries mensais possuem `raw`; demais painéis são classificações/rankings.
    kind = 'timeline' if rows and 'raw' in rows[0] else 'ranking'
    return {'title': title, 'rows': rows, 'caption': caption, 'kind': kind}


# Seções determinadas pelo significado dos indicadores, jamais pelo número de gráficos.
PANEL_SECTIONS = {
    'geral': [
        ('Evolução dos módulos', ['Pedidos por mês', 'OS abertas por mês']),
        ('Situação dos atendimentos', ['Situação das OS abertas no período']),
    ],
    'projetos': [
        ('Situação documental', ['Distribuição documental', 'Menor conclusão documental por obra']),
        ('Pendências e prioridades', ['Pendências por obra', 'Pendências documentais críticas', 'Pendências por grupo']),
        ('Alterações e histórico', ['Alterações por disciplina', 'Alterações registradas por mês']),
    ],
    'obras': [
        ('Qualidade das inspeções', ['Situação das FVS', 'Não conformidades por item de verificação', 'Não conformidade por empresa executora']),
        ('Evolução e distribuição', ['FVS emitidas por mês', 'FVS por obra', 'FVS por empresa executora']),
        ('Vistorias e registros de obra', ['Vistorias por situação', 'Ocorrências cautelares por manifestação', 'Diários por obra']),
        ('Materiais e almoxarifado', ['Movimentações de estoque por tipo', 'Saídas de materiais mais frequentes']),
    ],
    'suprimentos': [
        ('Contratações e valores', ['Pedidos por mês', 'Compras por obra', 'Compras por fornecedor']),
        ('Fluxo de compras', ['Etapas dos processos', 'Tempo médio por etapa', 'Decisões de aprovação']),
        ('Entregas e fornecedores', ['Situação dos pedidos', 'Fornecedores com pedidos abertos atrasados']),
        ('Gestão das compras', ['Compras por responsável']),
    ],
    'pos_obra': [
        ('Volume e evolução', ['Abertura de OS por mês', 'OS por situação', 'OS por empreendimento']),
        ('Problemas e prioridades', ['Tipos de problema', 'Tipos de problema mais frequentes', 'Prioridade dos chamados', 'OS por 100 unidades (obras atuais)']),
        ('Atendimento e experiência', ['Notas médias da pesquisa', 'Resolução informada pelo cliente', 'Resolução declarada pelo cliente', 'OS por responsável']),
        ('Custos', ['Custo de materiais por tipo de problema']),
    ],
}


def _sections_for(page, panels):
    by_title = {p['title']: p for p in panels}
    assigned = set()
    sections = []
    for title, names in PANEL_SECTIONS.get(page, []):
        entries = [by_title[n] for n in names if n in by_title and n not in assigned]
        assigned.update(p['title'] for p in entries)
        if entries:
            sections.append({'title': title, 'panels': entries})
    others = [p for p in panels if p['title'] not in assigned]
    if others:
        sections.append({'title': 'Outras análises', 'panels': others})
    return sections


def _render(request, title, page, cards, panels, f, note='', warning='', planning=False):
    if request.GET.get('exportar') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="indicadores_{page}.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        def safe(value):
            value = str(value or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
        writer.writerow(['Módulo', title, 'Período', str(f['inicio'] or 'Todos'), str(f['fim'] or 'Todos')])
        writer.writerow(['INDICADORES', 'Valor', 'Observação'])
        for item in cards: writer.writerow([safe(item['label']), safe(item['value']), safe(item['subtitle'])])
        for block in panels:
            writer.writerow([]); writer.writerow([safe(block['title']), 'Valor', safe(block['caption'])])
            for row in block['rows']:writer.writerow([safe(row['label']),safe(row['value'])])
        return response
    sections = _sections_for(page, panels)
    return render(request,'relatorios/painel.html',{'titulo':title,'pagina':page,'cards':cards,'panels':panels,
      'sections':sections,'destaques':cards[:4],'complementares':cards[4:], 'total_analises':len(panels),'nota':note,'aviso':warning,'planejamento_link':planning,**f})


@login_required
def visao_geral(request):
    _auth(request.user)
    f=_filters(request)
    projetos=_apply(ChecklistProjetoResposta.objects.all(),f,'criado_em__date','obra_id')
    pedidos=_apply(PedidoCompra.objects.exclude(status='CANCELADO'),f,'data','obra_id')
    os=_apply(Chamado.objects.all(),f,'criado_em__date')
    fvs=_apply(FVS.objects.all(),f,'data_abertura','obra_id')
    cards=[_card('Obras em andamento',Obra.objects.filter(status=Obra.Status.EM_ANDAMENTO).count(),'Situação atual; não limitada pelo período'),
           _card('Itens documentais',projetos.count(),'Cadastros no período'),
           _card('FVS abertas',fvs.count(),'Emitidas no período'),
           _card('Valor dos pedidos',pedidos.aggregate(v=Sum('valor_total'))['v'], 'Pedidos não cancelados',True),
           _card('OS abertas',os.count(),'Abertas no período'),
           _card('OS ainda não concluídas',os.exclude(status__in=['CONCLUIDO','CANCELADO']).count(),'Das OS abertas no período')]
    aplicaveis=projetos.exclude(status='NAO_SE_APLICA')
    finished=aplicaveis.filter(status__in=['FINALIZADO','RECEBIDO']).count()
    n_app=aplicaveis.count()
    itens_fvs=FVSItem.objects.filter(fvs__in=fvs,resultado__in=['C','NC'])
    total_itens=itens_fvs.count()
    n_nc=itens_fvs.filter(resultado='NC').count()
    overdue=pedidos.exclude(status='ENTREGUE').filter(
        Q(previsao_entrega_atual__lt=timezone.localdate())|
        Q(previsao_entrega_atual__isnull=True,previsao_entrega_original__lt=timezone.localdate()))
    cards += [_card('Conclusão documental',f'{finished/n_app*100:.1f}%' if n_app else '—', 'Itens aplicáveis cadastrados no período'),
              _card('Não conformidade das FVS',f'{n_nc/total_itens*100:.1f}%' if total_itens else '—','Itens NC / itens verificados das FVS no período'),
              _card('Pedidos com entrega vencida',overdue.count(),'Situação atual dos pedidos emitidos no período')]
    panels=[_panel('Pedidos por mês',_series(pedidos,'data','valor_total'),'Valores de pedidos emitidos; não representam pagamentos.'),
            _panel('OS abertas por mês',_series(os,'criado_em'),'Por data de abertura da OS.'),
            _panel('Situação das OS abertas no período',_group(os,'status'))]
    return _render(request,'Visão Geral','geral',cards,panels,f,'O filtro de obra restringe Projetos, Obras e Suprimentos. Pós-Obra utiliza cadastro próprio de empreendimentos e permanece consolidado nesta página.')


@login_required
def projetos(request):
    _auth(request.user); f=_filters(request)
    qs=_apply(ChecklistProjetoResposta.objects.all(),f,'criado_em__date','obra_id')
    changes=_apply(AlteracaoProjeto.objects.all(),f,'criado_em__date','obra_id')
    total=qs.count(); na=qs.filter(status='NAO_SE_APLICA').count(); done=qs.filter(status__in=['FINALIZADO','RECEBIDO']).count(); base=total-na
    cards=[_card('Itens registrados',total),_card('Finalizados / recebidos',done),
           _card('Conclusão aplicável',f'{done/base*100:.1f}%' if base else '—','Não se aplica excluído do denominador'),
           _card('Pendências registradas',qs.exclude(status__in=['FINALIZADO','RECEBIDO','NAO_SE_APLICA']).count()),
           _card('Alterações de projeto',changes.count())]
    panels=[_panel('Distribuição documental',_group(qs,'status')),
            _panel('Pendências por obra',_group(qs.exclude(status__in=['FINALIZADO','RECEBIDO','NAO_SE_APLICA']),'obra__nome')),
            _panel('Alterações por disciplina',_group(changes,'disciplina__nome')),
            _panel('Alterações registradas por mês',_series(changes,'criado_em'))]
    add_cards, add_panels = analises.project_details(qs,changes,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Projetos','projetos',cards,panels,f,'Os percentuais consideram os itens efetivamente cadastrados. Não há medição de prazo de entrega individual sem cadastro de data-limite.')


@login_required
def obras(request):
    _auth(request.user); f=_filters(request)
    fvs=_apply(FVS.objects.all(),f,'data_abertura','obra_id')
    itens=FVSItem.objects.filter(fvs__in=fvs)
    diarios=_apply(DiarioObra.objects.all(),f,'data','obra_id')
    vistorias=_apply(VistoriaItem.objects.all(),f,'atualizado_em__date','atividade__obra_id')
    movimentacoes=_apply(MovimentoEstoque.objects.all(),f,'data_movimento__date','obra_origem_id')
    checked=itens.filter(resultado__in=['C','NC']); confirmed=checked.filter(resultado='C').count(); count=checked.count()
    cards=[_card('FVS abertas',fvs.count()),_card('Itens não conformes',itens.filter(resultado='NC').count()),
           _card('Conformidade verificada',f'{confirmed/count*100:.1f}%' if count else '—','Apenas itens conformes/não conformes'),
           _card('Vistorias feitas',vistorias.filter(status='FEITO').count()),_card('Diários registrados',diarios.count()),
           _card('Movimentações de saída',movimentacoes.filter(tipo='SAIDA').count())]
    panels=[_panel('Situação das FVS',_group(fvs,'status')),
            _panel('FVS por obra',_group(fvs,'obra__nome')),
            _panel('FVS emitidas por mês',_series(fvs,'data_abertura')),
            _panel('Vistorias por situação',_group(vistorias,'status')),
            _panel('Movimentações de estoque por tipo',_group(movimentacoes,'tipo'))]
    add_cards, add_panels = analises.work_details(fvs,itens,diarios,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Obras','obras',cards,panels,f,
       'O cronograma detalhado continua no Planejamento. Movimentações refletem registros de saída/transferência, não custo total de consumo.',planning=True)


@login_required
def suprimentos(request):
    _auth(request.user); f=_filters(request)
    pedidos=_apply(PedidoCompra.objects.exclude(status='CANCELADO'),f,'data','obra_id')
    processos=_apply(ProcessoCompra.objects.all(),f,'data_abertura','obra_id')
    abertos=pedidos.exclude(status='ENTREGUE'); today=timezone.localdate()
    late=abertos.filter(Q(previsao_entrega_atual__lt=today)|Q(previsao_entrega_atual__isnull=True,previsao_entrega_original__lt=today))
    cards=[_card('Pedidos emitidos',pedidos.count()),
           _card('Total contratado',pedidos.aggregate(v=Sum('valor_total'))['v'],'Pedidos não cancelados',True),
           _card('Pedidos em aberto',abertos.count()),_card('Entregas vencidas',late.count(),'Pedidos em aberto e previsão vencida'),
           _card('Processos de compra',processos.count()),
           _card('Ticket médio por pedido',(pedidos.aggregate(v=Sum('valor_total'))['v'] or 0)/pedidos.count() if pedidos.exists() else 0,'Pedidos não cancelados',True)]
    panels=[_panel('Pedidos por mês',_series(pedidos,'data','valor_total'),'Valores de contratação, sem equivalência automática com pagamento.'),
            _panel('Situação dos pedidos',_group(pedidos,'status')),
            _panel('Compras por obra',_group(pedidos,'obra__nome',money='valor_total')),
            _panel('Compras por fornecedor',_group(pedidos,'fornecedor__nome',money='valor_total')),
            _panel('Etapas dos processos',_group(processos,'etapa_atual'))]
    add_cards, add_panels = analises.supplier_details(processos,pedidos,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Suprimentos','suprimentos',cards,panels,f,
     'As métricas consideram somente pedidos atuais. Histórico importado não é somado para evitar duplicações. Economia negociada será adicionada após validação das bases comparáveis.')


@login_required
def pos_obra(request):
    _auth(request.user); f=_filters(request,empreendimento=True)
    qs=_apply(Chamado.objects.all(),f,'criado_em__date',pos=True)
    active=qs.exclude(status__in=['CONCLUIDO','CANCELADO'])
    materials=MaterialOS.objects.filter(chamado__in=qs)
    amount=materials.aggregate(v=Sum(ExpressionWrapper(F('utilizado')*F('custo_unitario'),output_field=DecimalField(max_digits=26,decimal_places=4))))['v'] or Decimal('0')
    survey=PesquisaSatisfacao.objects.filter(chamado__in=qs)
    closed=qs.filter(status='CONCLUIDO')
    cards=[_card('OS abertas no período',qs.count()),_card('OS não encerradas',active.count()),
           _card('OS concluídas',closed.count()),_card('OS com prazo vencido',active.filter(prazo__lt=timezone.localdate()).count()),
           _card('Custo registrado de materiais',amount,'Exclui serviços, mão de obra e deslocamento',True),
           _card('Pesquisas respondidas',survey.count())]
    panels=[_panel('Abertura de OS por mês',_series(qs,'criado_em')),
            _panel('OS por situação',_group(qs,'status')),
            _panel('Tipos de problema',_group(qs,'tipo_problema__nome')),
            _panel('OS por empreendimento',_group(qs.annotate(nome_empreendimento=Case(When(empreendimento__obra__isnull=False,then=F('empreendimento__obra__nome')),default=F('empreendimento__nome_historico'),output_field=CharField())),'nome_empreendimento')),
            _panel('Prioridade dos chamados',_group(qs,'prioridade')),
            _panel('Resolução informada pelo cliente',_group(survey,'resolvido'))]
    add_cards, add_panels = analises.post_details(qs,active,survey,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Pós-Obra','pos_obra',cards,panels,f,
       'Os custos representam somente materiais utilizados; métricas de status e prazo consideram a situação atual das OS abertas dentro do período selecionado.')
