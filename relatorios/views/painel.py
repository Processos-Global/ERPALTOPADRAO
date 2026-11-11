"""Dashboards gerenciais do SAARI; todas as operações são somente leitura."""
from datetime import date
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db.models import Count, F, Q, Sum, DecimalField, ExpressionWrapper, Case, When, CharField, DateTimeField
from django.db.models.functions import TruncMonth
from collections import defaultdict
from cadastros.models import EmpreendimentoPosObra
from usuarios.decorators import possui_permissao_acao
from relatorios.services.dates import range_dt
from relatorios.services.presentation import chart, number
from django.shortcuts import render
from django.http import HttpResponse
import csv
from django.utils import timezone
from usuarios.models import ModuloSistema
from obras.models import Obra, FVS, FVSItem, VistoriaItem, DiarioObra, MovimentoEstoque
from projetos.models import ChecklistProjetoResposta, AlteracaoProjeto
from compras.models import ProcessoCompra, PedidoCompra
from pos_obra.models import Chamado, MaterialOS, PesquisaSatisfacao
from relatorios.services import analises, estrategicos


def _auth(user, export=False):
    if not possui_permissao_acao(user, ModuloSistema.RELATORIOS, 'visualizar'):
        raise PermissionDenied('Sem acesso ao módulo Indicadores.')
    if export and not possui_permissao_acao(user, ModuloSistema.RELATORIOS, 'exportar'):
        raise PermissionDenied('Sem permissão para exportar relatórios.')


def _date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (ValueError, TypeError):
        raise SuspiciousOperation('Data inválida. Use AAAA-MM-DD.')


def _identifier(raw, model):
    if not raw:
        return None
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 19:
        raise SuspiciousOperation('Identificador inválido.')
    pk = int(raw)
    if not 0 < pk <= 9223372036854775807 or not model.objects.filter(pk=pk).exists():
        raise SuspiciousOperation('Seleção inexistente.')
    return pk


def _filters(request, empreendimento=False):
    start, end = _date(request.GET.get('inicio')), _date(request.GET.get('fim'))
    if start and end and start > end:
        start, end = end, start
    return {'inicio': start, 'fim': end,
            'obra_id': _identifier(request.GET.get('obra', ''), Obra),
            'empreendimento_id': _identifier(request.GET.get('empreendimento', ''), EmpreendimentoPosObra),
            'obras_filtro': Obra.objects.order_by('nome').values('id', 'nome'),
            'empreendimentos_filtro': _empreendimentos() if empreendimento else [],
            'filtro_empreendimento': empreendimento}


def _empreendimentos():
    rows = EmpreendimentoPosObra.objects.values('id', 'obra__nome', 'nome_historico')
    return sorted([{'id': r['id'], 'nome': r['obra__nome'] or r['nome_historico'] or 'Sem nome'}
                   for r in rows], key=lambda r: r['nome'].casefold())


def _apply(qs, f, campo, obra_field=None, pos=False):
    if campo.endswith('__date'):
        qs = range_dt(qs, campo[:-6], f)
    else:
        if f['inicio']: qs = qs.filter(**{campo+'__gte':f['inicio']})
        if f['fim']: qs = qs.filter(**{campo+'__lte':f['fim']})
    if pos and f['empreendimento_id']: qs = qs.filter(empreendimento_id=f['empreendimento_id'])
    if obra_field and f['obra_id']: qs = qs.filter(**{obra_field:f['obra_id']})
    return qs


def _money(value):
    return f'{Decimal(value or 0):,.2f}'.replace(',','@').replace('.',',').replace('@','.')


def _card(label, value, subtitle='', money=False, severity=None):
    return {'label':label, 'value':('R$ '+_money(value)) if money and value is not None else ('—' if value is None else str(value)), 'subtitle':subtitle, 'severity':severity}


