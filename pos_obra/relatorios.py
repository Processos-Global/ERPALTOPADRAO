"""Documentos técnicos de Pós-Obra do SAARI ERP (ReportLab)."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from django.http import Http404, HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, LongTable, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle, HRFlowable,
)

MARROM = colors.HexColor('#463631')
DOURADO = colors.HexColor('#b79b59')
CINZA = colors.HexColor('#647074')
FUNDO = colors.HexColor('#f8f7f4')
LINHA = colors.HexColor('#dcdedc')


def gerar_termo_aceite(aceite):
    """Página(s) suplementar(es), preservando texto integral e a via original."""
    from django.utils import timezone
    memoria=BytesIO();estilos=getSampleStyleSheet()
    corpo=ParagraphStyle('Termo',parent=estilos['BodyText'],fontSize=9,leading=14,textColor=MARROM,spaceAfter=8)
    titulo=ParagraphStyle('TermoTitulo',parent=estilos['Heading1'],textColor=MARROM)
    def p(texto):return Paragraph(escape(str(texto or 'Não informado')).replace('\n','<br/>'),corpo)
    doc=aceite.documento
    campos=[('Ordem de serviço',doc.chamado.numero),('Documento',f'{doc.tipo} · versão {doc.versao}'),
        ('Resultado',aceite.get_resultado_display()),('Signatário',aceite.signatario),
        ('Representação declarada',aceite.representacao),
        ('Registrado em',timezone.localtime(aceite.criado_em).strftime('%d/%m/%Y %H:%M')),
        ('SHA-256 do PDF original',doc.sha256),('Observações / ressalvas',aceite.observacoes)]
    story=[Paragraph('SAARI ERP | Termo de aceite da OS',titulo),Spacer(1,5*mm)]
    for rotulo,valor in campos:
        story.extend([Paragraph(escape(rotulo),estilos['Heading3']),p(valor)])
    if aceite.assinatura:
        with aceite.assinatura.open('rb') as arquivo:imagem=arquivo.read()
        story.extend([Paragraph('Assinatura registrada',estilos['Heading3']),Image(BytesIO(imagem),width=120*mm,height=35*mm,kind='proportional')])
    story.extend([Spacer(1,6*mm),p('Registro eletrônico simples: autenticidade depende da identificação e das evidências de auditoria.')])
    def rodape(canvas,documento):
        canvas.setFont('Helvetica',8);canvas.setFillColor(CINZA)
        canvas.drawString(19*mm,14*mm,f'SAARI ERP | {doc.chamado.numero} | Termo de aceite')
        canvas.drawRightString(191*mm,14*mm,f'Página {documento.page}')
    SimpleDocTemplate(memoria,pagesize=A4,leftMargin=19*mm,rightMargin=19*mm,topMargin=19*mm,bottomMargin=24*mm).build(story,onFirstPage=rodape,onLaterPages=rodape)
    return memoria.getvalue()


def gerar_relatorio(chamado, tipo, publico=False, aceite=None):
    titulos = {'vistoria': 'Relatório técnico de vistoria',
               'execucao': 'Relatório técnico de execução',
               'os': 'Ordem de serviço'}
    if tipo not in titulos:
        raise Http404('Documento não encontrado.')
    c = chamado
    memoria = BytesIO()
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(name='DocTitle', fontName='Helvetica-Bold', fontSize=17, leading=21,
        textColor=MARROM, spaceAfter=4))
    estilos.add(ParagraphStyle(name='DocSub', fontName='Helvetica', fontSize=8.5, leading=13,
        textColor=CINZA, spaceAfter=5))
    estilos.add(ParagraphStyle(name='SectionSaari', fontName='Helvetica-Bold', fontSize=10,
        leading=13, textColor=MARROM, spaceBefore=9, spaceAfter=6, keepWithNext=True))
    estilos.add(ParagraphStyle(name='BodySaari', fontName='Helvetica', fontSize=9,
        leading=14, textColor=MARROM, spaceAfter=4, splitLongWords=True))
    estilos.add(ParagraphStyle(name='SmallSaari', parent=estilos['BodySaari'], fontSize=7.5, leading=11))
    estilos.add(ParagraphStyle(name='LabelSaari', parent=estilos['SmallSaari'],
        fontName='Helvetica-Bold', textColor=CINZA))
    estilos.add(ParagraphStyle(name='SignSaari', parent=estilos['SmallSaari'], alignment=TA_CENTER))
    estilos.add(ParagraphStyle(name='DocCode', parent=estilos['SmallSaari'], alignment=TA_RIGHT,
        fontName='Helvetica-Bold'))

    def p(value, style='BodySaari', empty='Não informado'):
        text = str(value).strip() if value is not None else ''
        return Paragraph(escape(text or empty).replace('\n', '<br/>'), estilos[style])

    def section(title, content, empty='Não registrado até a emissão deste documento.'):
        return KeepTogether([p(title, 'SectionSaari'), p(content, empty=empty)])

    def cells(items):
        return Table([[p(k, 'LabelSaari'), p(v)] for k, v in items],
            colWidths=[35*mm, 137*mm], splitInRow=1, hAlign='LEFT', style=TableStyle([
                ('BACKGROUND',(0,0),(0,-1),FUNDO),
                ('LINEBELOW',(0,0),(-1,-1),.35,LINHA),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),8),
                ('RIGHTPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),6),
                ('BOTTOMPADDING',(0,0),(-1,-1),5),
            ]))

    endereco = c.empreendimento.endereco_historico if c.empreendimento.historica else getattr(c.empreendimento.obra, 'endereco', '')
    responsavel = (c.responsavel.get_full_name() or c.responsavel.username) if c.responsavel else ''
    ambiente = f'{c.ambiente_padrao or c.ambiente_ficha or ""} {c.ambiente_detalhe or ""}'.strip()
    historia = [
        ('Número da OS', c.numero), ('Cliente', c.cliente), ('Imóvel', c.empreendimento),
        ('Endereço', endereco), ('Ambiente', ambiente),
        ('Data de abertura', c.criado_em.strftime('%d/%m/%Y')),
        ('Responsável', responsavel), ('Situação', c.get_status_display()),
    ]

    story = []
    # O símbolo é pequeno e acompanhado de uma identificação tipográfica legível.
    simbolo = finders.find('img/saari/saari-simbolo-gold.png')
    logotipo = None
    if simbolo and Path(simbolo).is_file():
        try:
            logotipo = Image(simbolo, width=14*mm, height=14*mm, kind='proportional')
        except (OSError, ValueError):
            pass
    nome = [p('SAARI ERP', 'SectionSaari'), p('ASSISTÊNCIA TÉCNICA · PÓS-OBRA', 'SmallSaari')]
    if logotipo:
        cabecalho = Table([[logotipo, nome, p(c.numero, 'DocCode')]], colWidths=[19*mm, 100*mm, 53*mm])
    else:
        cabecalho = Table([[nome, p(c.numero, 'DocCode')]], colWidths=[119*mm, 53*mm])
    cabecalho.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LINEBELOW',(0,0),(-1,-1),1,DOURADO), ('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story += [cabecalho, Spacer(1,8*mm), p(titulos[tipo], 'DocTitle'),
              p('Registro técnico do atendimento · Emitido em ' + __import__('django.utils.timezone', fromlist=['localtime']).localtime().strftime('%d/%m/%Y às %H:%M'), 'DocSub'),
              Spacer(1,3*mm), p('01  IDENTIFICAÇÃO DO ATENDIMENTO', 'SectionSaari'), cells(historia)]

    story += [p('02  OCORRÊNCIA REGISTRADA', 'SectionSaari'),
              cells([('Classificação', f'{c.categoria_original or c.tipo_problema.categoria} · {c.tipo_original or c.tipo_problema.nome}'),
                     ('Descrição', c.descricao)])]
    if not publico:
        story += [section('03  TRIAGEM INTERNA', c.triagem)]
    indice = 4 if not publico else 3
    if tipo in ('vistoria', 'execucao', 'os'):
        story += [p(f'{indice:02d}  VISTORIA TÉCNICA', 'SectionSaari'),
                  cells([('Data', c.data_vistoria.strftime('%d/%m/%Y') if c.data_vistoria else ''),
                         ('Diagnóstico', c.diagnostico)])]
        indice += 1
    if tipo in ('execucao','os'):
        story += [p(f'{indice:02d}  EXECUÇÃO DOS SERVIÇOS', 'SectionSaari'),
                  cells([('Data', c.data_execucao.strftime('%d/%m/%Y') if c.data_execucao else ''),
                         ('Serviços realizados', c.execucao)])]
        indice += 1
    if tipo == 'os':
        indice += 1
        materiais = list(c.materiais.all())
        story.append(p(f'{indice:02d}  MATERIAIS UTILIZADOS', 'SectionSaari'))
        if materiais:
            headers = ['Descrição', 'Un.', 'Qtd.'] + ([] if publico else ['Unit. (R$)', 'Total (R$)'])
            colWidths = [125*mm, 19*mm, 28*mm] if publico else [77*mm, 14*mm, 18*mm, 30*mm, 33*mm]
            rows = [[p(x,'LabelSaari') for x in headers]]
            for m in materiais:
                linha = [m.descricao, m.unidade, str(m.utilizado)]
                if not publico:
                    linha += [f'{m.custo_unitario:.4f}', f'{m.total:.2f}']
                rows.append([p(x,'SmallSaari') for x in linha])
            tabela = LongTable(rows, colWidths=colWidths, repeatRows=1, hAlign='LEFT')
            tabela.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),FUNDO),
                ('LINEBELOW',(0,0),(-1,-1),.35,LINHA), ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('TOPPADDING',(0,0),(-1,-1),6), ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.append(tabela)
        else:
            story.append(p('Nenhum material utilizado registrado.'))
        if not publico and (c.materiais_observacao or '').strip():
            story.append(section('Observações sobre materiais', c.materiais_observacao))
        indice += 1
    stages = {'vistoria':['ABERTURA','VISTORIA'], 'execucao':['ABERTURA','VISTORIA','EXECUCAO'],
              'os':['ABERTURA','VISTORIA','EXECUCAO','FINALIZACAO']}
    anexos = c.anexos.filter(etapa__in=stages[tipo])
    if publico:
        anexos = anexos.filter(publico=True)
    if anexos.exists():
        story.append(p(f'{indice:02d}  RELAÇÃO DE EVIDÊNCIAS', 'SectionSaari'))
        story.append(p('Arquivos vinculados ao atendimento. Os originais permanecem disponíveis no sistema conforme permissões de acesso.', 'SmallSaari'))
        for a in anexos:
            story.append(p(f'• {a.get_etapa_display()} — {Path(a.arquivo.name).name}', 'SmallSaari'))
            if Path(a.arquivo.name).suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                try:
                    with a.arquivo.open('rb') as arquivo:
                        imagem=Image(BytesIO(arquivo.read()),width=160*mm,height=90*mm,kind='proportional')
                        story.extend([imagem,Spacer(1,4*mm)])
                except (OSError,ValueError):
                    story.append(p('Imagem indisponível para impressão; consulte o arquivo original.','SmallSaari'))

    if tipo == 'os' and aceite is not None:
        story.append(p('ACEITE E ASSINATURA DO CLIENTE', 'SectionSaari'))
        story.append(cells([('Signatário', aceite.signatario),
                            ('Vínculo com o imóvel', aceite.representacao),
                            ('Resultado', aceite.get_resultado_display()),
                            ('Ressalvas', aceite.observacoes or 'Nenhuma'),
                            ('Data do aceite', __import__('django.utils.timezone', fromlist=['localtime']).localtime(aceite.criado_em).strftime('%d/%m/%Y %H:%M'))]))
        if aceite.assinatura:
            try:
                with aceite.assinatura.open('rb') as assinatura_arquivo:
                    imagem = Image(BytesIO(assinatura_arquivo.read()), width=88*mm, height=27*mm, kind='proportional')
                    story.extend([Spacer(1, 5*mm), imagem, p('Assinatura manuscrita registrada no atendimento', 'SmallSaari')])
            except (OSError, ValueError):
                story.append(p('Imagem de assinatura indisponível.', 'SmallSaari'))
    elif tipo == 'os':
        story.append(p('DOCUMENTO DE CONSULTA · SEM ASSINATURA', 'SectionSaari'))

    def pagina(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(DOURADO)
        canvas.setLineWidth(.65)
        canvas.line(19*mm, 19*mm, w-19*mm, 19*mm)
        canvas.setFont('Helvetica',7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(19*mm, 13.5*mm, f'SAARI ERP  |  {c.numero}  |  {titulos[tipo]}')
        canvas.drawRightString(w-19*mm,13.5*mm, f'Página {doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(memoria, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
        topMargin=17*mm, bottomMargin=26*mm, title=f'{titulos[tipo]} - {c.numero}',
        author='SAARI ERP')
    doc.build(story, onFirstPage=pagina, onLaterPages=pagina)
    return HttpResponse(memoria.getvalue(), content_type='application/pdf',
        headers={'Content-Disposition':f'attachment; filename="{c.numero}-{tipo}.pdf"'})
