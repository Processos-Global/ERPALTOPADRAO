from io import BytesIO
from datetime import date, datetime

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from financeiro.models import TituloPagar
from financeiro.services.agenda import _inteiro_positivo, recorte_contas_a_pagar
from financeiro.services.compromissos import contratos_assinados_separados, pedidos_comprometidos
from financeiro.services.permissoes import financeiro_acao_required, possui_acao_financeiro
from financeiro.views.indicadores import contexto_indicadores
from financeiro.views.liberacoes import recorte_liberacoes
from financeiro.views.pagamentos import recorte_pagamentos, titulos_central_pagamentos


def _contas(parametros, hoje, *, aprovacoes=False):
    filtros = parametros.copy()
    if aprovacoes:
        filtros["status"] = TituloPagar.Status.AGUARDANDO_APROVACAO
        filtros.pop("atalho", None)
    _, qs, *_ = recorte_contas_a_pagar(filtros, hoje)
    qs = qs.select_related("obra", "fornecedor", "pedido", "plano_financeiro", "pagamento", "programacao_pagamento")
    return (
        ("Código FIN", "Descrição", "Beneficiário", "Obra", "Origem", "Competência", "Vencimento",
         "Data efetiva", "Status", "Valor líquido (R$)", "Saldo (R$)", "Frete do pedido (R$)"),
        ((t.numero, t.descricao, t.beneficiario_exibicao, t.obra.nome if t.obra_id else "",
          t.get_origem_display(), t.competencia, t.vencimento, t.pagamento.data_pagamento if t.total_pago else None,
          t.get_status_display(), t.valor_liquido, t.saldo_aberto, t.pedido.frete if t.pedido_id else None)
         for t in qs.iterator(chunk_size=500)),
    )


def _pagamentos(parametros):
    aba = parametros.get("aba") or ("historico" if parametros.get("mes") else "disponiveis")
    if aba in {"disponiveis", "programados"}:
        titulos = titulos_central_pagamentos(parametros, aba)
        return (
            ("Código FIN", "Beneficiário", "Obra", "Vencimento", "Data programada", "Saldo (R$)"),
            ((t.numero, t.beneficiario_exibicao, t.obra.nome if t.obra_id else "", t.vencimento,
              t.programacao_pagamento.data_programada if aba == "programados" else None, t.saldo_aberto)
             for t in titulos.iterator(chunk_size=500)),
        )
    pagamentos, _ = recorte_pagamentos(parametros, aba)
    return (
        ("Código FIN", "Beneficiário", "Obra", "Data efetiva", "Estornado em", "Forma", "Status", "Valor (R$)"),
        ((p.titulo.numero, p.titulo.beneficiario_exibicao, p.titulo.obra.nome if p.titulo.obra_id else "",
          p.data_pagamento, timezone.localtime(p.estornado_em).date() if p.estornado_em else None,
          p.get_forma_display(), p.get_status_display(), p.valor) for p in pagamentos.iterator(chunk_size=500)),
    )


def _compromissos(parametros):
    filtros = {
        "obra_id": _inteiro_positivo(parametros.get("obra")), "fornecedor_id": _inteiro_positivo(parametros.get("fornecedor")),
        "busca": (parametros.get("q") or "").strip()[:120],
    }
    if parametros.get("aba") == "contratos":
        contratos = contratos_assinados_separados(**filtros)
        return (
            ("Contrato", "Obra", "Fornecedor", "Assinado em", "Valor (R$)"),
            ((c.numero, c.obra.nome, c.fornecedor.nome_exibicao,
              timezone.localtime(c.assinado_em).date() if c.assinado_em else None, c.valor_total)
             for c in contratos.iterator(chunk_size=500)),
        )
    pedidos = pedidos_comprometidos(**filtros, status=parametros.get("status", ""))
    return (
        ("Pedido", "Obra", "Fornecedor", "Status", "Original (R$)", "Desconto (R$)", "Frete (R$)",
         "Vigente (R$)", "Liberado (R$)", "Pago (R$)", "Saldo (R$)"),
        ((p.numero, p.obra.nome, p.fornecedor.nome_exibicao, p.get_status_display(), p.valor_total, p.descontos,
          p.frete, p.valor_vigente, p.liberado_financeiramente, p.pago_efetivado, p.saldo_financeiro)
         for p in pedidos.iterator(chunk_size=500)),
    )


def _liberacoes(parametros):
    return (
        ("Pedido", "Obra", "Fornecedor", "Tipo", "Status", "Valor de origem (R$)", "Compensado (R$)", "Líquido (R$)", "Título"),
        ((l.pedido.numero, l.pedido.obra.nome, l.pedido.fornecedor.nome_exibicao, l.get_tipo_display(),
          l.get_status_display(), l.valor_origem, l.valor_compensado, l.valor, l.titulo.numero if l.titulo_id else "")
         for l in recorte_liberacoes(parametros).iterator(chunk_size=500)),
    )


def _previsoes(parametros, hoje):
    from financeiro.services.planejamento_financeiro import recorte_planejamento, rotular_linha_planejamento

    contexto = recorte_planejamento(parametros, hoje)
    linhas = (rotular_linha_planejamento(linha) for linha in contexto["linhas"].iterator(chunk_size=500))
    return (
        ("Data", "Tipo", "Descrição", "Origem", "Beneficiário", "Obra", "Apropriação", "Certeza", "Valor (R$)"),
        ((l["data"], l["tipo"], l["descricao"], l["origem"], l["beneficiario"], l["obra"],
          l["apropriacao"], l["certeza"], l["valor"]) for l in linhas),
    )


