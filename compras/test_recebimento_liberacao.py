from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from cadastros.models import Fornecedor
from compras.models import NecessidadeCompra, PedidoCompra, PedidoCompraItem, ProcessoCompra
from compras.services.pedidos import registrar_recebimento
from financeiro.models import LiberacaoFinanceiraPedido, TituloPagar
from obras.models import Obra


class IntegracaoRecebimentoFinanceiroTests(TestCase):
    def test_recebimento_parcial_cria_candidata_sem_alterar_valor_contratado(self):
        usuario = get_user_model().objects.create_superuser(
            username="recebimento_integrado", email="recebimento@example.test", password="teste"
        )
        obra = Obra.objects.create(nome="Obra recebimento", codigo="OB-REC-1")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor recebimento")
        processo = ProcessoCompra.objects.create(numero="PC-REC-1", obra=obra, titulo="Compra recebimento")
        pedido = PedidoCompra.objects.create(
            numero="PED-REC-1", processo=processo, obra=obra, fornecedor=fornecedor,
            valor_total=Decimal("1000.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Material", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )

        recebimento = registrar_recebimento(
            pedido=pedido, quantidades={item.pk: Decimal("8")},
            valores_itens={item.pk: Decimal("800")}, usuario=usuario,
            numero_nota_fiscal="NF-REC-800", valor_total_nota=Decimal("800"),
            arquivo_nota_fiscal=None, dados_fiscais_opcionais=True,
        )

        pedido.refresh_from_db()
        item.refresh_from_db()
        candidata = LiberacaoFinanceiraPedido.objects.get(recebimento=recebimento)
        self.assertEqual(pedido.valor_total, Decimal("1000.00"))
        self.assertEqual(item.quantidade_recebida, Decimal("8"))
        self.assertEqual(candidata.valor, Decimal("800.00"))
        self.assertEqual(candidata.status, LiberacaoFinanceiraPedido.Status.PENDENTE)
        self.assertIsNone(candidata.titulo_id)
        self.assertFalse(TituloPagar.objects.filter(pedido=pedido, valor_original=Decimal("800.00")).exists())
