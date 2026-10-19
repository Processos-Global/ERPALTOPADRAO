from collections import defaultdict
from datetime import date
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from financeiro.models import Pagamento, TituloPagar, PlanoFinanceiro, AprovacaoTituloFinanceiro
from obras.models import Obra

GRUPOS = (
 ('Imóvel', ('1',)), ('Administração', ('2','3')),
 ('Taxas de projeto', ('4',)), ('Mão de obra', ('6','7.1','8.1','9.1')),
 ('Grandes fornecedores', ('10',)), ('Materiais', ('12','13')),
)

def classe_do_codigo(codigo):
    codigo = str(codigo or '').strip()
    for nome, codigos in GRUPOS:
        if any(codigo == c or codigo.startswith(c+'.') for c in codigos):
            return nome
    return 'Não agrupado'

def _filtros(qs, prefixo='', obra_ids=None, classe=None, apropriacao=None, fornecedor=None):
    if obra_ids:
        qs = qs.filter(**{f'{prefixo}obra_id__in': obra_ids})
    if fornecedor:
        qs = qs.filter(**{f'{prefixo}fornecedor_id': fornecedor})
    if apropriacao:
        qs = qs.filter(**{f'{prefixo}plano_financeiro_id': apropriacao})
    elif classe:
        # Inclui todos os descendentes de uma classe, não só filhos diretos.
        from financeiro.models import PlanoFinanceiro
        ids = {int(classe)}
        novos = ids
        while novos:
            novos = set(PlanoFinanceiro.objects.filter(pai_id__in=novos).values_list('pk', flat=True)) - ids
            ids.update(novos)
        qs = qs.filter(**{f'{prefixo}plano_financeiro_id__in': ids})
    return qs

def indicadores_gerenciais(inicio, fim, obra_ids=None, classe=None, apropriacao=None, fornecedor=None):
    obra_ids = list(obra_ids or [])
    titulos = TituloPagar.objects.filter(criado_em__date__range=(inicio,fim)).select_related('plano_financeiro')
    pagamentos = Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO,data_pagamento__range=(inicio,fim)).select_related('titulo__plano_financeiro','titulo__obra')
    aprovacoes = AprovacaoTituloFinanceiro.objects.filter(decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,criado_em__date__range=(inicio,fim)).select_related('titulo__plano_financeiro')
    titulos = _filtros(titulos, obra_ids=obra_ids, classe=classe, apropriacao=apropriacao, fornecedor=fornecedor)
    pagamentos = _filtros(pagamentos, "titulo__", obra_ids, classe, apropriacao, fornecedor)
    aprovacoes = _filtros(aprovacoes, "titulo__", obra_ids, classe, apropriacao, fornecedor)
    valores=defaultdict(lambda: {'lancado':Decimal('0'),'aprovado':Decimal('0'),'pago':Decimal('0')})
    def codigo(titulo):
        return titulo.plano_financeiro.codigo if titulo.plano_financeiro else ''
    for t in titulos:
        valores[classe_do_codigo(codigo(t))]['lancado'] += t.valor_original
    # Apuração de aprovações distintas evita duplicar mesmo título aprovado duas vezes no período.
    vistos=set()
    for a in aprovacoes.order_by('criado_em','pk'):
        if a.titulo_id in vistos: continue
        vistos.add(a.titulo_id)
        valores[classe_do_codigo(codigo(a.titulo))]['aprovado'] += a.titulo.valor_original
    por_obra=defaultdict(lambda:defaultdict(lambda:Decimal('0')))
    for p in pagamentos:
        categoria=classe_do_codigo(codigo(p.titulo))
        valores[categoria]['pago'] += p.valor
        por_obra[p.titulo.obra_id][categoria] += p.valor
    area_total=Decimal('0')
    if obra_ids:
        obras=Obra.objects.filter(pk__in=obra_ids)
    else:
        obras=Obra.objects.filter(pk__in=[pk for pk in por_obra if pk])
    obras=list(obras)
    # Sem área cadastrada não há custo/m² válido; não incluir os respectivos custos.
    areas={o.pk:o.area_construida for o in obras if o.area_construida and o.area_construida>0}
    area_total=sum(areas.values(),Decimal('0'))
    taxas={}
    for grupo in ('Mão de obra','Grandes fornecedores','Materiais'):
        custo=sum((por_obra[pk][grupo] for pk in areas),Decimal('0'))
        taxas[grupo]=custo/area_total if area_total else None
    faltantes=[o.nome for o in obras if not o.area_construida or o.area_construida<=0]
    detalhe_obras = []
    for o in obras:
        area = areas.get(o.pk)
        detalhe_obras.append({
            'nome': o.nome, 'area': area,
            'mao_obra': (por_obra[o.pk]['Mão de obra'] / area) if area else None,
            'fornecedores': (por_obra[o.pk]['Grandes fornecedores'] / area) if area else None,
            'materiais': (por_obra[o.pk]['Materiais'] / area) if area else None,
        })
    categorias = [{'nome': nome, **valores[nome]} for nome, _ in GRUPOS]
    if any(valores['Não agrupado'].values()):
        categorias.append({'nome': 'Não agrupado', **valores['Não agrupado']})
    totais = {col: sum((r[col] for r in categorias), Decimal('0')) for col in ('lancado', 'aprovado', 'pago')}
    return {'categorias': categorias, 'totais': totais, 'area_total': area_total,
            'custos_m2': taxas, 'obras_sem_area': faltantes, 'detalhe_obras': detalhe_obras}


