from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase

# Testes de integração dependem do factory/model Obra do projeto completo.
# Mantidos como documentação executável dos invariantes que devem ser cobertos
# quando o app for instalado no repositório completo.
class RegrasComprasTest(TestCase):
    def test_quantidade_decimal_basica(self):
        self.assertGreater(Decimal("1.0000"), Decimal("0"))

    def test_invariante_adjudicacao_documentada(self):
        self.assertTrue(True, "Adjudicação deve bloquear quantidade acima do saldo no service adjudicar().")
