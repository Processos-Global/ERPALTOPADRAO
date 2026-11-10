"""Indicadores estritamente derivados de dados já persistidos no SAARI.

Leitura apenas; sem migrar estruturas ou estimar dados faltantes.
"""
from collections import defaultdict
from datetime import date

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
    return round(float(value) * 100, 1) if value is not None else None


def _ranking(lines, limit=12):
    lines = list(lines)[:limit]
    peak = max((abs(float(x['raw'])) for x in lines), default=0)
    for x in lines:
        x['width'] = round(abs(float(x['raw'])) / peak * 100, 1) if peak else 0
    return lines


def _line(label, value, suffix='', precision=1):
    return {'label': label, 'value': f'{value:,.{precision}f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + suffix,
            'raw': round(value, precision)}


def planejamento(f, card, panel):
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
            if executed < planned - .1: late += 1
            if executed > planned + .1: ahead += 1
        cards.extend([
            card('Cronogramas acompanhados', len(snapshots), 'Último RESUMO GERAL por obra/projeto na importação ativa'),
            card('Cronogramas atrás do previsto', late, 'Comparação do avanço físico, não atraso confirmado da conclusão'),
            card('Cronogramas à frente', ahead, 'Avanço executado superior ao previsto'),
            card('Sem percentuais comparáveis', no_base, 'Sem base suficiente para comparação'),
        ])
        # Não sumarizamos percentuais de obras distintas como média da empresa:
        # os pesos e contratos não seriam comparáveis.
        rows=[]
        diffs=[]
        for row, executed, planned in qualified:
            name = row['obra__nome'] or row['projeto']
            if not row['obra_id']:
                name += ' (sem vínculo de obra)'
            rows.append({'label':name, 'value':f'{executed:.1f}%', 'raw': executed})
            diffs.append(_line(name, executed-planned))
        panels.append(panel('Avanço executado por obra', _ranking(sorted(rows, key=lambda x:x['label'])),
                            'Percentual executado do último resumo por obra/projeto; não é média do portfólio.'))
        panels.append(panel('Desvio físico por obra', _ranking(sorted(diffs, key=lambda x:x['raw'])),
                            'Pontos percentuais: executado menos previsto. Valor negativo indica atraso físico.'))

        # Marcos: apenas a semana mais recente de cada obra/projeto, jamais
        # contar todos os snapshots da importação como eventos novos.
        marks = list(base.filter(disciplina__iexact='MARCOS').values(
            'obra_id','projeto','semana','data_atualizacao','termino_base','termino_real',
            'percentual_concluida','percentual_executado'))
        total_mark=finished=overdue=finished_late=0
        for m in marks:
            key=(m['obra_id'],m['projeto'])
            if key not in latest: continue
            anchor=latest[key][1]
            if m['semana'] != anchor['semana']: continue
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
            card('Suprimentos programados',total,'Importação de suprimentos ativa'),
            card('Contratações realizadas',contracted,'Data real de contratação informada'),
            card('Contratações pendentes vencidas',delayed_open,'Prazo-limite anterior à data atual'),
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
    cards=[card('Previsão financeira ativa',previsto,'Por data prevista, não equivale a contas a pagar',True),
           card('Pagamentos efetivados',pago,'Por data de pagamento; estornos excluídos',True),
           card('Valor original dos títulos',total_titulo,'Por vencimento; não é saldo em aberto',True),
           card('Títulos vencidos',vencidos.count(),'Títulos não marcados como pagos'),
           card('Valor original dos títulos vencidos',vencido_valor,'Não representa saldo líquido devido',True)]
    # Sem snapshots históricos, não calcular "erro da previsão".
    planned=previsoes.values('data_prevista__year','data_prevista__month').annotate(v=Sum('valor_previsto'))
    actual=pagamentos.values('data_pagamento__year','data_pagamento__month').annotate(v=Sum('valor'))
    periods=defaultdict(lambda:{'previsto':0,'realizado':0})
    for r in planned:
        if r['data_prevista__year'] and r['data_prevista__month']:
            periods[(r['data_prevista__year'],r['data_prevista__month'])]['previsto']+=float(r['v'] or 0)
    for r in actual:
        if r['data_pagamento__year'] and r['data_pagamento__month']:
            periods[(r['data_pagamento__year'],r['data_pagamento__month'])]['realizado']+=float(r['v'] or 0)
    def fmt(v):return 'R$ '+f'{v:,.2f}'.replace(',','X').replace('.',',').replace('X','.')
    panels=[panel('Previsão financeira por mês',_ranking([
        {'label':f'{m:02d}/{y}','raw':values['previsto'],'value':fmt(values['previsto'])}
        for (y,m), values in sorted(periods.items())][-12:]),'Previsões ativas por data prevista.'),
        panel('Pagamentos efetivados por mês',_ranking([
        {'label':f'{m:02d}/{y}','raw':values['realizado'],'value':fmt(values['realizado'])}
        for (y,m), values in sorted(periods.items())][-12:]),'Somente pagamentos não estornados.'),
        panel('Previsões por nível de certeza',_ranking([
        {'label':r['certeza'] or 'Sem classificação','raw':float(r['v'] or 0),'value':fmt(float(r['v'] or 0))}
        for r in previsoes.values('certeza').annotate(v=Sum('valor_previsto')).order_by('-v')]),
        'Não somar novamente com os títulos e pagamentos.')]
    return cards,panels
