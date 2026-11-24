import csv
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from financeiro.models import AnexoTituloPagar, AprovacaoTituloFinanceiro, HistoricoTituloFinanceiro, Pagamento, TituloPagar


class DiagnosticoDuplicidadesTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="auditoria_avulsa")
        self.agora = timezone.now()

    def titulo(self, numero, *, descricao, documento="NF-90", minutos=0, grupo=""):
        titulo = TituloPagar.objects.create(
            numero=numero, descricao=descricao, documento_numero=documento, beneficiario_nome="Beneficiário sintético",
            valor_original=Decimal("151.00"), vencimento=date(2026, 12, 1), criado_por=self.usuario,
            origem_detalhe=f"Lançamento manual parcelado {grupo}" if grupo else "Lançamento manual",
            parcela_ordem=1, parcela_total=2 if grupo else 1,
        )
        TituloPagar.objects.filter(pk=titulo.pk).update(criado_em=self.agora + timedelta(minutes=minutos))
        if grupo:
            HistoricoTituloFinanceiro.objects.create(titulo=titulo, usuario=self.usuario, evento="CRIADO_MANUAL", dados={
                "grupo_manual": grupo, "parcela": 1, "total_parcelas": 2,
            })
        return titulo

    def test_csv_classifica_com_evidencia_e_executa_apenas_leituras(self):
        forte = self.titulo("FIN-S1", descricao="Reparo")
        self.titulo("FIN-S2", descricao=" reparo ", minutos=5)
        self.titulo("FIN-P1", descricao="Conserto")
        self.titulo("FIN-P2", descricao="Conserto", minutos=1440)
        self.titulo("FIN-L1", descricao="Transporte", documento="NF-91")
        self.titulo("FIN-L2", descricao="Transporte", documento="NF-92")
        self.titulo("FIN-C1", descricao="Descrição anterior", grupo="abcd1234abcd")
        self.titulo("FIN-C2", descricao="Descrição alterada", grupo="abcd1234abcd")
        self.titulo("FIN-U1", descricao="Isolado")
        AnexoTituloPagar.objects.create(titulo=forte, nome_original="teste.pdf", arquivo="privado/nao-exportar.pdf")
        Pagamento.objects.create(titulo=forte, valor=Decimal("151.00"), data_pagamento=date(2026, 12, 1))
        AprovacaoTituloFinanceiro.objects.create(titulo=forte, ciclo=1, usuario=self.usuario, decisao="APROVADO")

        saida = StringIO()
        with CaptureQueriesContext(connection) as consultas:
            call_command("diagnosticar_duplicidades_financeiras", stdout=saida)
        self.assertTrue(consultas)
        self.assertTrue(all(q["sql"].lstrip().startswith("SELECT") for q in consultas))
        self.assertNotIn("privado/nao-exportar.pdf", saida.getvalue())
        linhas = {linha["codigo_fin"]: linha for linha in csv.DictReader(StringIO(saida.getvalue()))}
        self.assertEqual(len(linhas), 8)
        for prefixo, classificacao in {
            "FIN-S": "Forte suspeita", "FIN-P": "Possível coincidência",
            "FIN-L": "Solicitações semelhantes legítimas", "FIN-C": "Duplicidade tecnicamente confirmada",
        }.items():
            for sufixo in ("1", "2"):
                linha = linhas[prefixo + sufixo]
                self.assertEqual(linha["classificacao"], classificacao)
                self.assertIn(prefixo + ("2" if sufixo == "1" else "1"), linha["registros_relacionados"])
                self.assertTrue(linha["motivo"])
                self.assertTrue(linha["recomendacao"])
        self.assertEqual(linhas["FIN-S1"]["pagamento"], "EFETIVADO")
        self.assertEqual(linhas["FIN-S1"]["aprovacoes"], "1:APROVADO")
        self.assertEqual(linhas["FIN-S1"]["anexos"], "1")
        self.assertEqual(TituloPagar.objects.count(), 9)
