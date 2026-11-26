import csv
from contextlib import closing
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from openpyxl import load_workbook

from cadastros.models import Fornecedor
from compras.models import PedidoCompra, ProcessoCompra
from financeiro.models import Pagamento, TituloPagar
from obras.models import Obra


class ComandosExportacaoFinanceiraTests(TestCase):
    """Conferência dos formatos e totais usando somente registros sintéticos."""

    def test_csv_frete_protege_texto_e_preserva_diferencas_negativas(self):
        obra = Obra.objects.create(nome="Obra sintética", codigo="OB-CSV")
        fornecedor = Fornecedor.objects.create(nome="@SUM(1;2)")
        processo = ProcessoCompra.objects.create(numero="PC-CSV", titulo="Pedido sintético", obra=obra)
        pedido = PedidoCompra.objects.create(
            numero="=1+1", processo=processo, obra=obra, fornecedor=fornecedor,
            subtotal=Decimal("100.00"), frete=Decimal("5.10"), valor_total=Decimal("105.10"),
        )
        TituloPagar.objects.create(
            numero="  +2+2", pedido=pedido, origem=TituloPagar.Origem.COMPRA,
            referencia_externa=f"COMPRA_PEDIDO:{pedido.pk}", valor_original=Decimal("100.00"),
        )

        saida = StringIO()
        with CaptureQueriesContext(connection) as consultas:
            call_command("diagnosticar_frete_compras", pedido=pedido.numero, stdout=saida)

        registro, = list(csv.DictReader(StringIO(saida.getvalue()), delimiter=";"))
        self.assertEqual(registro["pedido"], "'=1+1")
        self.assertEqual(registro["fornecedor"], "'@SUM(1;2)")
        self.assertEqual(registro["titulos"], "'  +2+2 (PREVISTA, 100.00)")
        self.assertEqual(registro["diferenca_financeiro_contratado"], "-5.10")
        self.assertEqual(registro["diferenca_financeiro_esperado"], "-5.10")
        self.assertTrue(consultas)
        self.assertTrue(all(consulta["sql"].lstrip().startswith("SELECT") for consulta in consultas))

    def test_xlsx_usa_celulas_de_texto_e_reconcilia_estornos_cancelados_e_saldos(self):
        obra = Obra.objects.create(nome="+2+2", codigo="OB-XLSX")
        pago = TituloPagar.objects.create(
            numero="FIN-PAGO", descricao="=1+1", beneficiario_nome=" @SUM(1,2)", obra=obra,
            valor_original=Decimal("100.00"), juros=Decimal("2.00"), multa=Decimal("1.00"),
            outros_acrescimos=Decimal("0.50"), desconto=Decimal("4.00"), status=TituloPagar.Status.PAGO,
        )
        estornado = TituloPagar.objects.create(
            numero="FIN-ESTORNADO", valor_original=Decimal("120.05"), juros=Decimal("0.25"),
            desconto=Decimal("20.20"), status=TituloPagar.Status.APROVADO,
        )
        TituloPagar.objects.create(numero="FIN-ABERTO", valor_original=Decimal("12.34"))
        TituloPagar.objects.create(
            numero="FIN-CANCELADO", valor_original=Decimal("33.33"), status=TituloPagar.Status.CANCELADO,
        )
        Pagamento.objects.create(
            titulo=pago, valor=Decimal("99.50"), data_pagamento=date(2026, 11, 30), referencia_bancaria="-1+1",
        )
        Pagamento.objects.create(
            titulo=estornado, valor=Decimal("100.10"), data_pagamento=date(2026, 10, 31),
            status=Pagamento.Status.ESTORNADO, motivo_estorno='=2<3 & "Revisão"',
        )

        with TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "pagamentos.xlsx"
            with CaptureQueriesContext(connection) as consultas:
                call_command("exportar_pagamentos_excel", saida=str(arquivo), stdout=StringIO())
            with closing(load_workbook(arquivo, read_only=True)) as planilha:
                resumo = list(planilha["Resumo"].iter_rows(min_row=5))
                contas = {linha[1].value: linha for linha in planilha["Contas a pagar"].iter_rows(min_row=5)}
                pagamentos = {linha[1].value: linha for linha in planilha["Pagamentos registrados"].iter_rows(min_row=5)}

        self.assertTrue(consultas)
        self.assertTrue(all(consulta["sql"].lstrip().startswith("SELECT") for consulta in consultas))
        self.assertEqual(set(contas), {"FIN-ABERTO", "FIN-ESTORNADO", "FIN-PAGO"})
        self.assertEqual(set(pagamentos), {"FIN-ESTORNADO", "FIN-PAGO"})
        self.assertEqual([celula.value for celula in resumo[0]], ["TOTAL GERAL", 3, 211.94, 99.5, 112.44])
        self.assertEqual(contas["FIN-ESTORNADO"][24].value, 100.1)
        self.assertEqual(pagamentos["FIN-ESTORNADO"][7].value, 100.1)
        self.assertEqual(pagamentos["FIN-ESTORNADO"][8].value, 0)
        obra_resumo, = [linha[0] for linha in resumo if linha[0].value == "+2+2"]
        for celula, valor in (
            (obra_resumo, "+2+2"),
            (contas["FIN-PAGO"][6], " @SUM(1,2)"),
            (contas["FIN-PAGO"][8], "=1+1"),
            (pagamentos["FIN-PAGO"][10], "-1+1"),
            (pagamentos["FIN-ESTORNADO"][12], '=2<3 & "Revisão"'),
        ):
            with self.subTest(celula=celula.coordinate):
                self.assertEqual((celula.value, celula.data_type), (valor, "s"))