def desembolso_mensal(inicio=None, meses=6, obra_ids=None, classe=None, apropriacao=None, fornecedor=None):
    """Contas aprovadas/em aberto e previsões não formalizadas sem contar a compra duas vezes."""
    from collections import defaultdict
    from datetime import date
    from calendar import monthrange
    from financeiro.services.fluxo_caixa import STATUS_ABERTOS
    from financeiro.models import PrevisaoFinanceira
    inicio=inicio or timezone.localdate()
    obra_ids=list(obra_ids or [])
    ano,mes=inicio.year,inicio.month
    meses_chaves=[]
    for i in range(meses):
        y=ano+(mes-1+i)//12
        m=(mes-1+i)%12+1
        meses_chaves.append((y,m))
    fim=date(meses_chaves[-1][0],meses_chaves[-1][1],monthrange(*meses_chaves[-1])[1])
    titulos=TituloPagar.objects.filter(status__in=STATUS_ABERTOS,vencimento__range=(inicio,fim)).select_related('pagamento')
    previsoes=PrevisaoFinanceira.objects.filter(ativa=True,data_prevista__range=(inicio,fim)).exclude(origem=PrevisaoFinanceira.Origem.COMPRA)
    titulos = _filtros(titulos, obra_ids=obra_ids, classe=classe, apropriacao=apropriacao, fornecedor=fornecedor)
    previsoes = _filtros(previsoes, obra_ids=obra_ids, classe=classe,
                       apropriacao=apropriacao, fornecedor=fornecedor)
    totais=defaultdict(lambda:Decimal('0'))
    for t in titulos: totais[(t.vencimento.year,t.vencimento.month)]+=t.saldo_aberto
    for p in previsoes: totais[(p.data_prevista.year,p.data_prevista.month)]+=p.valor_previsto
    acumulado=Decimal('0')
    resultado=[]
    for y,m in meses_chaves:
        valor=totais[(y,m)]
        acumulado+=valor
        resultado.append({'mes':f'{m:02d}/{y}','valor':valor,'acumulado':acumulado})
    return resultado


def forecast_mensal_por_categoria(inicio, fim, obra_ids=None, classe=None, apropriacao=None, fornecedor=None):
    """Histórico por competência do evento: cadastro, decisão de aprovação, quitação.

    As três etapas não são somadas entre si: cada coluna representa seu próprio evento.
    """
    from django.db.models.functions import TruncMonth
    from financeiro.models import Pagamento
    from collections import defaultdict
    obra_ids=list(obra_ids or [])
    valores=defaultdict(lambda: {'lancado':Decimal('0'),'aprovado':Decimal('0'),'pago':Decimal('0')})
    def acumular(data, titulo, tipo, valor):
        if not data:return
        chave=(data.year,data.month,classe_do_codigo(titulo.plano_financeiro.codigo if titulo.plano_financeiro else None))
        valores[chave][tipo]+=valor
    lancados=TituloPagar.objects.filter(criado_em__date__range=(inicio,fim)).select_related('plano_financeiro')
    aprovacoes=AprovacaoTituloFinanceiro.objects.filter(decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,criado_em__date__range=(inicio,fim)).select_related('titulo__plano_financeiro')
    pagos=Pagamento.objects.filter(status=Pagamento.Status.EFETIVADO,data_pagamento__range=(inicio,fim)).select_related('titulo__plano_financeiro')
    lancados = _filtros(lancados, obra_ids=obra_ids, classe=classe, apropriacao=apropriacao, fornecedor=fornecedor)
    aprovacoes = _filtros(aprovacoes, 'titulo__', obra_ids, classe, apropriacao, fornecedor)
    pagos = _filtros(pagos, 'titulo__', obra_ids, classe, apropriacao, fornecedor)
    for titulo in lancados:
        acumular(timezone.localtime(titulo.criado_em).date(),titulo,'lancado',titulo.valor_original)
    # Aprovado duas vezes em ciclos diferentes representa duas decisões: primeira por título no mês,
    # evita repetição no mesmo mês, sem retirar a rastreabilidade de novos ciclos.
    vistos=set()
    for aprovacao in aprovacoes.order_by('criado_em','pk'):
        dt=timezone.localtime(aprovacao.criado_em).date()
        chave=(aprovacao.titulo_id,dt.year,dt.month)
        if chave in vistos:continue
        vistos.add(chave)
        acumular(dt,aprovacao.titulo,'aprovado',aprovacao.titulo.valor_original)
    for pagamento in pagos:
        acumular(pagamento.data_pagamento,pagamento.titulo,'pago',pagamento.valor)
    return [{'mes':f'{ano:04d}-{mes:02d}','categoria':cat,**dados}
            for (ano,mes,cat),dados in sorted(valores.items())]
