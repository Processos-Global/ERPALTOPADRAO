from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from financeiro.models import Pagamento, TituloPagar


class PagamentosMesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_superuser(
            username="gestor_pagamentos_mes", password="senha-teste"
        )
        self.client.force_login(usuario)

    def _pagamento(self, numero, data, valor, status=Pagamento.Status.EFETIVADO):
        titulo = TituloPagar.objects.create(
            numero=numero,
            descricao=numero,
            valor_original=valor,
            status=TituloPagar.Status.PAGO,
        )
        return Pagamento.objects.create(
            titulo=titulo, data_pagamento=data, valor=valor, status=status
        )

    def test_mes_usa_data_efetiva_e_exclui_estornos_do_total(self):
        self._pagamento("NOV-1", date(2026, 11, 1), Decimal("80.00"))
        self._pagamento("NOV-2", date(2026, 11, 30), Decimal("20.00"))
        self._pagamento("OUT", date(2026, 10, 31), Decimal("30.00"))
        self._pagamento("EST", date(2026, 11, 15), Decimal("40.00"), Pagamento.Status.ESTORNADO)

        response = self.client.get(reverse("financeiro:pagamentos"), {"mes": "2026-11"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_pago"], Decimal("100.00"))
        self.assertEqual(response.context["page_obj"].paginator.count, 3)
        self.assertContains(response, "NOV-1")
        self.assertNotContains(response, "OUT")
