"""Indicadores gerenciais adicionais: nenhuma alteração de dados/banco."""
from datetime import timedelta, datetime, time
from decimal import Decimal
from statistics import median
from relatorios.services.dates import range_dt
from relatorios.services.presentation import chart, number
from django.db.models import Avg, Count, F, Q, Sum, ExpressionWrapper, DecimalField
from django.utils import timezone
from obras.models import FVSItem, FVSHistorico, DiarioObra, MovimentoEstoque, VistoriaCautelar, OcorrenciaCautelar, Obra
from projetos.models import ChecklistProjetoHistorico
from compras.models import (ProcessoCompra, PedidoCompra, PedidoCompraItem, NegociacaoItem,
    AdjudicacaoCompra, AprovacaoCompra, HistoricoPrevisaoPedido)
from pos_obra.models import Chamado, AgendamentoOS, HistoricoAgendamento, PesquisaSatisfacao, MaterialOS


def percent(n, d):
    return f'{100 * n / d:.1f}%' if d else '—'


def days(value):
    return f'{value:.1f} dias' if value is not None else '—'


def rank(rows, name, value, limit=8, percentage=False):
    rows = list(rows)[:limit]
    highest = max((float(r[value] or 0) for r in rows), default=0)
    out = []
    for r in rows:
        num = float(r[value] or 0)
        label = str(r[name] or 'Não informado')
        out.append({'label':label, 'value':f'{num:.1f}%' if percentage else str(int(num)), 'raw':num,
                    'width':round(100*num/highest, 1) if highest else 0})
    return out


def project_details(qs, changes, f, card, panel, group):
    base=qs.exclude(status__in=['NAO_SE_APLICA'])
    pending=base.exclude(status__in=['FINALIZADO','RECEBIDO'])
    idle=pending.filter(atualizado_em__lt=timezone.make_aware(datetime.combine(timezone.localdate()-timedelta(days=30),time.min)))
    critical=pending.filter(item__grupo__tipo='DOCUMENTAL',item__entrega_atividade__iregex=r'ALVAR[AÁ]|HABITE|CND|AVERBA|CNO')
    rows=list(base.values('obra__nome').annotate(total=Count('id'),complete=Count('id', filter=Q(status__in=['FINALIZADO','RECEBIDO']))).order_by('obra__nome'))
    progress=sorted([{'label':r['obra__nome'] or 'Sem obra', 'value':f"{percent(r['complete'],r['total'])} ({r['complete']}/{r['total']})", 'raw':100*r['complete']/r['total'] if r['total'] else None,
               'width':round(100*r['complete']/r['total'],1) if r['total'] else 0} for r in rows],key=lambda r:r['width'])[:12]
    history=ChecklistProjetoHistorico.objects.filter(resposta__in=qs,campo='STATUS')
    history=range_dt(history,'alterado_em',f)
    revisions=history.values('resposta_id').annotate(n=Count('id')).filter(n__gte=2).count()
    critical_count = critical.count()
    return ([card('Documentos críticos pendentes',critical_count,'Critério textual: alvarás, CNO, habite-se, CND e averbações',severity='warning' if critical_count else None),
             card('Pendências sem atualização há 30 dias',idle.count(),'Situação atual dos itens incluídos no filtro'),
             card('Itens com múltiplas mudanças de status',revisions,'Duas ou mais mudanças no histórico')],
            [panel('Menor conclusão documental por obra',progress,'Percentual entre itens aplicáveis; até 12 obras com menor avanço.', chart=chart(unit='percent', precision=1, max=100, sort='asc')),
             panel('Pendências documentais críticas',group(critical,'item__entrega_atividade')),
             panel('Pendências por grupo',group(pending,'item__grupo__nome'))])


