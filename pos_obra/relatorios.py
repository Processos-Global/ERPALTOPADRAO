"""Relatórios de atendimento com paginação, tabelas e campos para assinatura."""
from io import BytesIO
from xml.sax.saxutils import escape
from django.http import Http404, HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


def gerar_relatorio(chamado, tipo, publico=False):
    titulos = {'vistoria': 'Relatório de vistoria', 'execucao': 'Relatório de execução', 'os': 'Ordem de serviço'}
    if tipo not in titulos:
        raise Http404
    c = chamado
    stream = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('SAARI', fontName='Times-Roman', fontSize=23, leading=28, textColor=colors.HexColor('#453330'), spaceAfter=16))
    styles.add(ParagraphStyle('CorpoSAARI', fontName='Helvetica', fontSize=10, leading=15, spaceAfter=9, wordWrap='CJK'))
    styles.add(ParagraphStyle('SecaoSAARI', parent=styles['Heading2'], textColor=colors.HexColor('#453330'), spaceBefore=14, spaceAfter=8))
    styles.add(ParagraphStyle('AssinaturaSAARI', parent=styles['CorpoSAARI'], alignment=TA_CENTER, fontSize=9))

    def par(texto, estilo='CorpoSAARI'):
        return Paragraph(escape(str(texto or 'Não informado')).replace('\n', '<br/>'), styles[estilo])

    story = [par('SAARI ERP · Assistência técnica'), par(titulos[tipo], 'SAARI')]
    endereco = c.empreendimento.endereco_historico if c.empreendimento.historica else getattr(c.empreendimento.obra, 'endereco', '')
    detalhes = [('OS', c.numero), ('Imóvel', c.empreendimento), ('Cliente', c.cliente), ('Endereço', endereco),
                ('Abertura', c.criado_em.strftime('%d/%m/%Y')), ('Status', c.get_status_display()),
                ('Responsável', c.responsavel.get_full_name() or c.responsavel.username if c.responsavel else ''),
                ('Ambiente', f'{c.ambiente_padrao or c.ambiente_ficha or ""} {c.ambiente_detalhe}'.strip())]
    table = Table([[par(k), par(v)] for k,v in detalhes], colWidths=[32*mm, 142*mm], hAlign='LEFT')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'), ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#ded7c8')), ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#faf7f1')), ('TOPPADDING',(0,0),(-1,-1),7), ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.append(table)
    blocos = [('Ocorrência', f'{c.categoria_original} · {c.tipo_original}'), ('Descrição do problema', c.descricao)]
    if not publico:
        blocos.append(('Triagem interna', c.triagem))
    blocos += [('Data da vistoria', c.data_vistoria.strftime('%d/%m/%Y') if c.data_vistoria else ''), ('Diagnóstico', c.diagnostico)]
    if tipo != 'vistoria':
        blocos += [('Data da execução', c.data_execucao.strftime('%d/%m/%Y') if c.data_execucao else ''), ('Serviços executados', c.execucao)]
    if tipo == 'os':
        blocos.append(('Conclusão', c.conclusao))
    for titulo, texto in blocos:
        story.extend([par(titulo, 'SecaoSAARI'), par(texto)])
    if tipo == 'os':
        materiais = list(c.materiais.all())
        if materiais:
            story.append(par('Materiais utilizados', 'SecaoSAARI'))
            headers = ['Material', 'Unidade', 'Quantidade'] + ([] if publico else ['Valor unitário', 'Total'])
            rows = [[par(x) for x in headers]]
            for m in materiais:
                row = [m.descricao, m.unidade, str(m.utilizado)]
                if not publico:
                    row += [f'R$ {m.custo_unitario:.4f}', f'R$ {m.total:.2f}']
                rows.append([par(x) for x in row])
            widths = [94*mm, 30*mm, 50*mm] if publico else [74*mm, 20*mm, 25*mm, 28*mm, 27*mm]
            table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#ded7c8')), ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#faf7f1')),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(table)
        if not publico:
            story += [par('Observações de materiais', 'SecaoSAARI'), par(c.materiais_observacao)]
        assinaturas = Table([[par('Cliente / pessoa autorizada', 'AssinaturaSAARI'), '', par('Responsável pelo atendimento', 'AssinaturaSAARI')]], colWidths=[80*mm, 14*mm, 80*mm])
        assinaturas.setStyle(TableStyle([('LINEABOVE',(0,0),(0,0),.5,colors.HexColor('#85776f')), ('LINEABOVE',(2,0),(2,0),.5,colors.HexColor('#85776f')), ('TOPPADDING',(0,0),(-1,-1),8)]))
        story.append(KeepTogether([Spacer(1,20*mm), assinaturas, Spacer(1,6*mm), par('Data: ______ / ______ / __________', 'AssinaturaSAARI')]))
    # Evidências são baixadas por rota autenticada; nenhum link público é incorporado ao PDF.
    anexos = c.anexos.all()
    if publico:
        anexos = anexos.filter(publico=True)
    etapas = {'vistoria':['ABERTURA','VISTORIA'], 'execucao':['ABERTURA','VISTORIA','EXECUCAO'], 'os':['ABERTURA','VISTORIA','EXECUCAO','FINALIZACAO']}
    anexos = anexos.filter(etapa__in=etapas[tipo])
    if anexos.exists():
        story.append(par('Documentos anexados ao atendimento', 'SecaoSAARI'))
        for a in anexos:
            story.append(par(f'{a.get_etapa_display()} · {a.arquivo.name.rsplit("/",1)[-1]}'))
    def rodape(canvas, doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#85776f'))
        canvas.drawString(18*mm,14*mm,f'SAARI ERP | {c.numero}');canvas.drawRightString(192*mm,14*mm,f'Página {doc.page}');canvas.restoreState()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=23*mm, title=f'{titulos[tipo]} — {c.numero}')
    doc.build(story,onFirstPage=rodape,onLaterPages=rodape)
    return HttpResponse(stream.getvalue(),content_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="{c.numero}-{tipo}.pdf"'})
