from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.utils import timezone


def _texto(valor, padrao="—"):
    texto = str(valor or "").strip()
    return escape(texto) if texto else padrao


def _nome_usuario(usuario):
    if not usuario:
        return "—"
    nome = (usuario.get_full_name() or "").strip()
    return escape(nome) if nome else "Nome não cadastrado"


def _quantidade(valor):
    if valor is None:
        return "—"
    texto = f"{valor:f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") or "0"


def gerar_pdf_solicitacao_cotacao(processo):
    """Gera uma solicitação genérica de cotação, sem fornecedor e sem preços."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ValidationError(
            "O gerador de PDF requer o pacote reportlab. Instale com: pip install reportlab"
        ) from exc

    necessidades = list(
        processo.necessidades
        .select_related("material", "material__unidade")
        .exclude(situacao="CANCELADA")
        .order_by("descricao", "id")
    )
    if not necessidades:
        raise ValidationError("Não existem materiais ativos para gerar a solicitação de cotação.")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Solicitação de cotação - {processo.numero}",
        author="ERP Alto Padrão",
    )

    styles = getSampleStyleSheet()
    brand = colors.HexColor("#087F83")
    ink = colors.HexColor("#173946")
    muted = colors.HexColor("#64748B")
    line = colors.HexColor("#CBDDE2")
    soft = colors.HexColor("#EEF8F8")
    light = colors.HexColor("#F8FAFC")

    title = ParagraphStyle(
        "CotacaoTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        alignment=TA_CENTER,
        textColor=ink,
        spaceAfter=1 * mm,
    )
    subtitle = ParagraphStyle(
        "CotacaoSubtitle",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=10,
        alignment=TA_CENTER,
        textColor=muted,
    )
    body = ParagraphStyle(
        "CotacaoBody",
        parent=styles["Normal"],
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    small = ParagraphStyle(
        "CotacaoSmall",
        parent=body,
        fontSize=7.2,
        leading=9.5,
        textColor=muted,
    )
    label = ParagraphStyle(
        "CotacaoLabel",
        parent=small,
        fontName="Helvetica-Bold",
        textColor=ink,
    )
    right = ParagraphStyle("CotacaoRight", parent=small, alignment=TA_RIGHT)
    section = ParagraphStyle(
        "CotacaoSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=ink,
    )

    story = []

    cabecalho = Table(
        [[
            Paragraph("<b>DEPARTAMENTO DE ENGENHARIA — COMPRAS</b>", body),
            Paragraph(f"<b>Nº:</b> {_texto(processo.numero)}", right),
        ], [
            Paragraph("SOLICITAÇÃO DE COTAÇÃO DE MATERIAIS", title),
            Paragraph(
                f"<b>Comprador</b><br/>{_nome_usuario(processo.comprador)}",
                right,
            ),
        ], [
            Paragraph("ERP ALTO PADRÃO · SUPRIMENTOS", subtitle),
            Paragraph(
                f"Emitido em {timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
                right,
            ),
        ]],
        colWidths=[132 * mm, 50 * mm],
    )
    cabecalho.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, ink),
        ("SPAN", (0, 1), (0, 1)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(cabecalho)
    story.append(Spacer(1, 3 * mm))

    obra_nome = getattr(processo.obra, "nome", None) or str(processo.obra)
    suprimento = (
        processo.item_cronograma.item
        if processo.item_cronograma
        else processo.titulo
    )
    dados = [
        [Paragraph("OBRA", label), Paragraph("SUPRIMENTO / PROCESSO", label), Paragraph("DATA", label)],
        [Paragraph(_texto(obra_nome), body), Paragraph(_texto(suprimento), body), Paragraph(timezone.localdate().strftime("%d/%m/%Y"), body)],
        [Paragraph("SOLICITANTE", label), Paragraph("COMPRADOR RESPONSÁVEL", label), Paragraph("ITENS", label)],
        [Paragraph(_nome_usuario(processo.criado_por), body), Paragraph(_nome_usuario(processo.comprador), body), Paragraph(str(len(necessidades)), body)],
    ]
    dados_table = Table(dados, colWidths=[66 * mm, 83 * mm, 33 * mm])
    dados_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), soft),
        ("BACKGROUND", (0, 2), (-1, 2), soft),
        ("GRID", (0, 0), (-1, -1), 0.45, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(dados_table)
    story.append(Spacer(1, 3 * mm))

    fornecedor = Table([
        [Paragraph("DADOS DO FORNECEDOR / PREENCHIMENTO DA PROPOSTA", section)],
        [
            Paragraph("<b>Empresa:</b> ______________________________________________", body),
            Paragraph("<b>CNPJ:</b> ______________________________", body),
        ],
        [
            Paragraph("<b>Vendedor:</b> _____________________________________________", body),
            Paragraph("<b>Telefone:</b> ___________________________", body),
        ],
        [
            Paragraph("<b>E-mail:</b> _______________________________________________", body),
            Paragraph("<b>Validade:</b> ___________________________", body),
        ],
    ], colWidths=[112 * mm, 70 * mm])
    fornecedor.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, line),
        ("INNERGRID", (0, 1), (-1, -1), 0.3, line),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(fornecedor)
    story.append(Spacer(1, 3 * mm))

    item_rows = [[
        Paragraph("Item", label),
        Paragraph("Código", label),
        Paragraph("Material / especificação", label),
        Paragraph("Unid.", label),
        Paragraph("Qtd.", label),
    ]]
    for indice, item in enumerate(necessidades, start=1):
        codigo = getattr(item.material, "codigo", "") if item.material else ""
        especificacao = item.especificacao or ""
        descricao_html = f"<b>{_texto(item.descricao)}</b>"
        if especificacao:
            descricao_html += f"<br/><font color='#64748B'>{_texto(especificacao)}</font>"
        if item.observacao:
            descricao_html += f"<br/><font color='#64748B'><b>Obs.:</b> {_texto(item.observacao)}</font>"
        item_rows.append([
            Paragraph(str(indice), body),
            Paragraph(_texto(codigo), small),
            Paragraph(descricao_html, body),
            Paragraph(_texto(item.unidade), body),
            Paragraph(_quantidade(item.quantidade_incluida), body),
        ])

    itens_table = Table(
        item_rows,
        colWidths=[11 * mm, 24 * mm, 112 * mm, 16 * mm, 19 * mm],
        repeatRows=1,
    )
    itens_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCEDEF")),
        ("GRID", (0, 0), (-1, -1), 0.4, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(itens_table)
    story.append(Spacer(1, 3 * mm))

    comerciais = Table([
        [Paragraph("INFORMAÇÕES COMERCIAIS A INFORMAR NA PROPOSTA", section)],
        [
            Paragraph("<b>Condição de pagamento:</b> __________________________________________", body),
            Paragraph("<b>Prazo de entrega:</b> ____________________", body),
        ],
        [
            Paragraph("<b>Frete:</b> ___________________________________________________________", body),
            Paragraph("<b>Validade:</b> ____________________________", body),
        ],
    ], colWidths=[112 * mm, 70 * mm])
    comerciais.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, line),
        ("INNERGRID", (0, 1), (-1, -1), 0.3, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(comerciais)
    story.append(Spacer(1, 3 * mm))

    instrucoes = [
        "Informar preço unitário e total de cada item na proposta comercial enviada ao comprador.",
        "Respeitar as quantidades, unidades e especificações desta solicitação ou destacar claramente qualquer divergência.",
        "Informar marca/fabricante quando aplicável, prazo de entrega, condição de pagamento, frete e validade da proposta.",
        f"Referenciar o processo {_texto(processo.numero)} na proposta e nos documentos enviados.",
    ]
    if processo.observacao:
        instrucoes.append(f"Observação do processo: {_texto(processo.observacao)}")

    instrucoes_table = Table([
        [Paragraph("ORIENTAÇÕES AO FORNECEDOR", section)],
        [Paragraph("<br/>".join(f"• {texto}" for texto in instrucoes), body)],
    ], colWidths=[182 * mm])
    instrucoes_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), soft),
        ("BOX", (0, 0), (-1, -1), 0.55, brand),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(instrucoes_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Documento gerado eletronicamente pelo ERP Alto Padrão. Esta solicitação não representa pedido de compra, aprovação comercial ou autorização de faturamento.",
        small,
    ))

    doc.build(story)
    return buffer.getvalue()
