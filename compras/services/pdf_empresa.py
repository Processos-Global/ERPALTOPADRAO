from django.conf import settings
from django.contrib.staticfiles import finders
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from xml.sax.saxutils import escape
from cadastros.models import DadosEmpresa


def cabecalho_empresa(largura_mm=178):
    """Cabeçalho único de PDFs. O logo registrado prevalece sobre o logo padrão."""
    empresa = DadosEmpresa.atual()
    nome = (empresa.nome_fantasia if empresa else '') or 'SAARI'
    itens = []
    caminho = None
    if empresa and empresa.logo:
        try:
            caminho = empresa.logo.path
        except (ValueError, NotImplementedError):
            caminho = None
    if not caminho:
        caminho = finders.find('img/saari/saari-simbolo-gold.png')
    if caminho:
        try:
            logo = Image(caminho, width=18*mm, height=18*mm, kind='proportional')
            itens.append(logo)
        except (OSError, ValueError):
            pass
    titulo = ParagraphStyle('EmpresaTitulo', fontName='Helvetica-Bold', fontSize=14, leading=17, textColor=colors.HexColor('#453330'))
    detalhe = ParagraphStyle('EmpresaDetalhe', fontName='Helvetica', fontSize=7.5, leading=10.5, textColor=colors.HexColor('#66534C'))
    linhas = [f'<b>{escape(nome)}</b>']
    if empresa:
        if empresa.razao_social: linhas.append(escape(empresa.razao_social))
        if empresa.cnpj: linhas.append('CNPJ: '+escape(empresa.cnpj))
        if empresa.endereco_completo: linhas.append(escape(empresa.endereco_completo))
        if empresa.telefone: linhas.append('Telefone: '+escape(empresa.telefone))
        if empresa.email: linhas.append(escape(empresa.email))
    texto = Paragraph('<br/>'.join(linhas), detalhe)
    largura = largura_mm*mm
    if itens:
        tabela = Table([[itens[0], texto]], colWidths=[23*mm, largura-23*mm])
    else:
        tabela = Table([[texto]], colWidths=[largura])
    tabela.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F8F4ED')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#DED7C8')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return [tabela, Spacer(1, 5*mm)]
