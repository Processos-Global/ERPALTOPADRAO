from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from financeiro.models import Pagamento, TituloPagar
from financeiro.services.fluxo_caixa import STATUS_ABERTOS
from financeiro.views.dashboard import _resumo_titulos_abertos


class ResumoDashboardTests(TestCase):
    def test_resumo_preserva_periodos_saldos_estorno_e_origens_em_uma_consulta(self):
        hoje = date(2026, 11, 18)

        def titulo(numero, vencimento, *, valor="100.00", status=TituloPagar.Status.PREVISTA,
                   origem=TituloPagar.Origem.MANUAL, desconto="0.00", juros="0.00"):
            return TituloPagar.objects.create(
                numero=numero, descricao=numero, vencimento=vencimento,
                valor_original=Decimal(valor), status=status, origem=origem,
                desconto=Decimal(desconto), juros=Decimal(juros),
            )

        vencido = titulo("VENCIDO", hoje - timedelta(days=1), valor="100.00", desconto="5.00", juros="2.00")
        hoje_titulo = titulo("HOJE", hoje, status=TituloPagar.Status.AGUARDANDO_APROVACAO,
                             origem=TituloPagar.Origem.COMPRA)
        titulo("DIA7", hoje + timedelta(days=7), valor="30.00")
        titulo("DIA30", hoje + timedelta(days=30), valor="40.00", origem=TituloPagar.Origem.CONTRATO)
        titulo("DIA31", hoje + timedelta(days=31), valor="60.00", origem=TituloPagar.Origem.CONTRATO)
        titulo("SEM_DATA", None, valor="50.00")
        titulo("CANCELADO", hoje, status=TituloPagar.Status.CANCELADO)
        Pagamento.objects.create(titulo=vencido, data_pagamento=hoje, valor=Decimal("20.00"),
                                 status=Pagamento.Status.EFETIVADO)
        Pagamento.objects.create(titulo=hoje_titulo, data_pagamento=hoje, valor=Decimal("100.00"),
                                 status=Pagamento.Status.ESTORNADO)

        abertos = TituloPagar.objects.filter(status__in=STATUS_ABERTOS)
        with self.assertNumQueries(1):
            resumo = _resumo_titulos_abertos(abertos, hoje, hoje + timedelta(days=7), hoje + timedelta(days=30))

        self.assertEqual((resumo["valor_vencidos"], resumo["qtd_vencidos"]), (Decimal("77.00"), 1))
        self.assertEqual((resumo["valor_7"], resumo["qtd_7"]), (Decimal("130.00"), 2))
        self.assertEqual(resumo["valor_30"], Decimal("170.00"))
        self.assertEqual((resumo["valor_aprovacao"], resumo["qtd_aprovacao"]), (Decimal("100.00"), 1))
        self.assertEqual(
            [(item["codigo"], item["total"], item["quantidade"]) for item in resumo["por_origem"]],
            [(TituloPagar.Origem.MANUAL, Decimal("157.00"), 3),
             (TituloPagar.Origem.COMPRA, Decimal("100.00"), 1)],
        )
