from decimal import Decimal
from unittest import TestCase

from compras.services.valores import calcular_total_proposta, preco_final_valido


class ValoresComerciaisTest(TestCase):
    def test_total_proposta_soma_frete_e_desconta_desconto_geral(self):
        self.assertEqual(
            calcular_total_proposta(
                subtotal=Decimal('1000.00'),
                desconto=Decimal('125.50'),
                frete=Decimal('80.00'),
            ),
            Decimal('954.50'),
        )

    def test_total_proposta_nunca_fica_negativo(self):
        self.assertEqual(
            calcular_total_proposta(
                subtotal=Decimal('100.00'),
                desconto=Decimal('500.00'),
                frete=Decimal('0.00'),
            ),
            Decimal('0.00'),
        )

    def test_preco_zero_nao_e_valido_para_aprovacao(self):
        self.assertFalse(preco_final_valido(Decimal('0.0000')))
        self.assertFalse(preco_final_valido(None))
        self.assertTrue(preco_final_valido(Decimal('0.0001')))