def work_details(fvs, itens, diarios, f, card, panel, group):
    evaluated=itens.filter(resultado__in=['C','NC'])
    by_executor=list(fvs.exclude(empresa_executora='').values('empresa_executora').annotate(
        inspected=Count('itens',filter=Q(itens__resultado__in=['C','NC'])),
        failures=Count('itens',filter=Q(itens__resultado='NC'))).filter(inspected__gt=0))
    executor_rows=sorted([{'label':r['empresa_executora'],'value':f"{percent(r['failures'],r['inspected'])} ({r['failures']}/{r['inspected']})", 'raw':100*r['failures']/r['inspected'],
                   'width':round(100*r['failures']/r['inspected'],1)} for r in by_executor],key=lambda r:r['width'],reverse=True)[:10]
    open_approval=fvs.filter(status='AGUARDANDO_APROVACAO').count()
    closed=fvs.filter(status='APROVADA')
    first_approval=closed.exclude(historico__acao='DEVOLVIDA').distinct().count()
    effective=diarios.exclude(efetivo__isnull=True).aggregate(v=Avg('efetivo'))['v']
    cautious=VistoriaCautelar.objects.all()
    if f['obra_id']: cautious=cautious.filter(obra_id=f['obra_id'])
    cautious=range_dt(cautious,'criado_em',f)
    occurrences=OcorrenciaCautelar.objects.filter(vistoria__in=cautious)
    movements=MovimentoEstoque.objects.filter(tipo='SAIDA')
    if f['obra_id']: movements=movements.filter(obra_origem_id=f['obra_id'])
    movements=range_dt(movements,'data_movimento',f)
    # Agrupamento por itens verificados evita confundir FVS com itens de inspeção.
    items_q=itens.filter(resultado='NC')
    return ([card('FVS aprovadas',closed.count()),
             card('FVS com data de fechamento',fvs.filter(data_fechamento__isnull=False).count()),
             card('Aprovadas sem devolução',first_approval,'FVS aprovadas sem evento DEVOLVIDA'),
             card('FVS aguardando aprovação',open_approval),
             card('Efetivo médio registrado',f'{effective:.1f}' if effective is not None else '—','Somente diários com efetivo informado'),
             card('Vistorias cautelares',cautious.count()),
             card('Ocorrências cautelares',occurrences.count())],
            [panel('Não conformidades por item de verificação',group(items_q,'item_verificacao'),
                   'Itens NC; a taxa por serviço exige classificação padronizada'),
             panel('Não conformidade por empresa executora',executor_rows,
                   'Itens NC / itens avaliados; até 10 empresas.', chart=chart(unit='percent', precision=1, max=100, sort='desc')),
             panel('FVS por empresa executora',group(fvs.exclude(empresa_executora=''),'empresa_executora')),
             panel('Saídas de materiais mais frequentes',group(movements,'descricao_item')),
             panel('Ocorrências cautelares por manifestação',group(occurrences,'manifestacao')),
             panel('Diários por obra',group(diarios,'obra__nome'))])


