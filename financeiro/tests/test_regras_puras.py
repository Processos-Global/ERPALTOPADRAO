from decimal import Decimal

from django.test import SimpleTestCase

from financeiro.services.regras import calcular_saldo_titulo, calcular_status_pagamento


class RegrasFinanceirasTest(SimpleTestCase):
    def test_saldo_titulo(self):
        self.assertEqual(
            calcular_saldo_titulo(Decimal("100"), Decimal("10"), Decimal("5"), Decimal("0")),
            Decimal("105"),
        )

    def test_pagamento_integral(self):
        self.assertEqual(calcular_status_pagamento(Decimal("100"), Decimal("0")), "PENDENTE")
        self.assertEqual(calcular_status_pagamento(Decimal("100"), Decimal("100")), "PAGO")
        self.assertEqual(calcular_status_pagamento(Decimal("100"), Decimal("50")), "INCONSISTENTE")
