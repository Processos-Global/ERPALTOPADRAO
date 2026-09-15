from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from compras.models import ProcessoCompra


class GrandesFornecedoresContractTest(TestCase):
    def test_process_model_exposes_special_flow_flag(self):
        self.assertTrue(hasattr(ProcessoCompra, "fluxo_grande_fornecedor"))

    def test_price_history_difference_is_new_minus_old(self):
        from compras.models import HistoricoValorGrandeFornecedor

        historico = HistoricoValorGrandeFornecedor(
            valor_anterior=Decimal("100.00"),
            valor_novo=Decimal("90.00"),
        )
        self.assertEqual(historico.diferenca, Decimal("-10.00"))
