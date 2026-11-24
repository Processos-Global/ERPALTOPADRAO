from django.contrib import messages
from django.db import transaction
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from obras.models import VistoriaHistorico, VistoriaItem
from obras.services.resumo_vistorias import (
    DISCIPLINAS_PRE, DISCIPLINAS_VISTORIA, montar_resumo_vistorias,
)
from planejamento.models import ImportacaoCronograma, RegistroCronograma
from usuarios.decorators import modulo_required, possui_permissao_acao
from usuarios.models import ModuloSistema, NivelPermissao

# O filtro é executado no banco, antes de percorrer os snapshots semanais.
# As variantes abaixo preservam textos antigos, antes da normalização do CSV.
_DISCIPLINAS = DISCIPLINAS_VISTORIA
_PRE = DISCIPLINAS_PRE


def _importacao_id():
    return (ImportacaoCronograma.objects.filter(
        ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA
    ).order_by('-id').values_list('id', flat=True).first())


def _registros(importacao_id):
    return (RegistroCronograma.objects.filter(
        importacao_id=importacao_id, obra__ativa=True,
        atividade_planejamento__isnull=False, atividade_planejamento__ativa=True,
        disciplina__in=_DISCIPLINAS,
    ).order_by('-semana', '-id').values(
        'atividade_planejamento_id', 'obra_id', 'obra__nome', 'disciplina',
        'local_tarefa', 'nome_tarefa', 'atividade_planejamento__nome_tarefa',
    ))


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def vistorias_lista(request):
    importacao_id = _importacao_id()
    try:
        obra_solicitada = int(request.GET.get('obra') or 0)
    except (ValueError, TypeError):
        obra_solicitada = 0

    # Uma consulta leve de IDs/nomes para construir as abas, sem carregar os snapshots.
    obras = []
    itens = []
    if importacao_id:
        abas = (RegistroCronograma.objects.filter(
            importacao_id=importacao_id, obra__ativa=True,
            atividade_planejamento__isnull=False, atividade_planejamento__ativa=True,
            disciplina__in=_DISCIPLINAS,
        ).order_by('obra__nome', 'obra_id').values('obra_id', 'obra__nome').distinct())
        obras = [{'pk': r['obra_id'], 'nome': r['obra__nome']} for r in abas]
        ids = {o['pk'] for o in obras}
        obra_id = obra_solicitada if obra_solicitada in ids else (obras[0]['pk'] if obras else None)
        if obra_id:
            vistos = set()
            # Restringir snapshots à obra selecionada.
            for r in _registros(importacao_id).filter(obra_id=obra_id).iterator(chunk_size=1000):
                aid = r['atividade_planejamento_id']
                if aid in vistos:
                    continue
                vistos.add(aid)
                itens.append({
                    'atividade_id': aid, 'obra_id': r['obra_id'],
                    'tipo': 'PRE' if r['disciplina'] in _PRE else 'POS',
                    'local': r['local_tarefa'] or 'Sem local informado',
                    'nome': r['nome_tarefa'] or r['atividade_planejamento__nome_tarefa'],
                })
    else:
        obra_id = None

    estados = {v.atividade_id: v for v in VistoriaItem.objects.filter(
        atividade_id__in=[i['atividade_id'] for i in itens]
    ).only('atividade_id', 'status', 'atualizado_em')}
    grupos = []
    for tipo, rotulo in (('PRE', 'Pré Habite-se'), ('POS', 'Pós Habite-se')):
        rows = []
        for item in itens:
            if item['tipo'] != tipo:
                continue
            estado = estados.get(item['atividade_id'])
            rows.append({**item, 'status': estado.status if estado else 'NAO_FEITO',
                         'atualizado_em': estado.atualizado_em if estado else None})
        grupos.append({'tipo': tipo, 'titulo': rotulo, 'linhas': rows,
                       'feitos': sum(r['status'] == 'FEITO' for r in rows)})
    return render(request, 'obras/vistorias/lista.html', {
        'obras': obras, 'obra_id': obra_id, 'grupos': grupos,
    })


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def vistorias_resumo(request):
    return render(
        request, "obras/vistorias_resumo.html",
        montar_resumo_vistorias(request.GET, detalhar_todas_obras=False),
    )