def _indicadores(parametros, hoje):
    contexto = contexto_indicadores(parametros, hoje)
    aba = contexto["aba"]
    if aba in {"obras", "fornecedores"}:
        return (
            ("Nome", "Pago (R$)", "Em aberto (R$)", "Contratado (R$)"),
            ((l["nome"], l["pago"], l["aberto"], l["contratado"]) for l in contexto["por_entidade"]),
        )
    if aba == "custos":
        linhas = [
            ("Classe", l["titulo__plano_financeiro__pai__nome"] or "Sem classe pai", l["quantidade"], l["total"])
            for l in contexto["por_classe"]
        ] + [
            ("Apropriação", l["titulo__plano_financeiro__nome"] or "Sem apropriação", l["quantidade"], l["total"])
            for l in contexto["por_apropriacao"]
        ]
    else:
        linhas = [
            ("Período", "Pago", contexto["quantidade_pagamentos"], contexto["total_pago"]),
            ("Período", "Em aberto", None, contexto["total_aberto"]),
            ("Período", "Previsões sem título", None, contexto["total_previsto"]),
            ("Período", "Pedidos contratados", None, contexto["total_contratado"]),
            ("Projeção", "Próximos 30 dias", None, contexto["previsao_30"]),
        ] + [("Em aberto por origem", l["rotulo"], l["quantidade"], l["total"]) for l in contexto["por_origem"]]
    return ("Grupo", "Descrição", "Quantidade", "Valor (R$)"), linhas


def _criar_excel(titulo, cabecalhos, linhas):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    planilha = Workbook(write_only=True)
    folha = planilha.create_sheet(titulo[:31])
    folha.freeze_panes = "A2"
    folha.append(cabecalhos)
    for linha in linhas:
        celulas = []
        for valor in linha:
            celula = WriteOnlyCell(folha, value=valor)
            if isinstance(valor, str):
                celula.data_type = "s"
            celulas.append(celula)
        folha.append(celulas)
    buffer = BytesIO()
    planilha.save(buffer)
    return buffer.getvalue()


def _criar_pdf(titulo, cabecalhos, linhas):
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    largura, altura = landscape(A3)
    documento = canvas.Canvas(buffer, pagesize=(largura, altura))
    documento.setTitle(titulo)
    largura_coluna = (largura - 48) / len(cabecalhos)

    def nova_pagina():
        documento.setFont("Helvetica-Bold", 15)
        documento.drawString(24, altura - 28, titulo)
        documento.setFont("Helvetica-Bold", 8)
        for i, nome in enumerate(cabecalhos):
            documento.drawString(24 + i * largura_coluna, altura - 48, nome)
        documento.setFont("Helvetica", 8)
        return altura - 64

    y = nova_pagina()
    for linha in linhas:
        textos = []
        for valor in linha:
            if isinstance(valor, (datetime, date)):
                texto = valor.strftime("%d/%m/%Y")
            else:
                texto = " ".join(str(valor if valor is not None else "").split())
            textos.append(simpleSplit(texto[:180], "Helvetica", 8, largura_coluna - 8) or [""])
        altura_linha = (max(map(len, textos), default=1) + 1) * 10
        if y - altura_linha < 24:
            documento.showPage()
            y = nova_pagina()
        for i, coluna in enumerate(textos):
            for numero, texto in enumerate(coluna):
                documento.drawString(24 + i * largura_coluna, y - numero * 10, texto)
        y -= altura_linha
    documento.save()
    return buffer.getvalue()


@financeiro_acao_required("VISUALIZAR")
@require_GET
def exportar(request, tipo, formato):
    if formato not in {"xlsx", "pdf"}:
        raise Http404
    parametros = request.GET
    hoje = timezone.localdate()
    if tipo == "aprovacoes" and not possui_acao_financeiro(request.user, "APROVAR"):
        raise PermissionDenied
    relatorios = {
        "contas": ("Contas a pagar", lambda: _contas(parametros, hoje)),
        "aprovacoes": ("Aprovações pendentes", lambda: _contas(parametros, hoje, aprovacoes=True)),
        "pagamentos": ("Pagamentos", lambda: _pagamentos(parametros)),
        "compromissos": ("Compromissos", lambda: _compromissos(parametros)),
        "liberacoes": ("Liberações", lambda: _liberacoes(parametros)),
        "previsoes": ("Planejamento financeiro", lambda: _previsoes(parametros, hoje)),
        "indicadores": ("Indicadores", lambda: _indicadores(parametros, hoje)),
    }
    if tipo not in relatorios:
        raise Http404
    titulo, dados = relatorios[tipo]
    cabecalhos, linhas = dados()
    if formato == "xlsx":
        conteudo = _criar_excel(titulo, cabecalhos, linhas)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        conteudo = _criar_pdf(titulo, cabecalhos, linhas)
        content_type = "application/pdf"
    resposta = HttpResponse(conteudo, content_type=content_type)
    resposta["Content-Disposition"] = f'attachment; filename="financeiro-{tipo}.{formato}"'
    resposta["Cache-Control"] = "private, no-store"
    return resposta
