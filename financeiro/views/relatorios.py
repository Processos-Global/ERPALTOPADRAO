from datetime import datetime, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
import re
import shutil
import tempfile
import zipfile

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from financeiro.models import (
    AprovacaoTituloFinanceiro,
    ItemRelatorioPagamento,
    RelatorioPagamento,
    TituloPagar,
)
from financeiro.services.numeracao import gerar_numero
from financeiro.services.permissoes import financeiro_acao_required


def _parse_data(valor):
    try:
        return datetime.strptime(valor or "", "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _intervalo_local(data_inicio, data_fim):
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(data_inicio, time.min), tz)
    fim = timezone.make_aware(datetime.combine(data_fim, time.max), tz)
    return inicio, fim


def _aprovacoes_disponiveis(data_inicio=None, data_fim=None, obra_ids=None):
    qs = (
        AprovacaoTituloFinanceiro.objects.filter(
            decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,
            titulo__status=TituloPagar.Status.APROVADO,
            item_relatorio_pagamento__isnull=True,
        )
        .select_related(
            "titulo",
            "titulo__fornecedor",
            "titulo__obra",
            "titulo__pedido",
            "titulo__plano_financeiro",
            "titulo__plano_financeiro__pai",
            "titulo__pagamento",
            "usuario",
        )
        .order_by("criado_em", "id")
    )
    if data_inicio:
        inicio, _ = _intervalo_local(data_inicio, data_inicio)
        qs = qs.filter(criado_em__gte=inicio)
    if data_fim:
        _, fim = _intervalo_local(data_fim, data_fim)
        qs = qs.filter(criado_em__lte=fim)
    if obra_ids:
        qs = qs.filter(titulo__obra_id__in=obra_ids)
    return qs


def _parse_obra_id(valor):
    try:
        numero = int(valor)
        return numero if numero > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_obras(valores):
    """IDs positivos e únicos vindos de checkboxes; ausência = todas as obras."""
    ids = set()
    for valor in valores:
        try:
            numero = int(valor)
            if numero > 0:
                ids.add(numero)
        except (ValueError, TypeError):
            continue
    return sorted(ids)


def _url_relatorios(data_inicio=None, data_fim=None, obra_ids=None):
    params = []
    if data_inicio:
        params.append(("inicio", data_inicio.strftime("%Y-%m-%d")))
    if data_fim:
        params.append(("fim", data_fim.strftime("%Y-%m-%d")))
    params.extend(("obra", pk) for pk in (obra_ids or []))
    base = reverse("financeiro:relatorios_pagamento")
    return f"{base}?{urlencode(params)}" if params else base


