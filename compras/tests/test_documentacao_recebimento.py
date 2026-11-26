from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import NecessidadeCompra, PedidoCompra, PedidoCompraItem, ProcessoCompra
from financeiro.models import LiberacaoFinanceiraPedido, PlanoFinanceiro, TituloPagar
from obras.models import Obra


class DocumentacaoRecebimentoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser("documentacao-recebimento")
        obra = Obra.objects.create(codigo="NF-QA", nome="Obra sintética NF")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético NF")
        classe = PlanoFinanceiro.objects.create(codigo="NF-QA", nome="Classe sintética")
        apropriacao = PlanoFinanceiro.objects.create(codigo="NF-QA.1", nome="Apropriação sintética", pai=classe)
        processo = ProcessoCompra.objects.create(numero="PC-NF-QA", obra=obra, titulo="Teste da NF", apropriacao=apropriacao)
        cls.pedido = PedidoCompra.objects.create(
            numero="PD-NF-QA", obra=obra, processo=processo, fornecedor=fornecedor, valor_total=Decimal("1000.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material sintético", unidade="UN", quantidade_necessaria=10, quantidade_incluida=10,
        )
        cls.item = PedidoCompraItem.objects.create(
            pedido=cls.pedido, necessidade=necessidade, descricao="Material sintético", unidade="UN",
            quantidade=10, valor_unitario=100, valor_total=1000,
        )

    def test_correcao_fiscal_concilia_obrigacao_sem_mudar_quantidade_e_estoque(self):
        self.client.force_login(self.usuario)
        recebimento_url = reverse("compras:receber_pedido", args=[self.pedido.pk])
        resposta = self.client.post(recebimento_url, {
            "numero_nota_fiscal": "NF-QA-1", "valor_total_nota": "420.00", "vencimento_nota": "2026-12-15",
            f"item_{self.item.pk}": "4", f"valor_item_{self.item.pk}": "400.00",
            "arquivo_nota_fiscal": SimpleUploadedFile("nota-sintetica.pdf", b"%PDF-1.4\n", "application/pdf"),
        })
        self.assertEqual(resposta.status_code, 302)
        recebimento = self.pedido.recebimentos.get()
        self.assertEqual(recebimento.vencimento_nota, date(2026, 12, 15))
        self.assertEqual(recebimento.liberacao_financeira.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)
        self.assertFalse(TituloPagar.objects.filter(pedido=self.pedido).exists())
        self.assertContains(self.client.get(reverse("compras:lista_pedidos")), "Corrigir documentação fiscal")

        dados = {"numero_nota_fiscal": "NF-QA-1", "valor_total_nota": "420.00", f"valor_item_{self.item.pk}": "420.00"}
        url_errada = reverse("compras:corrigir_documentacao_recebimento", args=[self.pedido.pk + 1, recebimento.pk])
        self.assertEqual(self.client.post(url_errada, dados).status_code, 404)
        correcao = reverse("compras:corrigir_documentacao_recebimento", args=[self.pedido.pk, recebimento.pk])
        self.assertEqual(self.client.get(correcao).status_code, 405)
        resposta = self.client.post(correcao, dados)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(TituloPagar.objects.filter(recebimento=recebimento).exists(), [
            str(mensagem) for mensagem in get_messages(resposta.wsgi_request)
        ])
        self.assertEqual(self.client.post(correcao, dados).status_code, 302)
        titulo = TituloPagar.objects.get(pedido=self.pedido, recebimento=recebimento)
        self.assertEqual(titulo.valor_original, Decimal("420.00"))
        self.assertEqual(titulo.vencimento, date(2026, 12, 15))
        self.assertEqual(titulo.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(titulo.conferencia, TituloPagar.Conferencia.DIVERGENCIA)
        self.assertEqual(recebimento.itens.get().quantidade, Decimal("4.0000"))
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_recebida, Decimal("4.0000"))
