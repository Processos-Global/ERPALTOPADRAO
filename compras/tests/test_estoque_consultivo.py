from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.forms.fluxo import NecessidadeCompraForm
from compras.forms.processo import ItemCompraAberturaForm
from compras.models import (
    NecessidadeCompra, PedidoCompra, PedidoCompraItem, ProcessoCompra,
    RecebimentoPedido, RecebimentoPedidoItem, ReservaEstoqueCompra,
)
from financeiro.models import PlanoFinanceiro
from obras.models import MovimentoEstoque, Obra
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class EstoqueConsultivoTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="consulta-compras")
        PermissaoModulo.objects.create(
            usuario=cls.usuario, modulo=ModuloSistema.COMPRAS, nivel=NivelPermissao.LEITURA,
        )
        cls.obra = Obra.objects.create(nome="Obra sintética A", codigo="EST-A")
        cls.outra = Obra.objects.create(nome="Obra sintética B", codigo="EST-B")
        unidade = UnidadeMedida.objects.create(sigla="TON", descricao="Tonelada")
        cls.media = Material.objects.create(nome="Areia média", unidade=unidade)
        cls.fina = Material.objects.create(nome="Areia fina", unidade=unidade)
        unidade_legada = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        cls.legado = Material.objects.create(nome="Item sintético legado", unidade=unidade_legada)
        fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético")
        processo = ProcessoCompra.objects.create(numero="EST-1", obra=cls.obra, titulo="Areia")
        pedido = PedidoCompra.objects.create(
            numero="EST-P1", obra=cls.obra, processo=processo, fornecedor=fornecedor,
        )
        recebimento = RecebimentoPedido.objects.create(pedido=pedido)
        for material, unidade_item, quantidade in [
            (cls.media, "ton", Decimal("6.3870")),
            (cls.media, "KG", Decimal("100.0000")),
            (cls.fina, "TON", Decimal("90.0000")),
            (cls.legado, " ", Decimal("2.0000")),
        ]:
            necessidade = NecessidadeCompra.objects.create(
                processo=processo, material=material, descricao=material.nome, unidade=unidade_item,
                quantidade_necessaria=quantidade, quantidade_incluida=quantidade,
            )
            item = PedidoCompraItem.objects.create(
                pedido=pedido, necessidade=necessidade, descricao=material.nome, unidade=unidade_item,
                quantidade=quantidade, valor_unitario=1, valor_total=quantidade,
            )
            RecebimentoPedidoItem.objects.create(recebimento=recebimento, item_pedido=item, quantidade=quantidade)
        MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.TRANSFERENCIA, obra_origem=cls.obra, obra_destino=cls.outra,
            material=cls.media, descricao_item=cls.media.nome, unidade="TON", quantidade=Decimal("1.0000"),
        )
        MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.SAIDA, obra_origem=cls.obra,
            material=cls.media, descricao_item=cls.media.nome, unidade="TON", quantidade=Decimal("0.1000"),
        )

    def test_agrupa_por_obra_material_e_unidade(self):
        self.client.force_login(self.usuario)
        url = reverse("compras:estoque_materiais_obra")
        consulta = {"obra": self.obra.pk, "material": [self.media.pk, self.fina.pk, self.media.pk]}
        with self.assertNumQueries(9):
            resposta = self.client.get(url, consulta)
        self.assertEqual(resposta.json()["saldos"], {
            str(self.media.pk): {"saldo": "5.2870", "unidade": "TON"},
            str(self.fina.pk): {"saldo": "90.0000", "unidade": "TON"},
        })
        consulta["obra"] = self.outra.pk
        self.assertEqual(self.client.get(url, consulta).json()["saldos"], {
            str(self.media.pk): {"saldo": "1.0000", "unidade": "TON"},
            str(self.fina.pk): {"saldo": "0.0000", "unidade": "TON"},
        })

    def test_consulta_requer_permissao_de_compras(self):
        url = reverse("compras:estoque_materiais_obra")
        consulta = {"obra": self.obra.pk, "material": self.media.pk}
        self.assertEqual(self.client.get(url, consulta).status_code, 302)
        self.client.force_login(get_user_model().objects.create_user(username="sem-compras"))
        self.assertEqual(self.client.get(url, consulta).status_code, 403)

    def test_recebimento_legado_sem_unidade_segue_saldo_fisico(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("compras:estoque_materiais_obra"), {
            "obra": self.obra.pk, "material": self.legado.pk,
        })
        self.assertEqual(resposta.json()["saldos"][str(self.legado.pk)], {"saldo": "2.0000", "unidade": "UN"})

    def test_consulta_rejeita_parametros_invalidos_e_omite_material_desconhecido(self):
        self.client.force_login(self.usuario)
        url = reverse("compras:estoque_materiais_obra")
        self.assertEqual(self.client.get(url, {"obra": "-1", "material": self.media.pk}).status_code, 400)
        self.assertEqual(self.client.get(url, {"obra": self.obra.pk, "material": "1e2"}).status_code, 400)
        self.assertEqual(self.client.get(url, {"obra": 99999, "material": self.media.pk}).status_code, 404)
        self.assertEqual(self.client.get(url, {"obra": self.obra.pk, "material": 99999}).json(), {"saldos": {}})

    def test_compra_avulsa_e_edicao_preservam_o_total_solicitado(self):
        solicitante = get_user_model().objects.create_user(username="solicitante-compras")
        PermissaoModulo.objects.create(
            usuario=solicitante, modulo=ModuloSistema.COMPRAS, nivel=NivelPermissao.EDICAO,
        )
        classe = PlanoFinanceiro.objects.create(codigo="EST", nome="Classe sintética")
        apropriacao = PlanoFinanceiro.objects.create(codigo="EST.1", nome="Apropriação sintética", pai=classe)
        self.client.force_login(solicitante)

        resposta = self.client.post(reverse("compras:nova_compra_avulsa"), {
            "obra": self.obra.pk, "apropriacao": apropriacao.pk, "titulo": "Solicitação sintética",
            "itens-TOTAL_FORMS": 1, "itens-INITIAL_FORMS": 0,
            "itens-0-material": self.media.pk, "itens-0-quantidade": "4.5170",
            "itens-0-quantidade_compra": "3.5000",
        })
        self.assertEqual(resposta.status_code, 302)
        processo = ProcessoCompra.objects.get(titulo="Solicitação sintética")
        necessidade = processo.necessidades.get()
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("4.5170"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("3.5000"))
        self.assertFalse(ReservaEstoqueCompra.objects.filter(necessidade=necessidade).exists())

        Material.objects.filter(pk=self.media.pk).update(ativo=False)
        self.client.post(reverse("compras:editar_necessidade", args=[processo.pk, necessidade.pk]), {
            "material": self.media.pk, "quantidade_comercial": "3.8000",
        })
        necessidade.refresh_from_db()
        self.assertEqual(necessidade.quantidade_incluida, Decimal("3.8000"))

        edicao = self.client.post(reverse("compras:editar_necessidade", args=[processo.pk, necessidade.pk]), {
            "material": self.fina.pk, "quantidade_comercial": "4.5170", "observacao": "Areia fina cotada",
        })
        self.assertEqual(edicao.status_code, 302)
        necessidade.refresh_from_db()
        self.assertEqual(necessidade.material_id, self.fina.pk)
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("4.5170"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("4.5170"))

    def test_formularios_aceitam_quatro_casas_no_limite_minimo(self):
        abertura = ItemCompraAberturaForm({
            "material": self.media.pk, "quantidade": "0.0001", "quantidade_compra": "0.0001",
        })
        edicao = NecessidadeCompraForm({"material": self.media.pk, "quantidade_comercial": "0.0001"}, edicao=True)
        self.assertTrue(abertura.is_valid(), abertura.errors)
        self.assertTrue(edicao.is_valid(), edicao.errors)
