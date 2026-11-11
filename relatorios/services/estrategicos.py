"""Indicadores estritamente derivados de dados já persistidos no SAARI.

Leitura apenas; sem migrar estruturas ou estimar dados faltantes.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from relatorios.services.presentation import chart, number

from django.db.models import Count, Q, Sum
from django.utils import timezone

from planejamento.models import (
    ImportacaoCronograma, RegistroCronograma,
    ImportacaoCronogramaSuprimentos, ItemCronogramaSuprimento,
)
from financeiro.models import Pagamento, PrevisaoFinanceira, TituloPagar


def _num(value):
    return float(value) if value is not None else None


def _pct(value):
    """Os campos de progresso físico do cronograma estão em escala 0–1."""
    return Decimal(value) * 100 if value is not None else None


def _ranking(lines, limit=12):
    lines = list(lines)[:limit]
    peak = max((abs(float(x['raw'])) for x in lines), default=0)
    for x in lines:
        x['width'] = round(abs(float(x['raw'])) / peak * 100, 1) if peak else 0
    return lines


def _line(label, value, suffix='', precision=1):
    return {'label': label, 'value': f'{value:,.{precision}f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + suffix,
            'raw': number(value)}


def planejamento(f, card, panel, *, summary_only=False):
    """Só considera a importação física ativa e a importação ativa de suprimentos.

    Snapshot mais recente por (obra, projeto), evitando contar a mesma
    atividade repetidas vezes em semanas diferentes.
    """
    today = timezone.localdate()
    cards = []
    panels = []
    warning = []
    active = (ImportacaoCronograma.objects
              .filter(ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA)
              .order_by('-id').first())
    if active:
        base = RegistroCronograma.objects.filter(importacao=active)
        if f['obra_id']:
            base = base.filter(obra_id=f['obra_id'])
        # Data final é um recorte de estado (as-of); data inicial não restringe
        # o snapshot, pois removeria atividades anteriores ainda em execução.
        if f['fim']:
            base = base.filter(Q(data_atualizacao__lte=f['fim']) | Q(data_atualizacao__isnull=True))
        summaries = list(base.filter(disciplina__iexact='RESUMO GERAL').values(
            'id','obra_id','obra__nome','projeto','semana','data_atualizacao',
            'percentual_executado','percentual_previsto',
            'percentual_concluida','percentual_previsto_tarefa',
            'termino_base','termino_real'))
        latest = {}
        for record in summaries:
            key = (record['obra_id'], record['projeto'])
            rank = (record['data_atualizacao'] or date.min, record['semana'] or -1, record['id'])
            if key not in latest or rank > latest[key][0]:
                latest[key] = (rank, record)
        snapshots = [pair[1] for pair in latest.values()]
        qualified = []
        late = 0
        ahead = 0
        no_base = 0
        for row in snapshots:
            executed = _pct(row['percentual_executado'] if row['percentual_executado'] is not None else row['percentual_concluida'])
            planned = _pct(row['percentual_previsto'] if row['percentual_previsto'] is not None else row['percentual_previsto_tarefa'])
            if executed is None or planned is None:
                no_base += 1
                continue
            qualified.append((row, executed, planned))
            if executed < planned: late += 1
            if executed > planned: ahead += 1
        cards.extend([
            card('Cronogramas acompanhados', len(snapshots), 'Último RESUMO GERAL por obra/projeto na importação ativa'),
            card('Cronogramas atrás do previsto', late, 'Comparação do avanço físico, não atraso confirmado da conclusão', severity='warning' if late else None),
            card('Cronogramas à frente', ahead, 'Avanço executado superior ao previsto'),
            card('Sem percentuais comparáveis', no_base, 'Sem base suficiente para comparação'),
        ])
        if summary_only:
            return cards, [], ''
        # Não sumarizamos percentuais de obras distintas como média da empresa:
        # os pesos e contratos não seriam comparáveis.
        rows=[]
        diffs=[]
        for row, executed, planned in qualified:
            name = f"{row['obra__nome'] or 'Sem obra'} · {row['projeto']}"
            if not row['obra_id']:
                name += ' (sem vínculo de obra)'
            rows.append({'label':name, 'value':f'{executed:.1f}%', 'raw': number(executed)})
            diffs.append(_line(name, executed-planned, ' p.p.'))
        panels.append(panel('Desvio físico por obra', _ranking(sorted(diffs, key=lambda x:x['raw'])),
                            'Executado menos previsto; até 12 obras/projetos com menor desvio.', chart=chart(unit='percentage_point', precision=1, min=None, negative=True, sort='asc')))
        comparison = sorted(qualified, key=lambda item: (item[0]['obra__nome'] or '', item[0]['projeto']))[:12]
        comparison_rows = [{'label':f"{r['obra__nome'] or 'Sem obra'} · {r['projeto']}", 'value':f'{e:.1f}%', 'raw':number(e), 'width':0} for r,e,p in comparison]
        panels.append(panel('Previsto e executado por obra/projeto', comparison_rows, 'Último resumo; até 12 obras/projetos.', chart=chart(unit='percent', precision=1, max=100), series=[{'name':'Previsto','values':[number(p) for r,e,p in comparison]}, {'name':'Executado','values':[number(e) for r,e,p in comparison]}]))
        dated = {}
        for r in sorted(summaries, key=lambda item:(item['semana'] or -1,item['id'])):
            if r['data_atualizacao'] is not None:
                if f['inicio'] and r['data_atualizacao'] < f['inicio']:
                    continue
                key=(r['obra_id'],r['projeto'])
                dated.setdefault(key,{})[r['data_atualizacao']]=r
        histories = [(key,points) for key,points in sorted(dated.items(), key=lambda item:str(item[0])) if len(points)>1]
        for key, points in histories[:3]:
            selected=sorted(points.items())[-12:]
            rows_history=[]; planned_history=[]; executed_history=[]
            for dt,r in selected:
                e=_pct(r['percentual_executado'] if r['percentual_executado'] is not None else r['percentual_concluida'])
                p=_pct(r['percentual_previsto'] if r['percentual_previsto'] is not None else r['percentual_previsto_tarefa'])
                rows_history.append({'label':dt.isoformat(),'value':f'{e:.1f}%' if e is not None else '—','raw':number(e),'width':0})
                planned_history.append(number(p)); executed_history.append(number(e))
            panels.append(panel(f"Evolução física · {selected[-1][1]['obra__nome'] or 'Sem obra'} · {key[1]}", rows_history, 'Até 3 cronogramas por identificação e 12 datas no período; somente observações da importação ativa, sem interpolação.', chart=chart(orientation='vertical', unit='percent', precision=1, max=100, sort='chronological', allowed_types=['bar']), series=[{'name':'Previsto','values':planned_history},{'name':'Executado','values':executed_history}]))

        # Marcos: apenas a semana mais recente de cada obra/projeto, jamais
        # contar todos os snapshots da importação como eventos novos.
        marks = list(base.filter(disciplina__iexact='MARCOS').values(
            'id','chave_atividade','local_tarefa','nome_tarefa','obra_id','projeto','semana','data_atualizacao','termino_base','termino_real',
            'percentual_concluida','percentual_executado'))
        total_mark=finished=overdue=finished_late=0
        unique_marks = {}
        for m in marks:
            key=(m['obra_id'],m['projeto'])
            if key not in latest: continue
            anchor=latest[key][1]
            if (m['semana'],m['data_atualizacao']) != (anchor['semana'],anchor['data_atualizacao']): continue
            identity=m['chave_atividade'] or (m['local_tarefa'],m['nome_tarefa'])
            if not identity or identity == ('',''):
                identity=('unidentified',m['id'])
            mark_key=(key,identity)
            if mark_key not in unique_marks or m['id'] > unique_marks[mark_key]['id']:
                unique_marks[mark_key]=m
        for m in unique_marks.values():
            total_mark+=1
            value = m['percentual_concluida'] if m['percentual_concluida'] is not None else m['percentual_executado']
            complete = value is not None and float(value)>=.999
            if complete:
                finished+=1
                if m['termino_base'] and m['termino_real'] and m['termino_real']>m['termino_base']:
                    finished_late+=1
            elif m['termino_base'] and m['termino_base'] < (m['data_atualizacao'] or today):
                overdue+=1
        cards.extend([
            card('Marcos registrados',total_mark,'Somente o último snapshot de cada cronograma'),
            card('Marcos concluídos',finished),
            card('Marcos pendentes atrasados',overdue,'Prazo-base anterior à data de referência'),
            card('Marcos concluídos com atraso',finished_late,'Data real posterior à data-base'),
        ])
        panels.append(panel('Situação dos marcos',_ranking([
            {'label':'Concluídos','value':str(finished),'raw':finished},
            {'label':'Pendentes atrasados','value':str(overdue),'raw':overdue},
            {'label':'Outros pendentes','value':str(max(total_mark-finished-overdue,0)),'raw':max(total_mark-finished-overdue,0)},
        ]),'Última semana por cronograma; classificação conforme datas e percentuais armazenados.'))
    else:
        warning.append('Cronograma físico sem importação ativa concluída.')

    if summary_only:
        return cards, [], ' '.join(warning)
    supply = (ImportacaoCronogramaSuprimentos.objects
              .filter(ativa=True, status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA)
              .order_by('-id').first())
    if supply:
        qs = ItemCronogramaSuprimento.objects.filter(cronograma_obra__importacao=supply)
        if f['obra_id']:
            qs = qs.filter(cronograma_obra__obra_id=f['obra_id'])
        if f['fim']:
            qs = qs.filter(Q(prazo_limite_contratacao__lte=f['fim']) | Q(prazo_limite_contratacao__isnull=True))
        total = qs.count()
        done = qs.filter(data_real_contratacao__isnull=False)
        contracted = done.count()
        delayed_open = qs.filter(data_real_contratacao__isnull=True,prazo_limite_contratacao__lt=today).count()
        contracted_late = done.filter(data_real_contratacao__gt=django_f('prazo_limite_contratacao')).count()
        cards.extend([
            card('Suprimentos programados',total,'Importação ativa; data final filtra prazo-limite, não estado histórico'),
            card('Contratações realizadas',contracted,'Data real de contratação informada'),
            card('Contratações pendentes vencidas',delayed_open,'Prazo-limite anterior à data atual',severity='warning' if delayed_open else None),
            card('Contratações realizadas fora do prazo',contracted_late,'Data real posterior ao prazo-limite'),
        ])
        by_work = qs.filter(data_real_contratacao__isnull=True,prazo_limite_contratacao__lt=today).values(
            'cronograma_obra__obra__nome').annotate(n=Count('pk')).order_by('-n')[:12]
        panels.append(panel('Contratações pendentes vencidas por obra', _ranking([
            {'label':r['cronograma_obra__obra__nome'] or 'Sem obra','value':str(r['n']),'raw':r['n']}
            for r in by_work]), 'Prazo-base vencido e sem data real de contratação.'))
        by_category = qs.values('categoria').annotate(n=Count('pk')).order_by('-n')[:12]
        panels.append(panel('Suprimentos programados por categoria',_ranking([
            {'label':r['categoria'] or 'Sem categoria','value':str(r['n']),'raw':r['n']}
            for r in by_category]), 'Itens da importação ativa.'))
    else:
        warning.append('Cronograma de suprimentos sem importação ativa concluída.')
    return cards, panels, ' '.join(warning)


def django_f(field):
    from django.db.models import F
    return F(field)


def financeiro(f, card, panel):
    """Separar previsão, obrigação e pagamento: não somar como despesas."""
    previsoes=PrevisaoFinanceira.objects.filter(ativa=True)
    titulos=TituloPagar.objects.exclude(status__in=[TituloPagar.Status.CANCELADO, TituloPagar.Status.REJEITADO])
    pagamentos=Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO)
    if f['obra_id']:
        previsoes=previsoes.filter(obra_id=f['obra_id'])
        titulos=titulos.filter(obra_id=f['obra_id'])
        pagamentos=pagamentos.filter(titulo__obra_id=f['obra_id'])
    for field, qs in [('data_prevista',previsoes),('vencimento',titulos),('data_pagamento',pagamentos)]:
        if f['inicio']:
            qs=qs.filter(**{field+'__gte':f['inicio']})
        if f['fim']:
            qs=qs.filter(**{field+'__lte':f['fim']})
        if field=='data_prevista': previsoes=qs
        elif field=='vencimento': titulos=qs
        else: pagamentos=qs
    previsto=previsoes.aggregate(v=Sum('valor_previsto'))['v'] or 0
    pago=pagamentos.aggregate(v=Sum('valor'))['v'] or 0
    total_titulo=titulos.aggregate(v=Sum('valor_original'))['v'] or 0
    today=timezone.localdate()
    vencidos=titulos.exclude(status=TituloPagar.Status.PAGO).filter(vencimento__lt=today)
    vencido_valor=vencidos.aggregate(v=Sum('valor_original'))['v'] or 0
    balance = overdue_balance = liquid = Decimal('0')
    inconsistent = no_due = overdue_count = 0
    for title in titulos.select_related('pagamento').iterator(chunk_size=500):
        net = title.valor_liquido
        remaining = title.saldo_aberto
        paid = title.total_pago
        balance += remaining
        liquid += net
        if title.vencimento is None:
            no_due += 1
        if title.vencimento and title.vencimento < today and remaining > 0:
            overdue_balance += remaining
            overdue_count += 1
        if ((title.status == TituloPagar.Status.PAGO) != (paid > 0)) or (paid > 0 and paid != net):
            inconsistent += 1
    cards=[card('Previsão financeira ativa',previsto,'Por data prevista, não equivale a contas a pagar',True),
           card('Pagamentos efetivados',pago,'Por data de pagamento; estornos excluídos',True),
           card('Valor original dos títulos',total_titulo,'Por vencimento; não é saldo em aberto',True),
           card('Títulos vencidos',vencidos.count(),'Títulos não marcados como pagos'),
           card('Valor original dos títulos vencidos',vencido_valor,'Não representa saldo líquido devido',True)]
    cards = [card('Saldo em aberto',balance,'Líquido menos pagamento atualmente efetivado; por vencimento',True),
             card('Saldo vencido',overdue_balance,'Saldo positivo com vencimento anterior a hoje',True,severity='warning' if overdue_balance > 0 else None),
             card('Obrigações líquidas',liquid,'Original + acréscimos − desconto monetário, limitado a zero por título',True),
             card('Títulos com saldo vencido',overdue_count,severity='warning' if overdue_count else None)] + cards
    cards += [card('Títulos sem vencimento',no_due,'No universo filtrado; filtros de data excluem vencimentos nulos'),
              card('Inconsistências de pagamento',inconsistent,'Divergência entre status, pagamento efetivado e valor líquido',severity='warning' if inconsistent else None)]
    # Sem snapshots históricos, não calcular "erro da previsão".
    planned=previsoes.values('data_prevista__year','data_prevista__month').annotate(v=Sum('valor_previsto'))
    actual=pagamentos.values('data_pagamento__year','data_pagamento__month').annotate(v=Sum('valor'))
    periods=defaultdict(lambda:{'previsto':Decimal('0'),'realizado':Decimal('0')})
    for r in planned:
        if r['data_prevista__year'] and r['data_prevista__month']:
            periods[(r['data_prevista__year'],r['data_prevista__month'])]['previsto']+=r['v'] or Decimal('0')
    for r in actual:
        if r['data_pagamento__year'] and r['data_pagamento__month']:
            periods[(r['data_pagamento__year'],r['data_pagamento__month'])]['realizado']+=r['v'] or Decimal('0')
    # Contiguous calendar months: absent activity is zero, not a skipped interval.
    if periods:
        first, last = min(periods), max(periods)
        last_index = last[0] * 12 + last[1] - 1
        first_index = max(first[0] * 12 + first[1] - 1, last_index - 11)
        periods = {(index // 12, index % 12 + 1): periods[(index // 12, index % 12 + 1)]
                   for index in range(first_index, last_index + 1)}
    def fmt(v):return 'R$ '+f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    panels=[panel('Previsão financeira por mês',_ranking([
        {'label':f'{m:02d}/{y}','raw':number(values['previsto']),'value':fmt(values['previsto'])}
        for (y,m), values in sorted(periods.items())][-12:]),'Até 12 meses consecutivos; previsões ativas por data prevista.', chart=chart(type='line', orientation='vertical', unit='currency', precision=2, sort='chronological', allowed_types=['line','bar'])),
        panel('Pagamentos efetivados por mês',_ranking([
        {'label':f'{m:02d}/{y}','raw':number(values['realizado']),'value':fmt(values['realizado'])}
        for (y,m), values in sorted(periods.items())][-12:]),'Até 12 meses consecutivos; pagamentos atualmente não estornados.', chart=chart(type='line', orientation='vertical', unit='currency', precision=2, sort='chronological', allowed_types=['line','bar'])),
        panel('Previsões por nível de certeza',_ranking([
        {'label':r['certeza'] or 'Sem classificação','raw':float(r['v'] or 0),'value':fmt(r['v'] or 0)}
        for r in previsoes.values('certeza').annotate(v=Sum('valor_previsto')).order_by('-v')]),
        'Não somar novamente com os títulos e pagamentos.', chart=chart(unit='currency', precision=2, sort='desc'))]
    return cards,panels