def supplier_details(processes, orders, f, card, panel, group):
    # Economias apenas em adjudicações válidas, evitando somar fornecedores perdedores.
    adj=AdjudicacaoCompra.objects.filter(cancelada=False,necessidade__processo__in=processes).select_related('item_cotado')
    original=Decimal('0'); negotiated=Decimal('0'); compared=0
    for row in adj.iterator(chunk_size=500):
        if not row.item_cotado_id: continue
        qty=Decimal(row.quantidade or 0)
        initial=Decimal(row.item_cotado.valor_unitario_cotado or 0)
        final=Decimal(row.valor_unitario_final or 0)
        # Sem referência de preço inicial positiva, não há economia comparável.
        if qty <= 0 or initial <= 0 or final < 0: continue
        original += qty*initial
        negotiated += qty*final
        compared+=1
    economy=original-negotiated
    completed=[]
    stage_durations={'Cotação':[],'Compatibilização':[],'Negociação':[],'Contratação':[]}
    fields=['data_cotacao_concluida','data_compatibilizacao_concluida','data_negociacao_concluida','data_contratacao_concluida']
    for p in processes.only('data_abertura', *fields).iterator(chunk_size=500):
        previous=p.data_abertura
        for label, field in zip(stage_durations,fields):
            dt=getattr(p,field)
            if dt:
                day=timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
                if previous and day >= previous: stage_durations[label].append((day-previous).days)
                previous=day
            else:
                previous=None
        if p.data_contratacao_concluida and p.data_abertura:
            dt=p.data_contratacao_concluida
            d=timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
            if d >= p.data_abertura: completed.append((d-p.data_abertura).days)
    stage_rows=[{'label':label,'value':days(sum(vals)/len(vals)) if vals else '—','width':0,'raw':sum(vals)/len(vals) if vals else None,'num':sum(vals)/len(vals) if vals else 0} for label,vals in stage_durations.items()]
    maximum=max((r['num'] for r in stage_rows),default=0)
    for r in stage_rows:r['width']=round(r.pop('num')*100/maximum,1) if maximum else 0
    today=timezone.localdate()
    delivered=orders.filter(status='ENTREGUE',recebido_em__isnull=False)
    punctual=0; late_days=[]; have_deadline=0
    for o in delivered.only('previsao_entrega_original','recebido_em').iterator(chunk_size=500):
        if not o.previsao_entrega_original: continue
        have_deadline+=1
        day=timezone.localtime(o.recebido_em).date() if timezone.is_aware(o.recebido_em) else o.recebido_em.date()
        delay=(day-o.previsao_entrega_original).days
        if delay<=0:punctual+=1
        else:late_days.append(delay)
    late_orders=orders.exclude(status='ENTREGUE').filter(Q(previsao_entrega_atual__lt=today)|Q(previsao_entrega_atual__isnull=True,previsao_entrega_original__lt=today))
    by_sup=list(orders.values('fornecedor_id','fornecedor__nome').annotate(total=Count('id'),late=Count('id',filter=Q(id__in=late_orders.values('id')))).filter(total__gte=1))
    # Evita destacar como 'pior fornecedor' quem possui só 1 ou 2 pedidos.
    poor=sorted([{'label':f"{r['fornecedor__nome']} (#{r['fornecedor_id']})",'raw':100*r['late']/r['total'],'value':f"{r['late']}/{r['total']} atrasados",'width':round(100*r['late']/r['total'],1)} for r in by_sup if r['total'] >= 3],key=lambda r:(r['width'],r['value']),reverse=True)[:10]
    approvals=AprovacaoCompra.objects.filter(processo__in=processes)
    revisions=HistoricoPrevisaoPedido.objects.filter(pedido__in=orders)
    revisions=range_dt(revisions,'criado_em',f)
    return ([card('Economia bruta de preços adjudicados',economy if compared else None,f'{compared} itens comparáveis; base R$ {original:.2f}. Exclui descontos de item/globais e frete; referência atual da cotação.',money=True),
             card('Variação bruta percentual',percent(economy,original),'Somente itens adjudicados comparáveis'),
             card('Tempo médio até contratar',days(sum(completed)/len(completed)) if completed else '—'),
             card('Entrega integral no prazo original',percent(punctual,have_deadline),f'{punctual} no prazo / {have_deadline} entregues com previsão original e recebimento'),
             card('Atraso médio nas entregas tardias',days(sum(late_days)/len(late_days)) if late_days else '—'),
             card('Reprogramações de entrega',revisions.count())],
            [panel('Tempo médio por etapa',stage_rows,'Dias corridos; somente extremos consecutivos presentes e não negativos.', chart=chart(unit='days', precision=1)),
             panel('Fornecedores com pedidos abertos atrasados',poor,'Vencidos / todos os pedidos não cancelados; mínimo 3 pedidos; até 10 fornecedores.', chart=chart(unit='percent', precision=1, max=100, sort='desc')),
             panel('Decisões de aprovação',group(approvals,'decisao')),
             panel('Compras por responsável',group(orders,'responsavel__username'))])


