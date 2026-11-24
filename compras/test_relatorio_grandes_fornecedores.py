from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import (GrandeFornecedorItem, GrandeFornecedorProcesso, NecessidadeCompra,
                            PedidoCompra, PedidoCompraItem, ProcessoCompra)
from compras.services.relatorio_grandes_fornecedores import linhas_relatorio_gf
from obras.models import Obra


class RelatorioGFTests(TestCase):
    def test_linhas_sem_pedido_nao_inventam_valor_e_exportam_mesmos_filtros(self):
        usuario = get_user_model().objects.create_superuser(
            username="gf_relatorio", email="gf-relatorio@example.test", password="teste"
        )
        obra = Obra.objects.create(nome="Obra GF", codigo="OB-GF-REL")
        outra = Obra.objects.create(nome="Outra obra GF", codigo="OB-GF-OUTRA")
        processo = ProcessoCompra.objects.create(
            numero="GF-REL-1", obra=obra, titulo="GF relatório", fluxo_grande_fornecedor=True
        )
        fluxo = GrandeFornecedorProcesso.objects.create(processo=processo)
        GrandeFornecedorItem.objects.create(fluxo=fluxo, item="Bancada", quantidade=Decimal("2"))
        linhas = linhas_relatorio_gf(obra=str(obra.pk))
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["pendente"], Decimal("2"))
        self.assertEqual(linhas[0].get("solicitada"), Decimal("2"))
        self.assertIsNone(linhas[0].get("contratada"))
        self.assertIsNone(linhas[0]["valor_contratado"])
        self.assertEqual(linhas_relatorio_gf(obra=str(outra.pk)), [])

        self.client.force_login(usuario)
        url = reverse("compras:relatorio_grandes_fornecedores")
        tela = self.client.get(url, {"obra": obra.pk})
        self.assertContains(tela, "Bancada")
        self.assertContains(tela, "Solicitado")
        self.assertContains(tela, 'name="formato" value="xlsx" type="submit" data-download')
        self.assertNotContains(self.client.get(url, {"obra": outra.pk}), "Bancada")
        self.assertEqual(self.client.get(url, {"obra": obra.pk, "formato": "xlsx"}).status_code, 200)
        pdf = self.client.get(url, {"obra": obra.pk, "formato": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_pedido_exibe_quantidades_e_valor_reais_sem_somar_unidades(self):
        obra = Obra.objects.create(nome="Obra pedidos GF", codigo="OB-GF-PED")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor GF")
        responsavel = get_user_model().objects.create_user(username="comprador-teste")
        processo = ProcessoCompra.objects.create(
            numero="GF-PED-1", obra=obra, titulo="GF pedido", fluxo_grande_fornecedor=True,
            comprador=responsavel,
        )
        fluxo = GrandeFornecedorProcesso.objects.create(processo=processo)
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Bancada", unidade="M2",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        pedido = PedidoCompra.objects.create(
            numero="PED-GF-1", processo=processo, obra=obra, fornecedor=fornecedor,
            valor_total=Decimal("1000"),
        )
        pedido_item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Bancada", unidade="M2",
            quantidade=Decimal("10"), quantidade_recebida=Decimal("8"),
            valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )
        GrandeFornecedorItem.objects.create(
            fluxo=fluxo, item="Bancada", unidade="M2",
            quantidade=Decimal("12"), pedido_item=pedido_item,
        )
        linhas = linhas_relatorio_gf(obra=str(obra.pk), fornecedor=str(fornecedor.pk), status="PARCIAL")
        self.assertEqual(len(linhas), 1)
        self.assertEqual((linhas[0]["quantidade"], linhas[0]["recebida"], linhas[0]["pendente"]),
                         (Decimal("10"), Decimal("8"), Decimal("2")))
        self.assertEqual(linhas[0]["valor_contratado"], Decimal("1000"))
        self.assertEqual(linhas[0]["pedido"], "PED-GF-1")
        self.assertEqual(linhas[0].get("solicitada"), Decimal("12"))
        self.assertEqual(linhas[0].get("contratada"), Decimal("10"))
        self.assertEqual(linhas[0].get("responsavel"), responsavel.username)
