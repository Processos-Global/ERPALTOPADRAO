"""Diagnóstico SOMENTE LEITURA para datas do Cronograma Físico do SAARI.

Executar na raiz do projeto com Django configurado:
    python manage.py shell -c "exec(open('diagnostico_datas_cronograma.py', encoding='utf-8').read())"

NÃO altera registros, NÃO executa importações e NÃO cria migrações.
"""

from collections import Counter
from django.db import connection
from django.db.models import Count, Max, Min
from planejamento.models import ImportacaoCronograma, RegistroCronograma
from planejamento.services.cronograma.consultas import usar_importacao_ativa
from planejamento.services.cronograma.resumo_geral import obter_serie_resumo_geral

BUSCA_OBRA = "CJ 05 CASA 09"  # ajuste se o nome da obra no banco for diferente


def data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else "—"


def relatorio():
    print("\n" + "=" * 98)
    print("DIAGNÓSTICO DE DATAS DO CRONOGRAMA FÍSICO — SOMENTE LEITURA")
    print("=" * 98)
    print(f"Banco: {connection.vendor} ({connection.settings_dict.get('NAME')})")

    importacao = (
        ImportacaoCronograma.objects.filter(
            ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA
        )
        .order_by("-id")
        .first()
    )
    if importacao is None:
        print("NENHUMA IMPORTAÇÃO ATIVA CONCLUÍDA. Verifique o banco selecionado.")
        return
    print(f"Importação ativa: ID={importacao.id}; arquivo={importacao.nome_arquivo}; finalizada={importacao.finalizou_em}")

    projetos = list(
        RegistroCronograma.objects.filter(
            importacao_id=importacao.id, projeto__icontains=BUSCA_OBRA
        )
        .values_list("projeto", flat=True)
        .order_by("projeto")
        .distinct()[:20]
    )
    print(f"Projetos encontrados para '{BUSCA_OBRA}': {projetos}")
    if len(projetos) != 1:
        print("Busca sem resultado único. Confira a grafia e ajuste BUSCA_OBRA no início do script.")
        return
    projeto = projetos[0]
    base = RegistroCronograma.objects.filter(importacao_id=importacao.id, projeto=projeto)
    print(f"Projeto exato: {projeto} | registros totais: {base.count()}")

    resumo_qs = base.filter(disciplina__iexact="RESUMO GERAL").exclude(semana__isnull=True)
    resumos = list(
        resumo_qs.order_by("semana", "id").values(
            "id", "semana", "inicio_semana", "inicio_semana_base", "data_atualizacao",
            "semana_anterior", "semana_seguinte", "percentual_previsto", "percentual_executado",
        )
    )
    if not resumos:
        print("Nenhuma linha RESUMO GERAL. Verifique disciplina e importação.")
        print("Disciplinas disponíveis (amostra):", list(base.values_list("disciplina", flat=True).order_by("disciplina").distinct()[:15]))
        return

    por_semana = {registro["semana"]: registro for registro in resumos}
    contagem_semana = Counter(registro["semana"] for registro in resumos)
    print(f"Linhas RESUMO GERAL: {len(resumos)} | semanas distintas: {len(por_semana)}")
    print("OBS: o painel atual utiliza a última linha por semana (maior ID).")
    repetidas = {semana: qtd for semana, qtd in contagem_semana.items() if qtd > 1}
    print("Semanas com mais de um RESUMO GERAL:", repetidas if repetidas else "nenhuma")

    print("\nSEMANA | ID RESUMO | INÍCIO SEMANA | INÍCIO SEMANA BASE | ATUALIZAÇÃO | PREVISTO | REALIZADO")
    for semana in sorted(por_semana):
        r = por_semana[semana]
        previsto = f"{float(r['percentual_previsto'] or 0) * 100:.2f}%"
        executado = f"{float(r['percentual_executado'] or 0) * 100:.2f}%"
        print(
            f"{semana:>6} | {r['id']:>9} | {data_br(r['inicio_semana']):>13} | "
            f"{data_br(r['inicio_semana_base']):>18} | {data_br(r['data_atualizacao']):>11} | "
            f"{previsto:>8} | {executado:>9}"
        )

    datas_serie = [r["inicio_semana"] for r in por_semana.values()]
    data_counts = Counter(datas_serie)
    print("\nDATAS 'inicio_semana' NAS LINHAS RESUMO GERAL:")
    for data, qtd in sorted(data_counts.items(), key=lambda p: (p[0] is None, str(p[0]))):
        print(f"  {data_br(data)}: {qtd} semana(s)")
    if len(por_semana) > 1 and len(data_counts) == 1:
        print("ALERTA: TODAS AS SEMANAS TÊM A MESMA DATA. O gráfico repete o rótulo por causa dos dados recebidos.")
    elif len(data_counts) < len(por_semana):
        print("ALERTA: ALGUMAS SEMANAS COMPARTILHAM A MESMA DATA; verificar origem da coluna INICIO_SEMANA.")
    else:
        print("Datas das semanas são distintas no RESUMO GERAL. Se o gráfico repetir 27/04, examinar o JSON/JS gerado.")

    print("\nINÍCIO DE SEMANA EM TODAS AS ATIVIDADES (incluindo RESUMO GERAL), POR SEMANA:")
    print("SEMANA | REGISTROS | DATAS DISTINTAS | MENOR DATA | MAIOR DATA")
    grupos = list(
        base.exclude(semana__isnull=True)
        .values("semana")
        .annotate(
            total=Count("id"),
            distintas=Count("inicio_semana", distinct=True),
            menor=Min("inicio_semana"),
            maior=Max("inicio_semana"),
        )
        .order_by("semana")
    )
    for g in grupos:
        print(
            f"{g['semana']:>6} | {g['total']:>9} | {g['distintas']:>15} | "
            f"{data_br(g['menor']):>10} | {data_br(g['maior']):>10}"
        )

    print("\nCAMPOS DE ORIGEM (SEMANA 22 E SEMANA 29, SE PRESENTES):")
    for semana in (22, 29):
        r = por_semana.get(semana)
        if not r:
            print(f"Semana {semana}: sem RESUMO GERAL")
            continue
        print(
            f"Semana {semana}: início={data_br(r['inicio_semana'])}; "
            f"anterior={r['semana_anterior']!r}; seguinte={r['semana_seguinte']!r}; "
            f"início_semana_base={data_br(r['inicio_semana_base'])}"
        )

    with usar_importacao_ativa(importacao):
        serie = obter_serie_resumo_geral(projeto=projeto)
    print("\nSÉRIE EXATA ENTREGUE AO GRÁFICO (amostra de 4 pontos):")
    for r in (serie[:2] + serie[-2:]):
        print(
            f"semana={r['semana']}; início={data_br(r['inicio_semana'])}; "
            f"fim={data_br(r['fim_semana'])}; "
            f"previsto={r['previsto'] * 100:.2f}%; realizado={r['executado'] * 100:.2f}%"
        )
    print("\nFim do diagnóstico. NENHUM DADO FOI ALTERADO.\n")


relatorio()