def _dados_item(aprovacao):
    titulo = aprovacao.titulo
    apropriacao = ""
    if titulo.plano_financeiro_id:
        apropriacao = titulo.plano_financeiro.caminho

    pedido_numero = ""
    if titulo.pedido_id:
        pedido_numero = str(getattr(titulo.pedido, "numero", "") or getattr(titulo.pedido, "codigo", "") or titulo.pedido_id)

    centro_custo_codigo = ""
    centro_custo_descricao = ""
    if titulo.plano_financeiro_id:
        centro_custo_codigo = titulo.plano_financeiro.codigo or ""
        centro_custo_descricao = titulo.plano_financeiro.nome or ""

    fornecedor = titulo.fornecedor if titulo.fornecedor_id else None

    return {
        "aprovacao": aprovacao,
        "titulo": titulo,
        "data_aprovacao": aprovacao.criado_em,
        "conta_numero": titulo.numero,
        "pedido_numero": pedido_numero,
        "obra_nome": str(titulo.obra) if titulo.obra_id else "",
        "beneficiario_nome": titulo.beneficiario_exibicao,
        "beneficiario_documento": titulo.beneficiario_documento or (fornecedor.documento if fornecedor else "") or "",
        "beneficiario_banco": titulo.beneficiario_banco or (fornecedor.banco if fornecedor else "") or "",
        "beneficiario_agencia": titulo.beneficiario_agencia or (fornecedor.agencia if fornecedor else "") or "",
        "beneficiario_conta_corrente": titulo.beneficiario_conta_corrente or (fornecedor.conta_corrente if fornecedor else "") or "",
        "beneficiario_operacao": titulo.beneficiario_operacao or (fornecedor.operacao_bancaria if fornecedor else "") or "",
        "beneficiario_pix": titulo.beneficiario_pix or (fornecedor.pix if fornecedor else "") or "",
        "beneficiario_titular": titulo.beneficiario_titular or (fornecedor.titular_conta if fornecedor else "") or "",
        "descricao": titulo.descricao,
        "especificacao_pagamento": titulo.especificacao_pagamento or "",
        "apropriacao": apropriacao,
        "parcela": titulo.rotulo_parcela if titulo.rotulo_parcela != "—" else "",
        "vencimento": titulo.vencimento,
        "valor": titulo.saldo_aberto,
        "origem": titulo.get_origem_display(),
        "observacao": titulo.observacao or "",
        "documento_numero": titulo.documento_numero or "",
        "competencia": titulo.competencia,
        "centro_custo_codigo": centro_custo_codigo,
        "centro_custo_descricao": centro_custo_descricao,
        "forma_pagamento": titulo.condicao_pagamento or "",
    }


@financeiro_acao_required("VISUALIZAR")
def relatorios_pagamento(request):
    hoje = timezone.localdate()
    data_inicio = _parse_data(request.GET.get("inicio"))
    data_fim = _parse_data(request.GET.get("fim"))
    obra_ids = _parse_obras(request.GET.getlist("obra"))

    if data_inicio and data_fim and data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio

    aprovacoes = list(_aprovacoes_disponiveis(data_inicio, data_fim, obra_ids=obra_ids))
    itens_preview = [
        {"aprovacao": a, "titulo": a.titulo, "valor": a.titulo.saldo_aberto}
        for a in aprovacoes
    ]
    total_preview = sum((item["valor"] for item in itens_preview), Decimal("0"))

    obras = list(
        TituloPagar.objects.filter(obra__isnull=False)
        .values("obra_id", "obra__nome")
        .distinct()
        .order_by("obra__nome")
    )
    obras_selecionadas = set(obra_ids)

    historico = list(
        RelatorioPagamento.objects.select_related("emitido_por")
        .annotate(total_itens=Sum("itens__valor"))
        .order_by("-emitido_em", "-id")[:100]
    )

    return render(
        request,
        "financeiro/relatorios_pagamento.html",
        {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "obras": obras,
            "obra_ids": obra_ids,
            "obras_selecionadas": obras_selecionadas,
            "itens_preview": itens_preview,
            "total_preview": total_preview,
            "historico": historico,
        },
    )