def _group(qs, field, label=None, limit=8, money=False):
    if money:
        data=list(qs.values(field).annotate(total=Sum(money)).order_by('-total')[:limit])
    else:
        data=list(qs.values(field).annotate(total=Count('pk')).order_by('-total')[:limit])
    peak=max((float(r['total'] or 0) for r in data),default=0)
    return [{'label':str(r[field] if r[field] not in (None,'') else 'Não informado').replace('_',' ').title(),
            'value':_money(r['total']) if money else str(r['total']), 'raw':number(r['total']),
            'width':round(float(r['total'] or 0)*100/peak,1) if peak else 0} for r in data]


def _series(qs, field, money=None):
    is_datetime = isinstance(qs.model._meta.get_field(field), DateTimeField)
    last = qs.exclude(**{field+'__isnull': True}).order_by('-'+field).values_list(field, flat=True).first()
    if last is None:
        return []
    if is_datetime and timezone.is_aware(last):
        last = timezone.localtime(last)
    ordinal = last.year*12 + last.month-1
    earliest = qs.exclude(**{field+'__isnull': True}).order_by(field).values_list(field, flat=True).first()
    if is_datetime and timezone.is_aware(earliest):
        earliest = timezone.localtime(earliest)
    first_ordinal = max(earliest.year*12 + earliest.month-1, ordinal-11)
    first = date(first_ordinal//12, first_ordinal%12+1, 1)
    totals = defaultdict(lambda: Decimal('0'))
    if is_datetime:
        # Bound the streaming read to 12 local calendar months. No timezone
        # conversion in SQL and no named timezone tables required on MySQL.
        limited = range_dt(qs, field, {'inicio':first, 'fim':None})
        columns = [field] + ([money] if money else [])
        for values in limited.order_by().values_list(*columns).iterator(chunk_size=2000):
            dt = values[0]
            local = timezone.localtime(dt) if timezone.is_aware(dt) else dt
            totals[(local.year, local.month)] += (values[1] or 0) if money else 1
    else:
        rows = qs.filter(**{field+'__gte':first}).annotate(mes=TruncMonth(field)).values('mes').annotate(
            total=Sum(money) if money else Count('pk')).order_by()
        totals.update({(r['mes'].year,r['mes'].month):r['total'] for r in rows if r['mes']})
    months = [((n//12,n%12+1), totals[(n//12,n%12+1)]) for n in range(first_ordinal,ordinal+1)]
    peak = max((abs(float(v or 0)) for _,v in months),default=0)
    return [{'label':f'{month:02d}/{year}', 'value':_money(v) if money else str(int(v)),
             'raw':number(v), 'width':round(abs(float(v or 0))*100/peak,1) if peak else 0}
            for (year,month),v in months]


def _panel(title, rows, caption='', *, chart=None, series=None):
    from relatorios.services.presentation import chart as chart_spec
    metadata = chart or chart_spec()
    data = {'title': title, 'rows': rows, 'caption': caption,
            'kind': 'timeline' if metadata['sort'] == 'chronological' else 'ranking', 'chart': metadata}
    for row in rows:
        row.setdefault('raw', None)
    if series is not None:
        data['series'] = series
        for index, row in enumerate(rows):
            row['series_values'] = [
                '—' if item['values'][index] is None else
                f"{item['values'][index]:.{metadata['precision']}f}".replace('.', ',')
                for item in series]
    return data


def _monthly_chart(money=False):
    return chart(orientation='vertical', unit='currency' if money else 'count',
                 precision=2 if money else 0, sort='chronological', allowed_types=['bar', 'line'])


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
    'planejamento': [
        ('Desempenho físico', ['Previsto e executado por obra/projeto', 'Desvio físico por obra']),
        ('Marcos do cronograma', ['Situação dos marcos']),
        ('Cronograma de suprimentos', ['Contratações pendentes vencidas por obra', 'Suprimentos programados por categoria']),
    ],
    'financeiro': [
        ('Desembolso e previsão', ['Previsão financeira por mês', 'Pagamentos efetivados por mês']),
        ('Composição das previsões', ['Previsões por nível de certeza']),
    ],
    'pos_obra': [
        ('Volume e evolução', ['Abertura de OS por mês', 'OS por situação', 'OS por empreendimento']),
        ('Problemas e prioridades', ['Tipos de problema', 'Categorias de problema', 'Prioridade dos chamados', 'OS por 100 unidades (obras atuais)']),
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
        sections.append({'title': 'Evolução física' if page == 'planejamento' else 'Outras análises', 'panels': others})
    return sections


def _render(request, title, page, cards, panels, f, note='', warning='', planning=False):
    _auth(request.user, request.GET.get('exportar') == 'csv')
    if request.GET.get('exportar') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="indicadores_{page}.csv"'
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        def safe(value):
            value = str(value or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
        writer.writerow(['Módulo', title, 'Período', str(f['inicio'] or 'Todos'), str(f['fim'] or 'Todos')])
        writer.writerow(['Obra ID', f.get('obra_id') or 'Todas', 'Empreendimento ID', f.get('empreendimento_id') or 'Todos'])
        writer.writerow(['Exportação resumida: rankings e séries seguem os limites indicados nos painéis.'])
        writer.writerow(['INDICADORES', 'Valor', 'Observação'])
        for item in cards: writer.writerow([safe(item['label']), safe(item['value']), safe(item['subtitle'])])
        for block in panels:
            writer.writerow([])
            writer.writerow([safe(block['title']), safe(block['caption'])])
            writer.writerow(['Categoria / período'] + ([safe(s['name']) for s in block['series']] if block.get('series') else ['Valor']))
            for row in block['rows']:
                writer.writerow([safe(row['label'])] + [safe(v) for v in (row['series_values'] if block.get('series') else [row['value']])])
        return response
    sections = _sections_for(page, panels)
    return render(request,'relatorios/painel.html',{'titulo':title,'pagina':page,'cards':cards,'panels':panels,
      'pode_exportar': possui_permissao_acao(request.user, ModuloSistema.RELATORIOS, 'exportar'), 'sections':sections,'destaques':cards[:4],'complementares':cards[4:], 'total_analises':len(panels),'nota':note,'aviso':warning,'planejamento_link':planning,**f})


@login_required
def visao_geral(request):
    _auth(request.user, request.GET.get('exportar') == 'csv')
    f=_filters(request)
    projetos=_apply(ChecklistProjetoResposta.objects.all(),f,'criado_em__date','obra_id')
    pedidos=_apply(PedidoCompra.objects.exclude(status='CANCELADO'),f,'data','obra_id')
    os=_apply(Chamado.objects.all(),f,'criado_em__date','empreendimento__obra_id')
    fvs=_apply(FVS.objects.all(),f,'data_abertura','obra_id')
    works = Obra.objects.filter(status=Obra.Status.EM_ANDAMENTO)
    if f['obra_id']:
        works = works.filter(pk=f['obra_id'])
    cards=[_card('Obras em andamento',works.count(),'Situação atual; não limitada pelo período'),
           _card('Itens documentais',projetos.count(),'Cadastros no período'),
           _card('FVS emitidas',fvs.count(),'Emitidas no período'),
           _card('Valor dos pedidos',pedidos.aggregate(v=Sum('valor_total'))['v'] or 0, 'Pedidos não cancelados',True),
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
    late_orders = overdue.count()
    late_os = os.exclude(status__in=['CONCLUIDO','CANCELADO']).filter(prazo__lt=timezone.localdate()).count()
    cards = [_card('Pendências documentais',n_app-finished,f'{n_app} itens aplicáveis da coorte',severity='warning' if n_app>finished else None),
             _card('Não conformidade das FVS',f'{n_nc/total_itens*100:.1f}%' if total_itens else '—',f'{n_nc} NC / {total_itens} itens avaliados',severity='warning' if n_nc else None),
             _card('Pedidos com entrega vencida',late_orders,'Situação atual dos pedidos emitidos no período',severity='warning' if late_orders else None),
             _card('OS com prazo vencido',late_os,'Situação atual da coorte; obra apenas por vínculo cadastrado',severity='warning' if late_os else None),
             _card('Conclusão documental',f'{finished/n_app*100:.1f}%' if n_app else '—',f'{finished} concluídos / {n_app} aplicáveis')] + cards
    # Destaques físicos: somente se houver importação ativa com dados.
    plan_cards, _, _ = estrategicos.planejamento(f, _card, _ranking_panel, summary_only=True)
    if plan_cards and plan_cards[0]['value'] != '0':
        cards += plan_cards
    panels=[_panel('Pedidos por mês',_series(pedidos,'data','valor_total'),'Até 12 meses corridos terminando no último registro da coorte; contratação, não pagamento.',chart=_monthly_chart(True)),
            _panel('OS abertas por mês',_series(os,'criado_em'),'Até 12 meses corridos; abertura no fuso local, lacunas sem registros = zero.',chart=_monthly_chart()),
            _panel('Situação das OS abertas no período',_group(os,'status'))]
    return _render(request,'Visão Geral','geral',cards,panels,f,'Riscos atuais das coortes do período. O filtro de obra inclui somente OS de empreendimentos vinculados à obra; históricos sem vínculo ficam fora desse recorte.')


@login_required
def projetos(request):
    _auth(request.user, request.GET.get('exportar') == 'csv'); f=_filters(request)
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
            _panel('Alterações registradas por mês',_series(changes,'criado_em'),'Até 12 meses corridos; abertura no fuso local.',chart=_monthly_chart())]
    add_cards, add_panels = analises.project_details(qs,changes,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Projetos','projetos',cards,panels,f,'Os percentuais consideram os itens efetivamente cadastrados. Não há medição de prazo de entrega individual sem cadastro de data-limite.')


@login_required
def obras(request):
    _auth(request.user, request.GET.get('exportar') == 'csv'); f=_filters(request)
    fvs=_apply(FVS.objects.all(),f,'data_abertura','obra_id')
    itens=FVSItem.objects.filter(fvs__in=fvs)
    diarios=_apply(DiarioObra.objects.all(),f,'data','obra_id')
    vistorias=_apply(VistoriaItem.objects.all(),f,'atualizado_em__date','atividade__obra_id')
    movimentacoes=_apply(MovimentoEstoque.objects.all(),f,'data_movimento__date','obra_origem_id')
    checked=itens.filter(resultado__in=['C','NC']); confirmed=checked.filter(resultado='C').count(); count=checked.count()
    nc = count-confirmed
    cards=[_card('Itens não conformes',nc,severity='warning' if nc else None),
           _card('Conformidade verificada',f'{confirmed/count*100:.1f}%' if count else '—',f'{confirmed} conformes / {count} avaliados; NA e vazio excluídos'),
           _card('Itens avaliados',count),_card('Itens sem resultado',itens.filter(resultado='').count()),
           _card('FVS emitidas',fvs.count()),
           _card('Vistorias feitas',vistorias.filter(status='FEITO').count()),_card('Diários registrados',diarios.count()),
           _card('Movimentações de saída',movimentacoes.filter(tipo='SAIDA').count())]
    panels=[_panel('Situação das FVS',_group(fvs,'status')),
            _panel('FVS por obra',_group(fvs,'obra__nome')),
            _panel('FVS emitidas por mês',_series(fvs,'data_abertura'),'Até 12 meses corridos.',chart=_monthly_chart()),
            _panel('Vistorias por situação',_group(vistorias,'status')),
            _panel('Movimentações de estoque por tipo',_group(movimentacoes,'tipo'))]
    add_cards, add_panels = analises.work_details(fvs,itens,diarios,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Obras','obras',cards,panels,f,
       'O cronograma detalhado continua no Planejamento. Movimentações refletem registros de saída/transferência, não custo total de consumo.',planning=True)


@login_required
def suprimentos(request):
    _auth(request.user, request.GET.get('exportar') == 'csv'); f=_filters(request)
    pedidos=_apply(PedidoCompra.objects.exclude(status='CANCELADO'),f,'data','obra_id')
    processos=_apply(ProcessoCompra.objects.all(),f,'data_abertura','obra_id')
    abertos=pedidos.exclude(status='ENTREGUE'); today=timezone.localdate()
    late=abertos.filter(Q(previsao_entrega_atual__lt=today)|Q(previsao_entrega_atual__isnull=True,previsao_entrega_original__lt=today))
    totals = pedidos.aggregate(total=Sum('valor_total'), quantidade=Count('pk'))
    total_value, order_count = totals['total'] or Decimal('0'), totals['quantidade']
    cards=[_card('Pedidos emitidos',order_count),
           _card('Total contratado',total_value,'Pedidos não cancelados',True),
           _card('Pedidos em aberto',abertos.count()),_card('Entregas vencidas',late.count(),'Pedidos em aberto e previsão vencida'),
           _card('Processos de compra',processos.count()),
           _card('Ticket médio por pedido',total_value/order_count if order_count else 0,'Pedidos não cancelados',True)]
    suppliers = pedidos.values('fornecedor_id','fornecedor__nome').annotate(total=Sum('valor_total')).order_by('-total','fornecedor_id')[:8]
    supplier_rows = [{'label':f"{r['fornecedor__nome']} (#{r['fornecedor_id']})",'value':_money(r['total']),'raw':number(r['total']),'width':0} for r in suppliers]
    panels=[_panel('Pedidos por mês',_series(pedidos,'data','valor_total'),'Até 12 meses corridos; contratação, não pagamento.',chart=_monthly_chart(True)),
            _panel('Situação dos pedidos',_group(pedidos,'status')),
            _panel('Compras por obra',_group(pedidos,'obra__nome',money='valor_total'),'Até 8 obras por valor contratado.',chart=chart(unit='currency',precision=2,sort='desc')),
            _panel('Compras por fornecedor',supplier_rows,'Até 8 fornecedores distintos por valor contratado.',chart=chart(unit='currency',precision=2,sort='desc')),
            _panel('Etapas dos processos',_group(processos,'etapa_atual'))]
    add_cards, add_panels = analises.supplier_details(processos,pedidos,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Suprimentos','suprimentos',cards,panels,f,
     'Somente pedidos atuais, sem somar histórico importado. Economia bruta compara preços unitários adjudicados; não representa economia líquida com descontos e frete.')


@login_required
def pos_obra(request):
    _auth(request.user, request.GET.get('exportar') == 'csv'); f=_filters(request,empreendimento=True)
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
    panels=[_panel('Abertura de OS por mês',_series(qs,'criado_em'),'Até 12 meses corridos no fuso local.',chart=_monthly_chart()),
            _panel('OS por situação',_group(qs,'status')),
            _panel('Tipos de problema',_group(qs,'tipo_problema__nome')),
            _panel('OS por empreendimento',_group(qs.annotate(nome_empreendimento=Case(When(empreendimento__obra__isnull=False,then=F('empreendimento__obra__nome')),default=F('empreendimento__nome_historico'),output_field=CharField())),'nome_empreendimento')),
            _panel('Prioridade dos chamados',_group(qs,'prioridade')),
            _panel('Resolução informada pelo cliente',_group(survey,'resolvido'))]
    add_cards, add_panels = analises.post_details(qs,active,survey,f,_card,_panel,_group)
    cards += add_cards; panels += add_panels
    return _render(request,'Pós-Obra','pos_obra',cards,panels,f,
       'Os custos representam somente materiais utilizados; métricas de status e prazo consideram a situação atual das OS abertas dentro do período selecionado.')


@login_required
def planejamento(request):
    _auth(request.user, request.GET.get('exportar') == 'csv')
    f = _filters(request)
    cards, panels, warning = estrategicos.planejamento(f, _card, _ranking_panel)
    return _render(request, 'Planejamento', 'planejamento', cards, panels, f,
        'Avanços físicos não são somados nem promediados entre obras. Data inicial não elimina os snapshots anteriores; data final limita a posição do cronograma.',
        warning=warning, planning=True)


@login_required
def financeiro(request):
    _auth(request.user, request.GET.get('exportar') == 'csv')
    f = _filters(request)
    cards, panels = estrategicos.financeiro(f, _card, _ranking_panel)
    return _render(request, 'Financeiro', 'financeiro', cards, panels, f,
        'Previsões, títulos e pagamentos são visões diferentes; não devem ser somados. Sem versões congeladas, não é calculado erro histórico de previsão.')


def _ranking_panel(title, rows, caption='', **kwargs):
    return _panel(title, rows, caption, **kwargs)
