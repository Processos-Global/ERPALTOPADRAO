from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.contrib.staticfiles import finders
from googleapiclient.errors import HttpError
from PIL import Image as PillowImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from cadastros.models import DadosEmpresa


def _logo_pdf(abrir):
    try:
        with abrir() as arquivo, PillowImage.open(arquivo) as original:
            imagem = ImageOps.exif_transpose(original)
            imagem.thumbnail((640, 640))
            dados = BytesIO()
            imagem.convert("RGBA").save(dados, format="PNG")
            dados.seek(0)
        return Image(dados, width=18 * mm, height=18 * mm, kind="proportional")
    except (OSError, ValueError, HttpError, PillowImage.DecompressionBombError):
        return None


def cabecalho_empresa(largura_mm=178):
    """Cabeçalho único de PDFs. O logo registrado prevalece sobre o logo padrão."""
    empresa = DadosEmpresa.atual()
    nome = (empresa.nome_fantasia.strip() or empresa.razao_social.strip()) if empresa else "SAARI"
    logo = _logo_pdf(lambda: empresa.logo.open("rb")) if empresa and empresa.logo else None
    if logo is None and (caminho := finders.find("img/saari/saari-simbolo-gold.png")):
        logo = _logo_pdf(lambda: Path(caminho).open("rb"))

    titulo = ParagraphStyle(
        "EmpresaTitulo", fontName="Helvetica-Bold", fontSize=12, leading=15,
        textColor=colors.HexColor("#453330"), spaceAfter=3,
    )
    detalhe = ParagraphStyle(
        "EmpresaDetalhe", fontName="Helvetica", fontSize=7.5, leading=10.5,
        textColor=colors.HexColor("#66534C"),
    )
    texto = [Paragraph(escape(nome), titulo)]
    if empresa:
        campos = (
            ("", empresa.razao_social if empresa.razao_social.strip() != nome else ""),
            ("CNPJ: ", empresa.cnpj),
            ("Inscrição estadual: ", empresa.inscricao_estadual),
            ("Inscrição municipal: ", empresa.inscricao_municipal),
            ("", empresa.endereco_completo),
            ("Telefone: ", empresa.telefone),
            ("E-mail: ", empresa.email),
        )
        linhas = [escape(rotulo + valor.strip()) for rotulo, valor in campos if valor and valor.strip()]
        if linhas:
            texto.append(Paragraph("<br/>".join(linhas), detalhe))

    largura = largura_mm * mm
    tabela = Table([[logo, texto]], colWidths=[25 * mm, largura - 25 * mm]) if logo else Table([[texto]], colWidths=[largura])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8F4ED")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DED7C8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [tabela, Spacer(1, 4 * mm)]
