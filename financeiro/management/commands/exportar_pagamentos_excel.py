"""Exporta todo o contas a pagar SAARI, exceto titulos CANCELADOS.

Uso: python manage.py exportar_pagamentos_excel
     python manage.py exportar_pagamentos_excel --saida relatorios/pagamentos.xlsx

Sem dependencias de planilha alem da biblioteca padrao do Python.
A consulta usa apenas SELECTs e nao altera qualquer registro.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from financeiro.models import TituloPagar


_COR_PRIMARIA = "453330"
_COR_OURO = "B9AA72"
_FORMATOS = {"texto": 0, "moeda": 3, "data": 4, "numero": 5}
_EXCEL_MAX_LINHAS = 1048576


def _texto(valor):
    if valor is None:
        return ""
    # Remover codigos de controle proibidos pelo formato XML.
    s = str(valor)
    return "".join(c for c in s if (ord(c) >= 32 or c in "\t\n\r") and not (0xD800 <= ord(c) <= 0xDFFF) and ord(c) not in (0xFFFE, 0xFFFF))[:32767]


def _esc(valor):
    return escape(_texto(valor), {'"': '&quot;', "'": '&apos;'})


def _coluna(indice):
    s = ""
    while indice:
        indice, resto = divmod(indice - 1, 26)
        s = chr(65 + resto) + s
    return s


def _celula(referencia, valor, formato="texto", destaque=False):
    st = {"texto": 6, "moeda": 7, "data": 8, "numero": 9}[formato] if destaque else _FORMATOS[formato]
    if valor is None or valor == "":
        return f'<c r="{referencia}" s="{st}"/>'
    if isinstance(valor, (datetime, date)):
        dt = valor.date() if isinstance(valor, datetime) else valor
        serial = (dt - date(1899, 12, 30)).days
        return f'<c r="{referencia}" s="4"><v>{serial}</v></c>'
    if isinstance(valor, (Decimal, int, float)) and not isinstance(valor, bool):
        # Excel armazena moeda como decimal e aplica a formatacao por estilo.
        numero = format(valor, "f") if isinstance(valor, Decimal) else str(valor)
        return f'<c r="{referencia}" s="{st}"><v>{numero}</v></c>'
    # O tipo inlineStr mantém textos iniciados por =, +, - e @ como texto no Excel.
    return f'<c r="{referencia}" s="{st}" t="inlineStr"><is><t xml:space="preserve">{_esc(valor)}</t></is></c>'


class _PlanilhaXml:
    """Emite OOXML em fluxo: uso moderado de memoria ate com muitos titulos."""

    def __init__(self, caminho, titulo, subtitulo, cabecalhos, larguras, filtro=True):
        self.f = open(caminho, "w", encoding="utf-8", newline="")
        self.quantidade_colunas = len(cabecalhos)
        self.ultima_coluna = _coluna(self.quantidade_colunas)
        self.linha = 4
        self.filtro = filtro
        self.f.write('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
        self.f.write('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
        self.f.write('<sheetViews><sheetView workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
        self.f.write('<sheetFormatPr defaultRowHeight="19"/><cols>')
        for i, largura in enumerate(larguras, start=1):
            self.f.write(f'<col min="{i}" max="{i}" width="{largura}" customWidth="1"/>')
        self.f.write('</cols><sheetData>')
        self._linha_especial(1, [titulo], 1, 29)
        self._linha_especial(2, [subtitulo], 2, 21)
        self._linha_especial(3, [""], 0, 7)
        self._linha_especial(4, cabecalhos, 1, 30)

    def _linha_especial(self, numero, valores, estilo, altura):
        self.f.write(f'<row r="{numero}" ht="{altura}" customHeight="1">')
        for i, valor in enumerate(valores, start=1):
            ref = f"{_coluna(i)}{numero}"
            self.f.write(f'<c r="{ref}" s="{estilo}" t="inlineStr"><is><t xml:space="preserve">{_esc(valor)}</t></is></c>')
        self.f.write('</row>')

    def adicionar(self, valores, formatos=None, destaque=False):
        if self.linha >= _EXCEL_MAX_LINHAS:
            raise ValueError("Limite de linhas do Excel atingido. Divida o relatorio por periodo.")
        self.linha += 1
        self.f.write(f'<row r="{self.linha}">')
        for i, valor in enumerate(valores, start=1):
            if i > self.quantidade_colunas:
                raise ValueError("Linha tem mais colunas que o cabecalho")
            formato = (formatos or {}).get(i, "texto")
            self.f.write(_celula(f"{_coluna(i)}{self.linha}", valor, formato, destaque))
        self.f.write('</row>')

    def fechar(self):
        self.f.write('</sheetData>')
        if self.filtro:
            self.f.write(f'<autoFilter ref="A4:{self.ultima_coluna}{self.linha}"/>')
        self.f.write(f'<mergeCells count="2"><mergeCell ref="A1:{self.ultima_coluna}1"/><mergeCell ref="A2:{self.ultima_coluna}2"/></mergeCells>')
        self.f.write('</worksheet>')
        self.f.close()


def _estilos():
    # Estilos 0 padrao, 1 cabecalho/titulo, 2 subtitulo, 3 moeda,
    # 4 data, 5 inteiro, 6-9 destaque total (conforme _celula).
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;R$&quot; #,##0.00;[Red](&quot;R$&quot; #,##0.00)"/><numFmt numFmtId="165" formatCode="dd/mm/yyyy"/></numFmts>
<fonts count="3"><font><sz val="10"/><name val="Calibri"/><color rgb="FF453330"/></font><font><b/><sz val="10"/><name val="Calibri"/><color rgb="FFFFFFFF"/></font><font><b/><sz val="10"/><name val="Calibri"/><color rgb="FF453330"/></font></fonts>
<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF{_COR_PRIMARIA}"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF5F1E9"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="10">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1"/>
<xf numFmtId="164" fontId="2" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="2" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1" applyNumberFormat="1"/>
<xf numFmtId="1" fontId="2" fillId="3" borderId="0" xfId="0" applyFill="1" applyFont="1" applyNumberFormat="1"/>
</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _compactar_xlsx(saida, planilhas):
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
       '<Default Extension="xml" ContentType="application/xml"/>',
       '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
       '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    sheets = []
    rels = []
    for i, (nome, _) in enumerate(planilhas, start=1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        sheets.append(f'<sheet name="{_esc(nome)}" sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
    content_types.append('</Types>')
    n = len(planilhas) + 1
    rels.append(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{''.join(sheets)}</sheets></workbook>'''
    # Gravar atomico: nunca deixar uma planilha incompleta como resultado final.
    tmp = saida.with_name(saida.name + ".tmp")
    try:
        with ZipFile(tmp, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            z.writestr('[Content_Types].xml', ''.join(content_types))
            z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            z.writestr('xl/workbook.xml', workbook)
            z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(rels) + '</Relationships>')
            z.writestr('xl/styles.xml', _estilos())
            for i, (_, origem) in enumerate(planilhas, start=1):
                z.write(origem, f'xl/worksheets/sheet{i}.xml')
        tmp.replace(saida)
    finally:
        if tmp.exists():
            tmp.unlink()


CABECALHOS_TITULOS = [
    "ID", "Numero da conta", "Status", "Origem", "Classificacao", "Obra",
    "Beneficiario", "Documento beneficiario", "Descricao", "Especificacao",
    "Documento numero", "Pedido compra", "Parcela", "Plano financeiro", "Competencia",
    "Vencimento", "Emissao", "Valor original", "Juros", "Multa", "Outros acrescimos",
    "Desconto", "Valor liquido", "Valor pago efetivado", "Saldo em aberto",
    "Data pagamento", "Status pagamento", "Valor registrado", "Forma pagamento",
    "Meio previsto", "Referencia bancaria", "Criado em", "Observacoes",
]
CABECALHOS_PAG = [
    "ID pagamento", "Numero da conta", "Status da conta", "Beneficiario", "Obra",
    "Status do pagamento", "Data pagamento", "Valor registrado", "Valor efetivado",
    "Forma", "Referencia bancaria", "Estornado em", "Motivo estorno",
]


def gerar_relatorio(saida):
    from financeiro.models import Pagamento

    zero = Decimal('0.00')
    totais = defaultdict(lambda: {"quantidade": 0, "liquido": zero, "pago": zero, "aberto": zero})
    obras = defaultdict(lambda: {"quantidade": 0, "liquido": zero, "pago": zero, "aberto": zero})
    numero_pagamentos = 0
    discrepancias = 0
    total_registros = 0

    with TemporaryDirectory(prefix="saari_export_") as td:
        raiz = Path(td)
        titulo_path, pagamento_path, resumo_path = (raiz / n for n in ("titulos.xml", "pagamentos.xml", "resumo.xml"))
        titulo_sheet = _PlanilhaXml(titulo_path, "SAARI ERP | CONTAS A PAGAR", "Todos os status, exceto CANCELADO | Uma linha por conta", CABECALHOS_TITULOS, [9, 22, 24, 22, 20, 35, 35, 22, 42, 42, 20, 21, 13, 28, 16, 16, 16, 19, 17, 17, 20, 17, 19, 23, 20, 18, 22, 20, 23, 22, 23, 18, 38])
        pag_sheet = _PlanilhaXml(pagamento_path, "SAARI ERP | PAGAMENTOS REGISTRADOS", "Pagamentos vinculados a contas nao canceladas | Estornos ficam visiveis para auditoria", CABECALHOS_PAG, [17, 24, 23, 35, 32, 23, 19, 22, 22, 22, 25, 19, 38])
        queryset = (TituloPagar.objects
            .exclude(status=TituloPagar.Status.CANCELADO)
            .select_related('fornecedor', 'obra', 'pedido', 'plano_financeiro', 'pagamento')
            .order_by('pk'))
        for titulo in queryset.iterator(chunk_size=800):
            pagamento = getattr(titulo, 'pagamento', None)
            status_pag = pagamento.get_status_display() if pagamento else 'Sem pagamento registrado'
            forma_pag = pagamento.get_forma_display() if pagamento else ''
            pago = pagamento.valor if pagamento and pagamento.status == Pagamento.Status.EFETIVADO else zero
            liquido = titulo.valor_liquido
            aberto = titulo.saldo_aberto
            if titulo.status == TituloPagar.Status.PAGO and pago == zero:
                discrepancias += 1
            beneficiario = titulo.beneficiario_nome or (titulo.fornecedor.nome_exibicao if titulo.fornecedor_id else '') or 'Beneficiario nao definido'
            documento = titulo.beneficiario_documento or (titulo.fornecedor.documento if titulo.fornecedor_id else '')
            obra = titulo.obra.nome if titulo.obra_id else 'Sem obra'
            numero_pedido = titulo.pedido.numero if titulo.pedido_id else ''
            plano = f'{titulo.plano_financeiro.codigo} - {titulo.plano_financeiro.nome}' if titulo.plano_financeiro_id else ''
            status = titulo.get_status_display()
            for agregado in (totais[status], obras[obra]):
                agregado['quantidade'] += 1
                agregado['liquido'] += liquido
                agregado['pago'] += pago
                agregado['aberto'] += aberto
            linha = [
                titulo.pk, titulo.numero, status, titulo.get_origem_display(), titulo.get_classificacao_display(), obra,
                beneficiario, documento, titulo.descricao, titulo.especificacao_pagamento,
                titulo.documento_numero, numero_pedido, titulo.rotulo_parcela, plano, titulo.competencia,
                titulo.vencimento, titulo.data_emissao, titulo.valor_original, titulo.juros, titulo.multa, titulo.outros_acrescimos,
                titulo.desconto, liquido, pago, aberto, pagamento.data_pagamento if pagamento else None,
                status_pag, pagamento.valor if pagamento else None, forma_pag,
                titulo.get_meio_pagamento_display() if titulo.meio_pagamento else '',
                pagamento.referencia_bancaria if pagamento else '',
                timezone.localtime(titulo.criado_em).date() if titulo.criado_em else None,
                titulo.observacao,
            ]
            titulo_sheet.adicionar(linha, {1: 'numero', **{i:'data' for i in (15,16,17,26,32)}, **{i:'moeda' for i in (18,19,20,21,22,23,24,25,28)}})
            total_registros += 1
            if pagamento:
                numero_pagamentos += 1
                pag_sheet.adicionar([
                    pagamento.pk, titulo.numero, status, beneficiario, obra, status_pag,
                    pagamento.data_pagamento, pagamento.valor, pago, forma_pag,
                    pagamento.referencia_bancaria, timezone.localtime(pagamento.estornado_em).date() if pagamento.estornado_em else None,
                    pagamento.motivo_estorno,
                ], {1:'numero', 7:'data', 8:'moeda', 9:'moeda', 12:'data'})
        titulo_sheet.fechar()
        pag_sheet.fechar()

        resumo = _PlanilhaXml(resumo_path, "SAARI ERP | RESUMO FINANCEIRO", "Contas a pagar de todo o historico, exceto CANCELADO", ["Status ou obra", "Quantidade", "Valor liquido", "Valor pago efetivado", "Saldo em aberto"], [43, 18, 27, 27, 27], filtro=False)
        all_liq = sum((v['liquido'] for v in totais.values()), zero)
        all_pago = sum((v['pago'] for v in totais.values()), zero)
        all_aberto = sum((v['aberto'] for v in totais.values()), zero)
        resumo.adicionar(["TOTAL GERAL", total_registros, all_liq, all_pago, all_aberto], {2:'numero',3:'moeda',4:'moeda',5:'moeda'}, destaque=True)
        resumo.adicionar(["POR STATUS", "", "", "", ""], destaque=True)
        for status, a in sorted(totais.items()):
            resumo.adicionar([status, a['quantidade'], a['liquido'], a['pago'], a['aberto']], {2:'numero',3:'moeda',4:'moeda',5:'moeda'})
        resumo.adicionar(["", "", "", "", ""])
        resumo.adicionar(["POR OBRA", "", "", "", ""], destaque=True)
        for nome, a in sorted(obras.items(), key=lambda kv: kv[0].casefold()):
            resumo.adicionar([nome, a['quantidade'], a['liquido'], a['pago'], a['aberto']], {2:'numero',3:'moeda',4:'moeda',5:'moeda'})
        resumo.adicionar(["", "", "", "", ""])
        resumo.adicionar(["PAGAMENTOS REGISTRADOS (EFETIVADOS + ESTORNADOS)", numero_pagamentos, "", "", ""], {2:'numero'}, destaque=True)
        resumo.adicionar(["CONTAS PAGO SEM PAGAMENTO EFETIVADO", discrepancias, "", "", ""], {2:'numero'})
        resumo.adicionar(["OBS: Pagamentos estornados nao integram o valor pago efetivado.", "", "", "", ""])
        resumo.adicionar(["OBS: Cada conta entra uma unica vez, inclusive parcelas independentes.", "", "", "", ""])
        resumo.adicionar(["Gerado em", timezone.localtime().strftime('%d/%m/%Y %H:%M'), "", "", ""])
        resumo.fechar()
        _compactar_xlsx(saida, [('Resumo', resumo_path), ('Contas a pagar', titulo_path), ('Pagamentos registrados', pagamento_path)])

    return {'titulos': total_registros, 'pagamentos': numero_pagamentos, 'valor_liquido': all_liq, 'pago': all_pago, 'aberto': all_aberto, 'discrepancias': discrepancias}


class Command(BaseCommand):
    help = 'Exporta todas as contas a pagar, independentemente do status, exceto CANCELADO, em XLSX.'

    def add_arguments(self, parser):
        parser.add_argument('--saida', default='', help='Caminho do arquivo .xlsx de saida')

    def handle(self, *args, **options):
        nome = f'SAARI_PAGAMENTOS_GERAL_{timezone.localdate():%Y%m%d}.xlsx'
        downloads = Path.home() / "Downloads"
        padrao = downloads / nome if downloads.is_dir() else Path.cwd() / nome
        saida = Path(options.get('saida') or padrao).expanduser().resolve()
        if saida.suffix.lower() != '.xlsx':
            raise CommandError('O arquivo de saida deve terminar em .xlsx')
        if saida.exists():
            raise CommandError(f'O arquivo ja existe: {saida}. Escolha outro nome para preservar o anterior.')
        saida.parent.mkdir(parents=True, exist_ok=True)
        try:
            dados = gerar_relatorio(saida)
        except Exception as exc:
            if saida.exists():
                saida.unlink()
            raise CommandError(f'Falha ao gerar relatorio: {exc}') from exc
        self.stdout.write(self.style.SUCCESS(f'Excel criado: {saida}'))
        self.stdout.write(f"Contas: {dados['titulos']} | Pagamentos registrados: {dados['pagamentos']}")
        self.stdout.write(f"Liquido: R$ {dados['valor_liquido']:,.2f} | Pago: R$ {dados['pago']:,.2f} | Aberto: R$ {dados['aberto']:,.2f}")
        if dados['discrepancias']:
            self.stdout.write(self.style.WARNING(f"Atencao: {dados['discrepancias']} contas PAGO sem pagamento EFETIVADO vinculado."))
