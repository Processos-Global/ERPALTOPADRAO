from decimal import Decimal
from unittest import TestCase

from financeiro.services.regras import (
    calcular_saldo_titulo,
    calcular_status_pagamento,
    nivel_certeza_ordem,
)


class RegrasFinanceirasPurasTests(TestCase):
    def test_saldo_titulo_desconta_pagamentos_sem_alterar_valor_original(self):
        self.assertEqual(
            calcular_saldo_titulo(Decimal('10000'), Decimal('250'), Decimal('100'), Decimal('3000')),
            Decimal('7150'),
        )

    def test_status_pagamento_e_parcial_quando_existe_saldo(self):
        self.assertEqual(
            calcular_status_pagamento(Decimal('10000'), Decimal('3000')),
            'PAGO_PARCIAL',
        )

    def test_status_pagamento_e_pago_quando_quitado(self):
        self.assertEqual(
            calcular_status_pagamento(Decimal('10000'), Decimal('10000')),
            'PAGO',
        )

    def test_nivel_certeza_tem_ordem_gerencial(self):
        self.assertLess(nivel_certeza_ordem('REALIZADO'), nivel_certeza_ordem('PREVISTO'))
