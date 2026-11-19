from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from financeiro.models import Pagamento, PlanoFinanceiro, TituloPagar
from financeiro.services.agenda import (
    filtrar_por_vencimento, filtrar_titulos_base, indicadores_agenda, periodo_vencimento,
)
from financeiro.views.agenda import agenda_pagamentos
from financeiro.views.titulos import titulos_lista


class AgendaFinanceiraTests(TestCase):
    def setUp(self):
        self.hoje = date(2026, 11, 18)
        self.plano = PlanoFinanceiro.objects.create(codigo="TST-AGENDA", nome="Teste agenda")

    def titulo(self, numero, vencimento, status=TituloPagar.Status.PREVISTA, valor="100.00", plano=None):
        return TituloPagar.objects.create(
            numero=numero, descricao=numero, vencimento=vencimento, status=status,
            valor_original=Decimal(valor), plano_financeiro=plano,
        )

    def test_periodos_e_indicadores_usam_datas_e_origens_corretas(self):
        vencido = self.titulo("AG-V", self.hoje - timedelta(days=1), valor="60.00", plano=self.plano)
        hoje = self.titulo("AG-H", self.hoje, status=TituloPagar.Status.APROVADO, plano=self.plano)
        self.titulo("AG-7", self.hoje + timedelta(days=7), valor="30.00", plano=self.plano)
        self.titulo("AG-30", self.hoje + timedelta(days=30), valor="40.00", plano=self.plano)
        self.titulo("AG-31", self.hoje + timedelta(days=31), valor="50.00", plano=self.plano)
        pago = self.titulo("AG-P", self.hoje + timedelta(days=40), TituloPagar.Status.PAGO, "80.00", self.plano)
        outro = self.titulo("AG-OUTRO", self.hoje, valor="200.00")
        Pagamento.objects.create(titulo=pago, data_pagamento=self.hoje, valor=Decimal("80.00"))
        Pagamento.objects.create(titulo=vencido, data_pagamento=self.hoje, valor=Decimal("20.00"),
                                 status=Pagamento.Status.ESTORNADO)

        base = filtrar_titulos_base({"apropriacao": str(self.plano.pk)})
        codigo, inicio, fim = periodo_vencimento({"periodo": "30"}, self.hoje)
        self.assertEqual((codigo, inicio, fim), ("30", self.hoje, self.hoje + timedelta(days=30)))
        periodo = filtrar_por_vencimento(base, inicio, fim)
        self.assertEqual(set(periodo.values_list("numero", flat=True)), {"AG-H", "AG-7", "AG-30"})
        totais = indicadores_agenda(base, periodo, self.hoje, inicio, fim)
        self.assertEqual(totais, {
            "vencido": Decimal("0"), "hoje": Decimal("100.00"),
            "aprovado_hoje": Decimal("100.00"), "sete_dias": Decimal("130.00"),
            "em_aberto": Decimal("170.00"), "pago": Decimal("80.00"),
        })
        self.assertNotIn(outro.pk, periodo.values_list("pk", flat=True))
        self.assertEqual(periodo_vencimento({"periodo": "amanha"}, self.hoje)[1:],
                         (self.hoje + timedelta(days=1), self.hoje + timedelta(days=1)))
        self.assertEqual(periodo_vencimento({"periodo": "mes", "mes": "11", "ano": "2026"}, self.hoje)[1:],
                         (date(2026, 11, 1), date(2026, 11, 30)))
        todos = indicadores_agenda(base, base, self.hoje, None, None)
        self.assertEqual(todos["vencido"], Decimal("60.00"))
        self.assertEqual(todos["em_aberto"], Decimal("280.00"))
        self.assertEqual(todos["pago"], Decimal("80.00"))
        apenas_pagos = filtrar_titulos_base({"status": TituloPagar.Status.PAGO})
        self.assertEqual(indicadores_agenda(apenas_pagos, apenas_pagos, self.hoje, None, None)["pago"],
                         Decimal("80.00"))

    @patch("financeiro.views.titulos.timezone.localdate")
    @patch("financeiro.views.titulos.render")
    def test_cards_da_lista_usam_mesmos_filtros_da_tabela(self, render, localdate):
        localdate.return_value = self.hoje
        render.side_effect = lambda request, template, context: HttpResponse("ok")
        self.titulo("AG-PLANO", self.hoje - timedelta(days=1), valor="80.00", plano=self.plano)
        self.titulo("AG-OUTRO", self.hoje - timedelta(days=1), valor="120.00")
        request = RequestFactory().get("/financeiro/contas-a-pagar/", {"apropriacao": str(self.plano.pk)})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        titulos_lista(request)
        contexto = render.call_args.args[2]
        self.assertEqual(contexto["kpi_vencidos"], Decimal("80.00"))
        self.assertEqual(contexto["page_obj"].paginator.count, 1)

    def test_agenda_exige_autenticacao(self):
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/financeiro/agenda/")
        request.user = AnonymousUser()
        self.assertEqual(agenda_pagamentos(request).status_code, 302)

    @patch("financeiro.views.agenda.render")
    def test_paginacao_preserva_filtros_sem_repetir_pagina(self, render):
        render.side_effect = lambda request, template, context: HttpResponse("ok")
        request = RequestFactory().get("/financeiro/agenda/", {"periodo": "hoje", "page": "2", "status": "APROVADO"})
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        agenda_pagamentos(request)
        self.assertEqual(render.call_args.args[2]["query_string"], "periodo=hoje&status=APROVADO")
