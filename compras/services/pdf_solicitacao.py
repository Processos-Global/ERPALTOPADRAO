from io import BytesIO
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.utils import timezone


def _nome_usuario(usuario):
    if not usuario:
        return "-"
    nome = (usuario.get_full_name() or "").strip()
    return nome or getattr(usuario, "username", "-")


def _dinheiro(valor):
    valor = valor or 0
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _quantidade(valor):
    if valor is None:
        return "-"
    texto = f"{valor:.4f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _texto(valor, padrao="-"):
    if valor is None:
        return padrao
    texto = str(valor).strip()
    return escape(texto) if texto else padrao


def gerar_pdf_pedido_compra(pedido):
    """
    Gera o PDF comercial de um único PedidoCompra.

    O documento usa exclusivamente os itens vinculados ao pedido recebido,
    garantindo que fornecedores diferentes nunca sejam misturados no mesmo PDF.
    """
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

    if pedido is None or not getattr(pedido, "pk", None):
        raise ValidationError("Pedido inválido para geração do PDF.")

    itens = list(pedido.itens.all().order_by("id"))
    if not itens:
        raise ValidationError("Este pedido não possui itens para gerar o PDF.")

    processo = pedido.processo
    fornecedor = pedido.fornecedor

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Pedido de compra - {pedido.numero}",
        author="ERP Alto Padrão",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "PedidoTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=colors.HexColor("#173946"),
        spaceAfter=2 * mm,
    )
    subtitle = ParagraphStyle(
        "PedidoSubtitle",
        parent=styles["Normal"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748B"),
    )
    section = ParagraphStyle(
        "PedidoSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#173946"),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "PedidoBody",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    small = ParagraphStyle(
        "PedidoSmall",
        parent=body,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748B"),
    )
    right = ParagraphStyle("PedidoRight", parent=small, alignment=TA_RIGHT)
    center = ParagraphStyle("PedidoCenter", parent=body, alignment=TA_CENTER)
    total_style = ParagraphStyle(
        "PedidoTotal",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#173946"),
        alignment=TA_RIGHT,
    )

    story = []

    story.append(Paragraph("PEDIDO DE COMPRA", title))
    story.append(
        Table(
            [[
                Paragraph(f"<b>Pedido:</b> {_texto(pedido.numero)}", body),
                Paragraph(
                    f"Emitido em {timezone.localtime().strftime('%d/%m/%Y %H:%M')}",
                    right,
                ),
            ]],
            colWidths=[125 * mm, 42 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))

    cabecalho = [
        [Paragraph("Fornecedor", small), Paragraph("Obra", small), Paragraph("Processo", small)],
        [
            Paragraph(_texto(getattr(fornecedor, "nome", fornecedor)), body),
            Paragraph(_texto(getattr(pedido.obra, "nome", pedido.obra)), body),
            Paragraph(_texto(processo.numero), body),
        ],
        [Paragraph("Data do pedido", small), Paragraph("Previsão de entrega", small), Paragraph("Status", small)],
        [
            Paragraph(pedido.data.strftime("%d/%m/%Y") if pedido.data else "-", body),
            Paragraph(
                pedido.previsao_entrega_atual.strftime("%d/%m/%Y")
                if pedido.previsao_entrega_atual
                else "-",
                body,
            ),
            Paragraph(_texto(pedido.get_status_display()), body),
        ],
    ]
    tabela_cabecalho = Table(cabecalho, colWidths=[66 * mm, 61 * mm, 40 * mm])
    tabela_cabecalho.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE6EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela_cabecalho)

    story.append(Paragraph("Itens do pedido", section))
    item_rows = [[
        Paragraph("Item", small),
        Paragraph("Qtd.", small),
        Paragraph("Un.", small),
        Paragraph("Valor unit.", small),
        Paragraph("Desconto", small),
        Paragraph("Total", small),
    ]]

    for item in itens:
        descricao = _texto(item.descricao)
        if item.especificacao:
            descricao += f"<br/><font size='7' color='#64748B'>{_texto(item.especificacao)}</font>"

        item_rows.append([
            Paragraph(descricao, body),
            Paragraph(_quantidade(item.quantidade), center),
            Paragraph(_texto(item.unidade), center),
            Paragraph(_dinheiro(item.valor_unitario), right),
            Paragraph(_dinheiro(item.desconto), right),
            Paragraph(_dinheiro(item.valor_total), right),
        ])

    tabela_itens = Table(
        item_rows,
        colWidths=[66 * mm, 17 * mm, 12 * mm, 27 * mm, 21 * mm, 24 * mm],
        repeatRows=1,
    )
    tabela_itens.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF5F7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173946")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE6EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela_itens)

    story.append(Spacer(1, 3 * mm))
    resumo = Table([
        [Paragraph("Subtotal", body), Paragraph(_dinheiro(pedido.subtotal), right)],
        [Paragraph("Descontos", body), Paragraph(f"- {_dinheiro(pedido.descontos)}", right)],
        [Paragraph("Frete", body), Paragraph(_dinheiro(pedido.frete), right)],
        [Paragraph("TOTAL DO PEDIDO", total_style), Paragraph(_dinheiro(pedido.valor_total), total_style)],
    ], colWidths=[125 * mm, 42 * mm])
    resumo.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#9CB8C2")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0F8F9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(resumo)

    story.append(Paragraph("Condições do pedido", section))
    condicoes = [
        [Paragraph("Condição de pagamento", small), Paragraph("Local de entrega", small)],
        [
            Paragraph(_texto(pedido.condicao_pagamento), body),
            Paragraph(_texto(pedido.local_entrega), body),
        ],
    ]
    tabela_condicoes = Table(condicoes, colWidths=[77 * mm, 90 * mm])
    tabela_condicoes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE6EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tabela_condicoes)

    if pedido.observacoes:
        story.append(Paragraph("Observações", section))
        story.append(Paragraph(_texto(pedido.observacoes).replace("\n", "<br/>"), body))

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        f"<b>Responsável pela emissão:</b> {_texto(_nome_usuario(pedido.responsavel))}",
        small,
    ))
    story.append(Paragraph(
        "Documento emitido eletronicamente pelo ERP Alto Padrão. "
        "Este PDF representa exclusivamente o pedido e o fornecedor identificados acima.",
        subtitle,
    ))

    doc.build(story)
    return buffer.getvalue()
