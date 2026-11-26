from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from cadastros.models import CategoriaGrandeFornecedor, Fornecedor
from compras.services.permissoes import compras_acao_required
from compras.services.relatorio_grandes_fornecedores import linhas_relatorio_gf
from obras.models import Obra
from usuarios.models import AcaoCompra


COLUNAS = (
    ("obra", "Obra"), ("categoria", "Categoria GF"), ("fornecedor", "Fornecedor"),
    ("processo", "Processo"), ("etapa", "Etapa"), ("pedido", "Pedido"),
    ("status_contratacao", "Contratação"), ("responsavel", "Responsável"), ("item", "Item"),
    ("especificacao", "Especificação"), ("solicitada", "Solicitada"),
    ("unidade_solicitada", "Unidade solicitada"), ("contratada", "Contratada"),
    ("recebida", "Recebida"), ("pendente", "Pendente"), ("unidade", "Unidade"),
    ("valor_contratado", "Valor contratado"), ("previsao", "Previsão entrega"),
    ("realizada", "Entrega concluída"), ("ultimo_recebimento", "Último recebimento"),
    ("desvio_comercial", "Desvio comercial (dias)"),
    ("data_necessaria_obra", "Data necessária na obra (cronograma atual)"),
    ("desvio_obra", "Desvio na obra (dias)"), ("situacao_obra", "Prazo na obra"),
    ("status_entrega", "Situação entrega"), ("pendencia", "Pendência"),
)


def _filtros(request):
    return {chave: (request.GET.get(chave) or "").strip() for chave in
            ("obra", "categoria", "fornecedor", "status", "busca")}


@compras_acao_required(AcaoCompra.VISUALIZAR)
def relatorio_grandes_fornecedores(request):
    filtros = _filtros(request)
    linhas = linhas_relatorio_gf(**filtros)
    formato = (request.GET.get("formato") or "").lower()
    if formato == "xlsx":
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell

        planilha = Workbook(write_only=True)
        folha = planilha.create_sheet("Grandes Fornecedores")
        folha.append([titulo for _, titulo in COLUNAS])
        for linha in linhas:
            celulas = []
            for chave, _ in COLUNAS:
                valor = linha[chave]
                celula = WriteOnlyCell(folha, value=valor)
                if isinstance(valor, str):
                    celula.data_type = "s"
                celulas.append(celula)
            folha.append(celulas)
        fluxo = BytesIO()
        planilha.save(fluxo)
        resposta = HttpResponse(
            fluxo.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        resposta["Content-Disposition"] = 'attachment; filename="saari_grandes_fornecedores.xlsx"'
        return resposta
    if formato == "pdf":
        from xml.sax.saxutils import escape

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A2, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        fluxo = BytesIO()
        doc = SimpleDocTemplate(fluxo, pagesize=landscape(A2), leftMargin=24, rightMargin=24)
        estilos = getSampleStyleSheet()
        chaves = tuple(chave for chave, _ in COLUNAS)
        titulos = dict(COLUNAS)
        celula = ParagraphStyle("celula_gf", parent=estilos["Normal"], fontSize=6, leading=8)
        cabecalho = ParagraphStyle("cabecalho_gf", parent=celula, textColor=colors.white)
        tabela = [[Paragraph(escape(titulos[chave]), cabecalho) for chave in chaves]]
        tabela.extend([
            [Paragraph(escape(str(linha[chave] if linha[chave] is not None else "")), celula)
             for chave in chaves] for linha in linhas
        ])
        largura = doc.width / len(chaves)
        elementos = [Paragraph("SAARI · Grandes Fornecedores", estilos["Title"]),
                    Paragraph(f"Emissão: {timezone.localtime():%d/%m/%Y %H:%M} | Filtros: {escape(str(filtros))}", estilos["Normal"]),
                    Spacer(1, 12)]
        grade = Table(tabela, colWidths=[largura] * len(chaves), repeatRows=1)
        grade.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3e3028")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), .25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elementos.append(grade)
        doc.build(elementos)
        resposta = HttpResponse(fluxo.getvalue(), content_type="application/pdf")
        resposta["Content-Disposition"] = 'attachment; filename="saari_grandes_fornecedores.pdf"'
        return resposta
    return render(request, "compras/relatorio_grandes_fornecedores.html", {
        "linhas": linhas, "filtros": filtros,
        "obras": Obra.objects.order_by("nome"),
        "categorias": CategoriaGrandeFornecedor.objects.order_by("nome"),
        "fornecedores": Fornecedor.objects.order_by("nome"),
    })
