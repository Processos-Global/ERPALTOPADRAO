from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import ContratoCompra, NecessidadeCompra, PedidoCompra, PedidoCompraItem, ProcessoCompra, RecebimentoPedido, RecebimentoPedidoItem
from compras.services.pedidos import cancelar_pedido
from financeiro.services.compromissos import pedidos_comprometidos
from financeiro.services.liberacoes import autorizar_liberacao, registrar_recebimento_para_liberacao
from obras.models import Obra


class CompromissosAbasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(username="compromissos_abas")
        cls.obra = Obra.objects.create(nome="Obra sintética", codigo="OB-ABAS-COMP")
        cls.fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético")
        cls.processo = ProcessoCompra.objects.create(numero="PC-ABAS-COMP", obra=cls.obra, titulo="Compra sintética")
        cls.pedido = PedidoCompra.objects.create(
            numero="PED-ABAS-COMP", processo=cls.processo, obra=cls.obra, fornecedor=cls.fornecedor,
            subtotal=Decimal("1000.00"), frete=Decimal("100.00"), valor_total=Decimal("1100.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=cls.processo, descricao="Item sintético", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        cls.item = PedidoCompraItem.objects.create(
            pedido=cls.pedido, necessidade=necessidade, descricao="Item sintético", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )

    def _receber(self, *, frete=None):
        recebimento = RecebimentoPedido.objects.create(
            pedido=self.pedido, numero_nota_fiscal="NF-SINT-COMP", arquivo_nota_fiscal="sintetico.xml",
            valor_total_nota=Decimal("800.00") + (frete or Decimal("0")), valor_frete_nota=frete,
        )
        RecebimentoPedidoItem.objects.create(
            recebimento=recebimento, item_pedido=self.item, quantidade=Decimal("8"), valor_recebido=Decimal("800"),
        )
        return registrar_recebimento_para_liberacao(recebimento, usuario=self.usuario)

    def test_frete_contratado_sem_nota_permanece_para_conciliacao_apos_cancelamento(self):
        self._receber()
        cancelar_pedido(pedido=self.pedido, usuario=self.usuario, motivo="Materiais restantes indisponíveis")
        pedido = pedidos_comprometidos().get(pk=self.pedido.pk)
        self.assertEqual(pedido.saldo_cancelado, Decimal("200.00"))
        self.assertEqual(pedido.saldo_cancelamento_pendente, Decimal("100.00"))
        self.assertEqual(pedido.valor_vigente, Decimal("900.00"))

    def test_frete_ja_documentado_na_nf_concilia_valor_liberado_sem_duplicar_material(self):
        candidata = self._receber(frete=Decimal("100.00"))
        autorizar_liberacao(candidata, usuario=self.usuario)
        cancelar_pedido(pedido=self.pedido, usuario=self.usuario, motivo="Materiais restantes indisponíveis")
        pedido = pedidos_comprometidos().get(pk=self.pedido.pk)
        self.assertEqual(pedido.recebido_identificado, Decimal("800.00"))
        self.assertEqual(pedido.valor_documentado, Decimal("900.00"))
        self.assertEqual(pedido.frete_documentado, Decimal("100.00"))
        self.assertEqual(pedido.liberado_financeiramente, Decimal("900.00"))
        self.assertEqual(pedido.saldo_cancelado, Decimal("200.00"))
        self.assertEqual(pedido.liberado_sem_recebimento, Decimal("0.00"))

    def test_abas_consultam_so_pedidos_ou_contratos_conforme_selecao(self):
        ContratoCompra.objects.create(
            numero="CTR-ABA-ASSINADO", obra=self.obra, fornecedor=self.fornecedor, processo=self.processo,
            criado_por=self.usuario, data_contrato=date(2026, 1, 1),
            status=ContratoCompra.Status.ASSINADO, valor_total=Decimal("1100.00"),
        )
        self.client.force_login(self.usuario)
        url = reverse("financeiro:compromissos")
        with CaptureQueriesContext(connection) as consultas_pedidos:
            pedidos = self.client.get(url)
        with CaptureQueriesContext(connection) as consultas_contratos:
            contratos = self.client.get(url, {"aba": "contratos"})
        self.assertContains(pedidos, self.pedido.numero)
        self.assertNotContains(pedidos, "CTR-ABA-ASSINADO")
        self.assertContains(contratos, "CTR-ABA-ASSINADO")
        self.assertNotContains(contratos, self.pedido.numero)
        self.assertFalse(any('"compras_contratocompra"' in query["sql"] for query in consultas_pedidos))
        self.assertFalse(any('"compras_pedidocompra"' in query["sql"] for query in consultas_contratos))
