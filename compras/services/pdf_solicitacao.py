from io import BytesIO

from django.core.exceptions import ValidationError
from django.utils import timezone
from compras.models import AprovacaoCompra


def _nome_usuario(usuario):
    if not usuario:
        return "-"
    nome = (usuario.get_full_name() or "").strip()
    return nome or getattr(usuario, "username", "-")


def _dinheiro(valor):
    valor = valor or 0
    texto = f"{valor:,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_pdf_solicitacao_aprovada(processo):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ValidationError(
            "O gerador de PDF requer o pacote reportlab. Instale com: pip install reportlab"
        ) from exc
    aprovacao = (
        processo.aprovacoes.filter(decisao=AprovacaoCompra.Decisao.APROVADO)
        .select_related("usuario", "alcada")
        .order_by("-criado_em", "-id")
        .first()
    )
    if aprovacao is None:
        raise ValidationError("O PDF só pode ser emitido depois da aprovação do gestor.")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Solicitação aprovada - {processo.numero}",
        author="ERP Alto Padrão",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "PdfTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#173946"),
        spaceAfter=3 * mm,
    )
    subtitle = ParagraphStyle(
        "PdfSubtitle",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#64748B"),
    )
    section = ParagraphStyle(
        "PdfSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#173946"),
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "PdfBody",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    small = ParagraphStyle(
        "PdfSmall",
        parent=body,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#64748B"),
    )
    right = ParagraphStyle("PdfRight", parent=small, alignment=TA_RIGHT)
    approved = ParagraphStyle(
        "PdfApproved",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#047857"),
        alignment=TA_CENTER,
    )

    story = []
    story.append(Paragraph("SOLICITAÇÃO DE COMPRA APROVADA", title))
    story.append(
        Table(
            [[
                Paragraph(f"<b>Processo:</b> {processo.numero}", body),
                Paragraph(f"Emitido em {timezone.localtime().strftime('%d/%m/%Y %H:%M')}", right),
            ]],
            colWidths=[125 * mm, 42 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))

    dados = [
        [Paragraph("Obra", small), Paragraph("Suprimento", small), Paragraph("Data de abertura", small)],
        [
            Paragraph(str(processo.obra), body),
            Paragraph(str(processo.item_cronograma.item if processo.item_cronograma else processo.titulo), body),
            Paragraph(processo.data_abertura.strftime("%d/%m/%Y") if processo.data_abertura else "-", body),
        ],
        [Paragraph("Solicitante", small), Paragraph("Comprador responsável", small), Paragraph("Status", small)],
        [
            Paragraph(_nome_usuario(processo.criado_por), body),
            Paragraph(_nome_usuario(processo.comprador), body),
            Paragraph(processo.get_status_display(), body),
        ],
    ]
    t = Table(dados, colWidths=[60 * mm, 60 * mm, 47 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F8FAFC")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE6EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    if processo.descricao or processo.observacao:
        story.append(Paragraph("Descrição e observações", section))
        if processo.descricao:
            story.append(Paragraph(processo.descricao, body))
        if processo.observacao:
            story.append(Spacer(1, 1.5 * mm))
            story.append(Paragraph(f"<b>Observação:</b> {processo.observacao}", body))

    atividades = list(
        processo.vinculos_atividades.select_related("atividade").order_by("atividade__nome_tarefa", "id")
    )
    if atividades:
        story.append(Paragraph("Atividades vinculadas", section))
        for vinculo in atividades:
            story.append(Paragraph(f"• {vinculo.atividade}", body))

    necessidades = list(
        processo.necessidades.select_related("material", "material__unidade").order_by("descricao", "id")
    )
    story.append(Paragraph("Itens solicitados", section))
    item_rows = [[
        Paragraph("Item", small),
        Paragraph("Especificação", small),
        Paragraph("Quantidade", small),
        Paragraph("Un.", small),
    ]]
    for item in necessidades:
        item_rows.append([
            Paragraph(item.descricao or "-", body),
            Paragraph(item.especificacao or "-", small),
            Paragraph(f"{item.quantidade_incluida:g}", body),
            Paragraph(item.unidade or "-", body),
        ])
    itens_table = Table(item_rows, colWidths=[65 * mm, 69 * mm, 22 * mm, 11 * mm], repeatRows=1)
    itens_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF5F7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173946")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#DDE6EA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(itens_table)

    adjudicacoes = list(
        processo.adjudicacoes.filter(cancelada=False)
        .select_related("necessidade", "cotacao__fornecedor")
        .order_by("cotacao__fornecedor__nome", "necessidade__descricao")
    )
    if adjudicacoes:
        story.append(Paragraph("Resultado aprovado pelo gestor", section))
        result_rows = [[
            Paragraph("Fornecedor", small),
            Paragraph("Item", small),
            Paragraph("Qtd.", small),
            Paragraph("Valor unit.", small),
            Paragraph("Total", small),
        ]]
        total_geral = 0
        for ad in adjudicacoes:
            total = ad.valor_total
            total_geral += total
            result_rows.append([
                Paragraph(ad.cotacao.fornecedor.nome, body),
                Paragraph(ad.necessidade.descricao, small),
                Paragraph(f"{ad.quantidade:g}", body),
                Paragraph(_dinheiro(ad.valor_unitario_final), body),
                Paragraph(_dinheiro(total), body),
            ])
        result_rows.append([
            Paragraph("", body),
            Paragraph("", body),
            Paragraph("", body),
            Paragraph("<b>Total aprovado</b>", body),
            Paragraph(f"<b>{_dinheiro(total_geral)}</b>", body),
        ])
        result_table = Table(result_rows, colWidths=[43 * mm, 55 * mm, 16 * mm, 27 * mm, 26 * mm], repeatRows=1)
        result_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF5F7")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0FDF4")),
            ("GRID", (0, 0), (-1, -2), 0.35, colors.HexColor("#DDE6EA")),
            ("LINEABOVE", (3, -1), (-1, -1), 0.6, colors.HexColor("#9CC9AD")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(result_table)

    story.append(Paragraph("Aprovação do gestor", section))
    aprovacao_box = Table([
        [Paragraph("APROVADO", approved)],
        [Paragraph(f"<b>Gestor:</b> {_nome_usuario(aprovacao.usuario)}", body)],
        [Paragraph(f"<b>Data:</b> {timezone.localtime(aprovacao.criado_em).strftime('%d/%m/%Y %H:%M')}", body)],
        [Paragraph(f"<b>Alçada:</b> {aprovacao.alcada.nome if aprovacao.alcada else 'Conforme permissão do usuário'}", body)],
        [Paragraph(f"<b>Observação:</b> {aprovacao.observacao or '-'}", body)],
    ], colWidths=[167 * mm])
    aprovacao_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#A7D8B8")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECFDF5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(KeepTogether(aprovacao_box))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "Documento emitido eletronicamente pelo ERP Alto Padrão a partir dos dados registrados no processo de compra.",
        small,
    ))

    doc.build(story)
    return buffer.getvalue()