def post_details(qs, active, surveys, f, card, panel, group):
    closed=qs.filter(status='CONCLUIDO',finalizado_em__isnull=False)
    solved=[]; ontime=0; deadlines=0
    # Limita as leituras às colunas necessárias, não a relacionamentos pesados.
    for row in closed.only('criado_em','finalizado_em','prazo').iterator(chunk_size=500):
        if not row.criado_em:continue
        elapsed=(row.finalizado_em-row.criado_em).total_seconds()/86400
        if elapsed>=0:solved.append(elapsed)
        if row.prazo:
            deadlines+=1
            day=timezone.localtime(row.finalizado_em).date() if timezone.is_aware(row.finalizado_em) else row.finalizado_em.date()
            if day<=row.prazo:ontime+=1
    today=timezone.localdate()
    reference = timezone.now()
    age30=active.filter(criado_em__lt=reference-timedelta(days=30)).count()
    age60=active.filter(criado_em__lt=reference-timedelta(days=60)).count()
    age90=active.filter(criado_em__lt=reference-timedelta(days=90)).count()
    appointments=AgendamentoOS.objects.filter(chamado__in=qs)
    rescheduled=appointments.filter(Q(situacao__in=['REAGENDAMENTO','SUBSTITUIDO'])|Q(historico__para__in=['REAGENDAMENTO','SUBSTITUIDO'])).distinct().count()
    survey_avg=surveys.aggregate(att=Avg('atendimento'),due=Avg('prazo'),quality=Avg('qualidade'))
    survey_rows=[]
    for field,label in [('att','Atendimento'),('due','Cumprimento do prazo'),('quality','Qualidade do serviço')]:
        val=survey_avg[field]
        survey_rows.append({'label':label,'value':f'{val:.2f} / 5' if val is not None else '—',
                            'raw':number(val), 'width':round(val/5*100,1) if val is not None else 0})
    # Somente obras atuais têm contagem confiável de unidades; imóveis históricos não entram.
    by_obra=list(qs.filter(empreendimento__obra__quantidade_unidades__gt=0).values(
         'empreendimento__obra__nome','empreendimento__obra__quantidade_unidades').annotate(total=Count('id')))
    per100=sorted([{'label':r['empreendimento__obra__nome'] or 'Obra','value':f"{r['total']*100/r['empreendimento__obra__quantidade_unidades']:.1f}",
                   'raw':r['total']*100/r['empreendimento__obra__quantidade_unidades'], 'width':round(r['total']*100/r['empreendimento__obra__quantidade_unidades'],1)} for r in by_obra],key=lambda r:r['width'],reverse=True)[:10]
    peak=max((r['width'] for r in per100),default=0)
    for r in per100:r['width']=round(100*r['width']/peak,1) if peak else 0
    # Reincidência candidata: cliente + empreendimento + tipo + ambiente, mais de uma OS.
    recurrent=qs.exclude(status='CANCELADO').exclude(ambiente_padrao='').values('empreendimento_id','cliente_id','tipo_problema_id','ambiente_padrao').annotate(n=Count('id')).filter(n__gte=2).count()
    mat=MaterialOS.objects.filter(chamado__in=qs)
    cost=ExpressionWrapper(F('utilizado')*F('custo_unitario'),output_field=DecimalField(max_digits=26,decimal_places=4))
    material_by_type=mat.values('chamado__tipo_problema__nome').annotate(total=Sum(cost)).order_by('-total')[:8]
    maxcost=max((float(r['total'] or 0) for r in material_by_type),default=0)
    cost_rows=[{'label':r['chamado__tipo_problema__nome'] or 'Sem tipo','value':'R$ '+f"{r['total'] or 0:,.2f}".replace(',','@').replace('.',',').replace('@','.'),
                'raw':number(r['total']), 'width':round(float(r['total'] or 0)*100/maxcost,1) if maxcost else 0} for r in material_by_type]
    return ([card('Tempo médio de resolução',days(sum(solved)/len(solved)) if solved else '—','Somente OS concluídas com datas válidas'),
             card('Tempo mediano de resolução',days(median(solved)) if solved else '—','Metade das OS válidas é concluída até este tempo'),
             card('OS encerradas no prazo',percent(ontime,deadlines),'Somente encerradas com prazo cadastrado'),
             card('OS abertas há mais de 30 / 60 / 90 dias',f'{age30} / {age60} / {age90}','Duração superior a 30/60/90 períodos de 24h; contagens cumulativas da coorte filtrada'),
             card('Agendamentos remarcados',rescheduled,'Agendamentos com situação ou histórico de remarcação'),
             card('Possíveis grupos reincidentes',recurrent,'Mesmo cliente, empreendimento, tipo e ambiente; canceladas excluídas, sem comprovar retrabalho'),
             card('Pesquisas por OS concluída',percent(surveys.filter(chamado__status='CONCLUIDO').count(),qs.filter(status='CONCLUIDO').count()),'OS atualmente concluídas com pesquisa / OS concluídas; não é taxa de convite')],
            [panel('Notas médias da pesquisa',survey_rows,f'Escala de 1 a 5; {surveys.count()} respostas da coorte de abertura.', chart=chart(type='scatter',unit='score', precision=2, min=1, max=5)),
             panel('OS por 100 unidades (obras atuais)',per100,'OS / unidades × 100; não é percentual de imóveis afetados. Até 10 obras.', chart=chart(unit='rate', precision=1, sort='desc')),
             panel('Custo de materiais por tipo de problema',cost_rows,'Até 8 tipos; não inclui mão de obra, deslocamento ou terceirizados.', chart=chart(unit='currency', precision=2, sort='desc')),
             panel('Categorias de problema',group(qs,'tipo_problema__categoria__nome')),
             panel('OS por responsável',group(qs,'responsavel__username'))])