@financeiro_acao_required("PAGAR")
@require_POST
@transaction.atomic
def relatorio_pagamento_emitir(request):
    data_inicio = _parse_data(request.POST.get("inicio"))
    data_fim = _parse_data(request.POST.get("fim"))
    obra_ids = _parse_obras(request.POST.getlist("obra"))

    if data_inicio and data_fim and data_fim < data_inicio:
        messages.error(request, "A data final não pode ser anterior à data inicial.")
        return redirect(_url_relatorios(data_inicio, data_fim, obra_ids))

    ids_raw = request.POST.getlist("aprovacoes")
    ids = {int(v) for v in ids_raw if v.isdigit() and int(v) > 0}
    if not ids or len(ids) != len(ids_raw):
        messages.error(request, "Selecione ao menos um pagamento válido.")
        return redirect(_url_relatorios(data_inicio, data_fim, obra_ids))
    # Reconsulta aprovações e bloqueia os registros, evitando emissões repetidas.
    aprovacoes = list(_aprovacoes_disponiveis(data_inicio, data_fim, obra_ids=obra_ids).filter(pk__in=ids).select_for_update())
    if len(aprovacoes) != len(ids):
        messages.error(request, "Um ou mais pagamentos já foram emitidos ou não estão disponíveis. Atualize a seleção.")
        return redirect(_url_relatorios(data_inicio, data_fim, obra_ids))
    relatorio = RelatorioPagamento.objects.create(
        numero=gerar_numero("RELATORIO_PAGAMENTO"),
        periodo_inicio=min(a.criado_em.date() for a in aprovacoes),
        periodo_fim=max(a.criado_em.date() for a in aprovacoes),
        emitido_por=request.user,
    )

    itens = []
    total = Decimal("0")
    for aprovacao in aprovacoes:
        dados = _dados_item(aprovacao)
        total += dados["valor"]
        itens.append(ItemRelatorioPagamento(relatorio=relatorio, **dados))

    ItemRelatorioPagamento.objects.bulk_create(itens)
    relatorio.quantidade_itens = len(itens)
    relatorio.valor_total = total
    relatorio.save(update_fields=["quantidade_itens", "valor_total"])

    messages.success(
        request,
        f"Relatório {relatorio.numero} emitido com {len(itens)} pagamento(s).",
    )
    return redirect("financeiro:relatorio_pagamento_excel", pk=relatorio.pk)


