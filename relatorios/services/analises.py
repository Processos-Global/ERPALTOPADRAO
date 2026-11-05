"""Indicadores gerenciais adicionais: nenhuma alteração de dados/banco."""
from datetime import timedelta, datetime, time
from decimal import Decimal
from statistics import median
from django.db.models import Avg, Count, F, Q, Sum, ExpressionWrapper, DecimalField
from django.utils import timezone
from obras.models import FVSItem, FVSHistorico, DiarioObra, MovimentoEstoque, VistoriaCautelar, OcorrenciaCautelar, Obra
from projetos.models import ChecklistProjetoHistorico
from compras.models import (ProcessoCompra, PedidoCompra, PedidoCompraItem, NegociacaoItem,
    AdjudicacaoCompra, AprovacaoCompra, HistoricoPrevisaoPedido)
from pos_obra.models import Chamado, AgendamentoOS, HistoricoAgendamento, PesquisaSatisfacao, MaterialOS


def range_dt(qs, field, f):
    if f['inicio']:
        qs=qs.filter(**{field+'__gte':timezone.make_aware(datetime.combine(f['inicio'],time.min))})
    if f['fim']:
        qs=qs.filter(**{field+'__lt':timezone.make_aware(datetime.combine(f['fim']+timedelta(days=1),time.min))})
    return qs

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
        out.append({'label':label, 'value':f'{num:.1f}%' if percentage else str(int(num)),
                    'width':round(100*num/highest, 1) if highest else 0})
    return out


def project_details(qs, changes, f, card, panel, group):
    base=qs.exclude(status__in=['NAO_SE_APLICA'])
    pending=base.exclude(status__in=['FINALIZADO','RECEBIDO'])
    idle=pending.filter(atualizado_em__lt=timezone.make_aware(datetime.combine(timezone.localdate()-timedelta(days=30),time.min)))
    critical=pending.filter(item__grupo__tipo='DOCUMENTAL',item__entrega_atividade__iregex=r'ALVAR[AÁ]|HABITE|CND|AVERBA|CNO')
    rows=list(base.values('obra__nome').annotate(total=Count('id'),complete=Count('id', filter=Q(status__in=['FINALIZADO','RECEBIDO']))).order_by('obra__nome'))
    progress=sorted([{'label':r['obra__nome'] or 'Sem obra', 'value':percent(r['complete'],r['total']),
               'width':round(100*r['complete']/r['total'],1) if r['total'] else 0} for r in rows],key=lambda r:r['width'])[:12]
    history=ChecklistProjetoHistorico.objects.filter(resposta__in=qs,campo='STATUS')
    history=range_dt(history,'alterado_em',f)
    revisions=history.values('resposta_id').annotate(n=Count('id')).filter(n__gte=2).count()
    return ([card('Documentos críticos pendentes',critical.count(),'Alvarás, CNO, habite-se, CND e averbações'),
             card('Pendências sem atualização há 30 dias',idle.count(),'Situação atual dos itens incluídos no filtro'),
             card('Itens com múltiplas mudanças de status',revisions,'Duas ou mais mudanças no histórico')],
            [panel('Menor conclusão documental por obra',progress,'Percentual entre itens aplicáveis; obras com menor avanço primeiro'),
             panel('Pendências documentais críticas',group(critical,'item__entrega_atividade')),
             panel('Pendências por grupo',group(pending,'item__grupo__nome'))])


