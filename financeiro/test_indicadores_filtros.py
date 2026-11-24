from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from financeiro.models import Pagamento, PlanoFinanceiro, PrevisaoFinanceira, TituloPagar
from financeiro.services.fluxo_caixa import serie_desembolsos
from financeiro.views.indicadores import indicadores


class IndicadoresFiltrosTests(TestCase):
    def setUp(self):
        self.hoje = date(2026, 11, 18)
        self.plano = PlanoFinanceiro.objects.create(codigo="IND-UM", nome="Plano um")
        self.outro_plano = PlanoFinanceiro.objects.create(codigo="IND-DOIS", nome="Plano dois")

    def titulo(self, numero, vencimento, valor, plano, status=TituloPagar.Status.PREVISTA):
        return TituloPagar.objects.create(
            numero=numero, descricao=numero, vencimento=vencimento,
            valor_original=Decimal(valor), plano_financeiro=plano, status=status,
        )

    @patch("financeiro.views.indicadores.timezone.localdate")
    @patch("financeiro.views.indicadores.render")
    def test_cards_graficos_e_projecao_respeitam_filtros_e_datas(self, render, localdate):
        localdate.return_value = self.hoje
        render.side_effect = lambda request, template, context: HttpResponse("ok")
        self.titulo("IND-HOJE", self.hoje, "100.00", self.plano)
        self.titulo("IND-ONTEM", self.hoje - timedelta(days=1), "30.00", self.plano)
        self.titulo("IND-FUTURO", self.hoje + timedelta(days=1), "20.00", self.plano)
        self.titulo("IND-OUTRO", self.hoje, "900.00", self.outro_plano)
        pago = self.titulo("IND-PAGO", self.hoje + timedelta(days=10), "50.00", self.plano,
                           TituloPagar.Status.PAGO)
        outro_pago = self.titulo("IND-OUTRO-PAGO", self.hoje, "700.00", self.outro_plano,
                                 TituloPagar.Status.PAGO)
        Pagamento.objects.create(titulo=pago, data_pagamento=self.hoje, valor=Decimal("50.00"))
        Pagamento.objects.create(titulo=outro_pago, data_pagamento=self.hoje, valor=Decimal("700.00"))
        PrevisaoFinanceira.objects.create(
            descricao="Extra um", data_prevista=self.hoje + timedelta(days=1),
            valor_previsto=Decimal("10.00"), plano_financeiro=self.plano,
        )
        PrevisaoFinanceira.objects.create(
            descricao="Extra dois", data_prevista=self.hoje + timedelta(days=1),
            valor_previsto=Decimal("800.00"), plano_financeiro=self.outro_plano,
        )

        request = RequestFactory().get("/financeiro/indicadores/", {
            "inicio": self.hoje.isoformat(), "fim": self.hoje.isoformat(),
            "apropriacao": str(self.plano.pk),
        })
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        indicadores(request)
        contexto = render.call_args.args[2]
        self.assertEqual(contexto["total_pago"], Decimal("50.00"))
        self.assertEqual(contexto["quantidade_pagamentos"], 1)
        self.assertEqual(contexto["total_aberto"], Decimal("100.00"))
        self.assertEqual(contexto["por_origem"][0]["total"], Decimal("100.00"))
        self.assertEqual(contexto["previsao_30"], Decimal("130.00"))
        self.assertEqual(sum(item["saida"] for item in contexto["pontos_desembolso"]), Decimal("130.00"))
        self.assertEqual(contexto["por_mes"][0]["total"], Decimal("50.00"))

        serie = serie_desembolsos(inicio=self.hoje, dias=1, apropriacao=str(self.plano.pk))
        self.assertEqual(serie["total"], Decimal("130.00"))

    @patch("financeiro.views.indicadores.timezone.localdate")
    def test_origens_legadas_reconciliam_e_aba_isola_agregacoes(self, localdate):
        localdate.return_value = self.hoje
        self.client.force_login(get_user_model().objects.create_superuser('fin-indicadores-abas'))
        legado = self.titulo('LEGADO', self.hoje, '10.25', self.plano)
        legado.origem = TituloPagar.Origem.MEDICAO
        legado.save(update_fields=['origem'])
        self.titulo('MANUAL', self.hoje, '80.07', self.plano)
        pago = self.titulo('PAGO', self.hoje, '21.23', self.plano, TituloPagar.Status.PAGO)
        Pagamento.objects.create(titulo=pago, data_pagamento=self.hoje, valor='21.23')
        rota = reverse('financeiro:indicadores')
        geral = self.client.get(rota)
        self.assertEqual(geral.context['total_aberto'], Decimal('90.32'))
        self.assertEqual(sum(linha['total'] for linha in geral.context['por_origem']), Decimal('90.32'))
        self.assertNotIn('por_fornecedor', geral.context)
        origens = self.client.get(rota, {'origem': TituloPagar.Origem.MEDICAO})
        self.assertEqual(origens.context['total_aberto'], Decimal('10.25'))
        fornecedores = self.client.get(rota, {'aba': 'fornecedores'})
        self.assertNotIn('por_origem', fornecedores.context)
        self.assertEqual(sum(linha['pago'] for linha in fornecedores.context['por_fornecedor']), Decimal('21.23'))