@modulo_required(ModuloSistema.OBRAS, NivelPermissao.LEITURA)
def vistorias_resumo_pdf(request):
    """Exporta a mesma seleção e os mesmos totais do resumo na tela."""
    from html import escape
    from io import BytesIO

    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    dados = montar_resumo_vistorias(request.GET)
    estilos = getSampleStyleSheet()
    p = lambda valor: Paragraph(escape(str(valor or "—")), estilos["Normal"])
    filtros = dados["filtros"]
    obra_nome = next((obra["obra__nome"] for obra in dados["obras_filtro"]
                      if obra["obra_id"] == filtros["obra"]), "Todas")
    tipo = {"PRE": "Pré Habite-se", "POS": "Pós Habite-se"}.get(filtros["tipo"], "Todos")
    situacao = dict(dados["situacoes_filtro"]).get(filtros["situacao"], "Todas")
    data_texto = lambda data: data.strftime("%d/%m/%Y") if data else "Sem limite"
    emissao = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    ultima = (timezone.localtime(dados["ultima_atualizacao"]).strftime("%d/%m/%Y %H:%M")
              if dados["ultima_atualizacao"] else "Sem registro")

    conteudo = [
        Paragraph("SAARI ERP Alto Padrão", estilos["Heading2"]),
        Paragraph("Resumo Gerencial de Vistorias", estilos["Title"]),
        p(f"Emitido em: {emissao}"),
        p(f"Obra: {obra_nome} | Checklist: {tipo} | Situação: {situacao}"),
        p(f"Período do cronograma: {data_texto(filtros['inicio'])} a {data_texto(filtros['fim'])}"),
        p(f"Última atualização relevante: {ultima}"),
        Spacer(1, 6 * mm),
    ]
    resumo = dados["resumo"]
    conteudo.append(p(
        f"Total: {resumo['total']} | Realizadas: {resumo['realizadas']} | "
        f"Não realizadas: {resumo['nao_realizadas']} "
        f"(sem avaliação: {resumo['sem_avaliacao']}) | Conclusão: {resumo['percentual']}%"
    ))
    conteudo.append(Spacer(1, 5 * mm))

    def tabela(linhas, larguras):
        tab = Table(linhas, colWidths=larguras, repeatRows=1, hAlign="LEFT")
        tab.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#453330")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f0e9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return tab

    cabecalho = ["Obra", "Total", "Feitas", "Pendentes", "Conclusão", "Última atualização"]
    linhas = [cabecalho]
    for linha in dados["linhas"]:
        atualizado = (timezone.localtime(linha["ultima_atualizacao"]).strftime("%d/%m/%Y")
                      if linha["ultima_atualizacao"] else "—")
        linhas.append([p(linha["obra_nome"]), str(linha["total"]), str(linha["realizadas"]),
                       str(linha["nao_realizadas"]), f"{linha['percentual']}%", atualizado])
    if len(linhas) == 1:
        linhas.append(["Nenhuma atividade encontrada", "", "", "", "", ""])
    conteudo.extend([Paragraph("Resumo por obra", estilos["Heading3"]),
                     tabela(linhas, [55 * mm, 18 * mm, 18 * mm, 21 * mm, 23 * mm, 42 * mm]),
                     Spacer(1, 5 * mm), Paragraph("Pendências", estilos["Heading3"])])
    pendencias = [["Obra", "Tipo", "Atividade / local", "Situação"]]
    for item in dados["pendencias"]:
        pendencias.append([p(item["obra_nome"]), p(item["tipo"]),
                           p(f"{item['atividade']} — {item['local']}"), p(item["situacao"])])
    if len(pendencias) == 1:
        pendencias.append(["Nenhuma pendência", "", "", ""])
    conteudo.append(tabela(pendencias, [38 * mm, 33 * mm, 82 * mm, 24 * mm]))
    buffer = BytesIO()
    SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(conteudo)
    resposta = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resposta["Content-Disposition"] = 'attachment; filename="saari-resumo-vistorias.pdf"'
    return resposta


@require_POST
@modulo_required(ModuloSistema.OBRAS, NivelPermissao.EDICAO)
def vistoria_alterar(request, atividade_id):
    status = request.POST.get('status')
    if status not in VistoriaItem.Status.values:
        raise Http404('Status inválido')
    importacao_id = _importacao_id()
    if not importacao_id:
        raise Http404('Nenhum cronograma ativo')
    # Consulta EXISTS: verifica uma única atividade, sem reler o cronograma inteiro.
    registro = (RegistroCronograma.objects.filter(
        importacao_id=importacao_id, atividade_planejamento_id=atividade_id,
        atividade_planejamento__ativa=True, obra__ativa=True,
        disciplina__in=_DISCIPLINAS,
    ).values('obra_id').first())
    if not registro:
        raise Http404('Atividade indisponível no cronograma ativo')
    disciplina = RegistroCronograma.objects.filter(
        importacao_id=importacao_id, atividade_planejamento_id=atividade_id,
        disciplina__in=_DISCIPLINAS,
    ).values_list('disciplina', flat=True).first()
    acao = 'pre_habite_se' if disciplina in _PRE else 'pos_habite_se'
    if not possui_permissao_acao(request.user, ModuloSistema.VISTORIAS, acao):
        raise PermissionDenied('Você não pode alterar esta vistoria.')

    with transaction.atomic():
        item, _ = VistoriaItem.objects.select_for_update().get_or_create(
            atividade_id=atividade_id, defaults={'status': 'NAO_FEITO'})
        anterior = item.status
        if anterior != status:
            item.status = status
            item.atualizado_por = request.user
            item.save(update_fields=['status', 'atualizado_por', 'atualizado_em'])
            VistoriaHistorico.objects.create(
                item=item, status_anterior=anterior, status_novo=status,
                usuario=request.user)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True, 'status': item.status,
                             'atualizado_em': timezone.localtime(item.atualizado_em).strftime('%d/%m/%Y %H:%M')})
    messages.success(request, 'Vistoria atualizada.')
    return redirect(f"/obras/vistorias/?obra={registro['obra_id']}")