def work_details(fvs, itens, diarios, f, card, panel, group):
    evaluated=itens.filter(resultado__in=['C','NC'])
    by_executor=list(fvs.exclude(empresa_executora='').values('empresa_executora').annotate(
        inspected=Count('itens',filter=Q(itens__resultado__in=['C','NC'])),
        failures=Count('itens',filter=Q(itens__resultado='NC'))).filter(inspected__gt=0))
    executor_rows=sorted([{'label':r['empresa_executora'],'value':percent(r['failures'],r['inspected']),
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
    return ([card('FVS com fechamento',closed.count()),
             card('Aprovadas sem devolução',first_approval,'FVS aprovadas sem evento DEVOLVIDA'),
             card('FVS aguardando aprovação',open_approval),
             card('Efetivo médio registrado',f'{effective:.1f}' if effective is not None else '—','Somente diários com efetivo informado'),
             card('Vistorias cautelares',cautious.count()),
             card('Ocorrências cautelares',occurrences.count())],
            [panel('Não conformidades por item de verificação',group(items_q,'item_verificacao'),
                   'Itens NC; a taxa por serviço exige classificação padronizada'),
             panel('Não conformidade por empresa executora',executor_rows,
                   'Percentual de itens NC / itens avaliados da empresa; não é total absoluto'),
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
        if p.data_contratacao_concluida and p.data_abertura:
            dt=p.data_contratacao_concluida
            d=timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()
            if d >= p.data_abertura: completed.append((d-p.data_abertura).days)
    stage_rows=[{'label':label,'value':days(sum(vals)/len(vals)) if vals else '—','width':0,'num':sum(vals)/len(vals) if vals else 0} for label,vals in stage_durations.items()]
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
    by_sup=list(orders.values('fornecedor__nome').annotate(total=Count('id'),late=Count('id',filter=Q(id__in=late_orders.values('id')))).filter(total__gte=1))
    # Evita destacar como 'pior fornecedor' quem possui só 1 ou 2 pedidos.
    poor=sorted([{'label':r['fornecedor__nome'] or 'Não informado','value':f"{r['late']}/{r['total']} atrasados",'width':round(100*r['late']/r['total'],1)} for r in by_sup if r['total'] >= 3],key=lambda r:(r['width'],r['value']),reverse=True)[:10]
    approvals=AprovacaoCompra.objects.filter(processo__in=processes)
    revisions=HistoricoPrevisaoPedido.objects.filter(pedido__in=orders)
    revisions=range_dt(revisions,'criado_em',f)
    return ([card('Economia negociada comparável',economy,f'Cotação inicial menos adjudicação final; {compared} itens com preço-base válido, sem frete/desconto global',money=True),
             card('Economia percentual',percent(economy,original),'Somente itens adjudicados comparáveis'),
             card('Tempo médio até contratar',days(sum(completed)/len(completed)) if completed else '—'),
             card('Entrega integral no prazo original',percent(punctual,have_deadline),'Pedidos entregues com previsão e data de recebimento'),
             card('Atraso médio nas entregas tardias',days(sum(late_days)/len(late_days)) if late_days else '—'),
             card('Reprogramações de entrega',revisions.count())],
            [panel('Tempo médio por etapa',stage_rows,'Dias corridos; datas de conclusão registradas no processo'),
             panel('Fornecedores com pedidos abertos atrasados',poor,'Pedidos vencidos / total de pedidos não cancelados do fornecedor no filtro; mínimo de 3 pedidos'),
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
    age30=active.filter(criado_em__lt=timezone.make_aware(datetime.combine(today-timedelta(days=29),time.min))).count()
    age60=active.filter(criado_em__lt=timezone.make_aware(datetime.combine(today-timedelta(days=59),time.min))).count()
    age90=active.filter(criado_em__lt=timezone.make_aware(datetime.combine(today-timedelta(days=89),time.min))).count()
    appointments=AgendamentoOS.objects.filter(chamado__in=qs)
    rescheduled=appointments.filter(Q(situacao__in=['REAGENDAMENTO','SUBSTITUIDO'])|Q(historico__para__in=['REAGENDAMENTO','SUBSTITUIDO'])).distinct().count()
    survey_avg=surveys.aggregate(att=Avg('atendimento'),due=Avg('prazo'),quality=Avg('qualidade'))
    survey_rows=[]
    for field,label in [('att','Atendimento'),('due','Cumprimento do prazo'),('quality','Qualidade do serviço')]:
        val=survey_avg[field]
        survey_rows.append({'label':label,'value':f'{val:.2f} / 5' if val is not None else '—',
                            'width':round(val/5*100,1) if val is not None else 0})
    # Somente obras atuais têm contagem confiável de unidades; imóveis históricos não entram.
    by_obra=list(qs.filter(empreendimento__obra__quantidade_unidades__gt=0).values(
         'empreendimento__obra__nome','empreendimento__obra__quantidade_unidades').annotate(total=Count('id')))
    per100=sorted([{'label':r['empreendimento__obra__nome'] or 'Obra','value':f"{r['total']*100/r['empreendimento__obra__quantidade_unidades']:.1f}",
                   'width':round(r['total']*100/r['empreendimento__obra__quantidade_unidades'],1)} for r in by_obra],key=lambda r:r['width'],reverse=True)[:10]
    peak=max((r['width'] for r in per100),default=0)
    for r in per100:r['width']=round(100*r['width']/peak,1) if peak else 0
    # Reincidência candidata: cliente + empreendimento + tipo + ambiente, mais de uma OS.
    recurrent=qs.exclude(ambiente_padrao='').values('empreendimento_id','cliente_id','tipo_problema_id','ambiente_padrao').annotate(n=Count('id')).filter(n__gte=2).count()
    mat=MaterialOS.objects.filter(chamado__in=qs)
    cost=ExpressionWrapper(F('utilizado')*F('custo_unitario'),output_field=DecimalField(max_digits=26,decimal_places=4))
    material_by_type=mat.values('chamado__tipo_problema__nome').annotate(total=Sum(cost)).order_by('-total')[:8]
    maxcost=max((float(r['total'] or 0) for r in material_by_type),default=0)
    cost_rows=[{'label':r['chamado__tipo_problema__nome'] or 'Sem tipo','value':'R$ '+f"{r['total'] or 0:,.2f}".replace(',','@').replace('.',',').replace('@','.'),
                'width':round(float(r['total'] or 0)*100/maxcost,1) if maxcost else 0} for r in material_by_type]
    return ([card('Tempo médio de resolução',days(sum(solved)/len(solved)) if solved else '—','Somente OS concluídas com datas válidas'),
             card('Tempo mediano de resolução',days(median(solved)) if solved else '—','Metade das OS válidas é concluída até este tempo'),
             card('OS encerradas no prazo',percent(ontime,deadlines),'Somente encerradas com prazo cadastrado'),
             card('OS abertas há mais de 30 / 60 / 90 dias',f'{age30} / {age60} / {age90}','Contagens cumulativas da coorte filtrada'),
             card('Agendamentos remarcados',rescheduled,'Agendamentos com situação ou histórico de remarcação'),
             card('Possíveis grupos reincidentes',recurrent,'Mesmo cliente, empreendimento, tipo e ambiente'),
             card('Pesquisas por OS concluída',percent(surveys.values('chamado_id').distinct().count(),qs.filter(status='CONCLUIDO').count()),'OS distintas com pesquisa / OS concluídas no filtro; não é taxa de convite')],
            [panel('Notas médias da pesquisa',survey_rows,'Escala original de 1 a 5'),
             panel('OS por 100 unidades (obras atuais)',per100,'Históricos sem quantidade de unidades são excluídos; filtro por abertura'),
             panel('Custo de materiais por tipo de problema',cost_rows,'Não inclui mão de obra, deslocamento ou terceirizados'),
             panel('Tipos de problema mais frequentes',group(qs,'tipo_problema__categoria__nome')),
             panel('OS por responsável',group(qs,'responsavel__username')),
             panel('Resolução declarada pelo cliente',group(surveys,'resolvido'))])
