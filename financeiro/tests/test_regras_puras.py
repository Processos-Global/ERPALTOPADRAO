from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from financeiro.services.regras import (
    calcular_saldo_titulo,
    calcular_situacao_temporal,
    calcular_status_pagamento,
    distribuir_valor_parcelas,
)


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

    def test_vencida_continua_aberta_com_situacao_temporal(self):
        self.assertEqual(
            calcular_situacao_temporal(date(2026, 9, 8), "APROVADO", date(2026, 9, 16)),
            "VENCIDA",
        )

    def test_pago_nao_e_classificado_como_vencido(self):
        self.assertEqual(
            calcular_situacao_temporal(date(2026, 9, 8), "PAGO", date(2026, 9, 16)),
            "ENCERRADA",
        )

    def test_parcelamento_manual_preserva_total(self):
        parcelas = distribuir_valor_parcelas(Decimal("100.00"), 3)
        self.assertEqual(parcelas, [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual(sum(parcelas), Decimal("100.00"))