@financeiro_acao_required("VISUALIZAR")
def relatorio_pagamento_excel(request, pk):
    relatorio = get_object_or_404(
        RelatorioPagamento.objects.select_related("emitido_por"),
        pk=pk,
    )

    obra_id = _parse_obra_id(request.GET.get("obra"))
    itens_qs = (
        relatorio.itens.select_related("titulo", "titulo__pedido", "titulo__obra")
        .prefetch_related("titulo__anexos", "titulo__pedido__anexos", "titulo__pedido__recebimentos")
        .order_by("data_aprovacao", "id")
    )
    if obra_id:
        itens_qs = itens_qs.filter(titulo__obra_id=obra_id)

    itens = list(itens_qs)
    if obra_id and not itens:
        messages.warning(request, "Esta obra não possui itens dentro do relatório selecionado.")
        return redirect("financeiro:relatorios_pagamento")

    obra_reemissao = None
    if obra_id and itens:
        obra_reemissao = itens[0].obra_nome or str(getattr(itens[0].titulo, "obra", "") or "Obra")

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        messages.error(request, "A biblioteca openpyxl não está instalada no servidor.")
        return redirect("financeiro:relatorios_pagamento")

    wb = Workbook()
    ws = wb.active
    ws.title = "Programação de pagamentos"
    ws.sheet_view.showGridLines = False

    # Modelo utilizado pelo setor financeiro: uma linha por compromisso/parcela.
    cabecalhos = [
        "ID_Compromisso",
        "Parcela/Evento",
        "Nº da NF",
        "Data_Prevista",
        "Competência",
        "Fornecedor",
        "Centro_Custo",
        "Descrição_CC",
        "Valor_Previsto",
        "Valor_Reprogramado",
        "Valor_Final_Previsto",
        "Status",
        "Forma_Pagamento",
        "Observações",
        "DADOS BENEFICIÁRIO",
    ]

    azul = "1F4E78"
    amarelo = "FFF2CC"
    branco = "FFFFFF"
    azul_texto = "0000FF"
    borda_fina = Side(style="thin", color="000000")

    for coluna, texto in enumerate(cabecalhos, 1):
        celula = ws.cell(row=1, column=coluna, value=texto)
        celula.fill = PatternFill("solid", fgColor=azul)
        celula.font = Font(bold=True, color=branco)
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        celula.border = Border(left=borda_fina, right=borda_fina, top=borda_fina, bottom=borda_fina)

    for linha, item in enumerate(itens, 2):
        competencia = item.competencia or item.vencimento
        competencia_texto = competencia.strftime("%b/%y").lower() if competencia else ""
        parcela = item.parcela or "ÚNICA"

        dados_beneficiario = "\n".join([
            f"Banco: {item.beneficiario_banco or ''}",
            f"AGÊNCIA: {item.beneficiario_agencia or ''}",
            f"CONTA CORRENTE: {item.beneficiario_conta_corrente or ''}",
            f"OPERAÇÃO: {item.beneficiario_operacao or ''}",
            f"CNPJ: {item.beneficiario_documento or ''}",
            f"PIX: {item.beneficiario_pix or ''}",
            f"TITULAR: {item.beneficiario_titular or ''}",
        ])

        valores = [
            item.conta_numero,
            parcela,
            item.documento_numero,
            item.vencimento,
            competencia_texto,
            item.beneficiario_nome,
            item.centro_custo_codigo,
            item.centro_custo_descricao,
            item.valor,
            None,
            item.valor,
            "Previsto",
            item.forma_pagamento,
            item.observacao,
            dados_beneficiario,
        ]

        for coluna, valor in enumerate(valores, 1):
            celula = ws.cell(row=linha, column=coluna, value=valor)
            celula.alignment = Alignment(vertical="center", wrap_text=True)
            celula.border = Border(left=borda_fina, right=borda_fina, top=borda_fina, bottom=borda_fina)

        # Colunas de programação seguem o visual da planilha de referência.
        for coluna in (1, 2, 3, 4, 9, 10, 12, 13, 14, 15):
            ws.cell(row=linha, column=coluna).fill = PatternFill("solid", fgColor=amarelo)

        for coluna in (1, 2, 3, 4, 9, 12, 13):
            ws.cell(row=linha, column=coluna).font = Font(color=azul_texto)

        ws.cell(row=linha, column=4).number_format = "dd/mm/yyyy"
        ws.cell(row=linha, column=9).number_format = 'R$ #,##0.00'
        ws.cell(row=linha, column=10).number_format = 'R$ #,##0.00'
        ws.cell(row=linha, column=11).number_format = 'R$ #,##0.00'
        ws.row_dimensions[linha].height = 96

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:O{max(1, len(itens) + 1)}"
    ws.row_dimensions[1].height = 28

    larguras = [18, 16, 16, 16, 14, 32, 15, 42, 18, 21, 21, 16, 20, 34, 38]
    for idx, largura in enumerate(larguras, 1):
        ws.column_dimensions[get_column_letter(idx)].width = largura

    # Segunda aba: rastreabilidade da emissão sem alterar o layout operacional.
    meta = wb.create_sheet("Controle da emissão")
    meta.sheet_view.showGridLines = False
    total_exportado = sum((item.valor for item in itens), Decimal("0"))
    controle = [
        ("Relatório", relatorio.numero),
        ("Período das aprovações", f"{relatorio.periodo_inicio:%d/%m/%Y} a {relatorio.periodo_fim:%d/%m/%Y}"),
        ("Emitido em", timezone.localtime(relatorio.emitido_em).strftime("%d/%m/%Y %H:%M")),
        ("Emitido por", (relatorio.emitido_por.get_full_name() or relatorio.emitido_por.get_username()) if relatorio.emitido_por else ""),
        ("Reemissão por obra", obra_reemissao or "Todas as obras"),
        ("Quantidade exportada", len(itens)),
        ("Valor exportado", total_exportado),
    ]
    for linha, (rotulo, valor) in enumerate(controle, 1):
        meta.cell(row=linha, column=1, value=rotulo).font = Font(bold=True)
        meta.cell(row=linha, column=2, value=valor)
    meta.column_dimensions["A"].width = 24
    meta.column_dimensions["B"].width = 46
    meta.cell(row=7, column=2).number_format = 'R$ #,##0.00'

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    def nome_seguro(valor, padrao="SEM_IDENTIFICACAO"):
        texto = re.sub(r"[^A-Za-z0-9._-]+", "_", str(valor or "").strip())
        return texto.strip("._-")[:90] or padrao

    pacote = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024, mode="w+b")
    incluidos = 0
    with zipfile.ZipFile(pacote, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{nome_seguro(relatorio.numero)}.xlsx", buffer.getvalue())

        instrucoes = [
            f"Relatório: {relatorio.numero}",
            f"Reemissão por obra: {obra_reemissao or 'Todas as obras'}",
            f"Itens neste pacote: {len(itens)}",
            f"Valor neste pacote: R$ {total_exportado:.2f}",
            "",
            "A pasta DOCUMENTOS contém os anexos das Contas a Pagar e também os documentos herdados dos Pedidos de Compra vinculados.",
            "Cada subpasta é identificada por PEDIDO + CONTA + BENEFICIÁRIO para facilitar a rastreabilidade.",
            "Quando não existe pedido vinculado, a identificação começa por SEM_PEDIDO.",
        ]
        zf.writestr("LEIA-ME.txt", "\n".join(instrucoes).encode("utf-8"))

        for item in itens:
            titulo = item.titulo
            pedido = item.pedido_numero or (getattr(titulo.pedido, "numero", "") if titulo.pedido_id else "") or "SEM_PEDIDO"
            pasta = "DOCUMENTOS/{pedido}__{conta}__{beneficiario}".format(
                pedido=nome_seguro(pedido, "SEM_PEDIDO"),
                conta=nome_seguro(item.conta_numero, "SEM_CONTA"),
                beneficiario=nome_seguro(item.beneficiario_nome, "SEM_BENEFICIARIO"),
            )

            campos = []
            if titulo.arquivo_documento and titulo.arquivo_documento.name:
                campos.append((titulo.arquivo_documento, Path(titulo.arquivo_documento.name).name))
            campos.extend((anexo.arquivo, anexo.nome_original or Path(anexo.arquivo.name).name) for anexo in titulo.anexos.all())
            if titulo.pedido_id:
                campos.extend(
                    (anexo.arquivo, f"PEDIDO_{anexo.nome_arquivo}")
                    for anexo in titulo.pedido.anexos.all()
                    if anexo.arquivo and anexo.arquivo.name
                )
                campos.extend(
                    (recebimento.arquivo_nota_fiscal, f"NF_{recebimento.nome_arquivo_nota_fiscal}")
                    for recebimento in titulo.pedido.recebimentos.all()
                    if recebimento.arquivo_nota_fiscal and recebimento.arquivo_nota_fiscal.name
                )

            usados = set()
            for indice, (campo, nome_original) in enumerate(campos, start=1):
                base_nome = nome_seguro(Path(nome_original).stem, f"anexo_{indice}")
                extensao_bruta = Path(nome_original).suffix.lower()
                extensao = extensao_bruta if re.fullmatch(r"\.[a-z0-9]{1,10}", extensao_bruta) else ""
                candidato = f"{base_nome}{extensao}"
                contador = 2
                while candidato.lower() in usados:
                    candidato = f"{base_nome}_{contador}{extensao}"
                    contador += 1
                usados.add(candidato.lower())

                try:
                    origem = campo.open("rb")
                except (FileNotFoundError, OSError):
                    continue
                try:
                    with zf.open(f"{pasta}/{candidato}", "w") as destino:
                        shutil.copyfileobj(origem, destino, length=1024 * 1024)
                    incluidos += 1
                finally:
                    origem.close()

        if incluidos == 0:
            zf.writestr("DOCUMENTOS/SEM_ANEXOS.txt", "Nenhum documento estava anexado às contas deste relatório.")

    pacote.seek(0)
    sufixo_obra = f"__{nome_seguro(obra_reemissao, 'OBRA')}" if obra_reemissao else ""
    response = FileResponse(
        pacote,
        as_attachment=True,
        filename=f"{relatorio.numero}{sufixo_obra}.zip",
        content_type="application/zip",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response

