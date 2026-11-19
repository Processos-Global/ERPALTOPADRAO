from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.models import (
    HistoricoProcessoCompra, NecessidadeCompra, PedidoCompra, PedidoCompraItem,
    ProcessoCompra, RecebimentoPedido, RecebimentoPedidoItem,
)
from compras.services.processos import editar_necessidade, excluir_necessidade, incluir_necessidade
from compras.services.cobertura_estoque import obter_cobertura, revalidar_necessidade
from obras.models import MovimentoEstoque, Obra
from obras.services.estoque import chave_estoque
from compras.models import ReservaEstoqueCompra
from django.urls import reverse
from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra, ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)


class CoberturaEstoqueCompraTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="estoque_compras_admin", email="estoque-compras@example.test", password="teste"
        )
        self.obra = Obra.objects.create(nome="Obra cobertura", codigo="OB-COB-01")
        self.outra = Obra.objects.create(nome="Outra cobertura", codigo="OB-COB-02")
        self.unidade = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        self.material = Material.objects.create(
            nome="Bancada teste", especificacao="Granito A", unidade=self.unidade
        )
        self.processo = ProcessoCompra.objects.create(
            numero="PC-COB-01", obra=self.obra, titulo="Compra coberta"
        )
        self.fornecedor = Fornecedor.objects.create(nome="Fornecedor cobertura")

    def registrar_entrada(self, obra, quantidade, *, especificacao="Granito A"):
        processo = ProcessoCompra.objects.create(
            numero=f"PC-ORIG-{obra.pk}-{quantidade}-{especificacao}", obra=obra, titulo="Origem"
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, material=self.material, descricao=self.material.nome,
            especificacao=especificacao, unidade="UN",
            quantidade_necessaria=quantidade, quantidade_incluida=quantidade,
        )
        pedido = PedidoCompra.objects.create(
            numero=f"PED-ORIG-{processo.pk}", processo=processo, obra=obra,
            fornecedor=self.fornecedor,
        )
        item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao=self.material.nome,
            especificacao=especificacao, unidade="UN", quantidade=quantidade,
            valor_unitario=Decimal("1"), valor_total=quantidade,
            quantidade_recebida=quantidade,
        )
        recebimento = RecebimentoPedido.objects.create(pedido=pedido)
        RecebimentoPedidoItem.objects.create(
            recebimento=recebimento, item_pedido=item, quantidade=quantidade,
            valor_recebido=quantidade,
        )

    def test_bloqueia_compra_totalmente_coberta_na_mesma_obra(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        with self.assertRaises(ValidationError):
            incluir_necessidade(
                processo=self.processo, material=self.material, quantidade=Decimal("5"),
                usuario=self.usuario,
            )
        self.assertFalse(self.processo.necessidades.exists())

    def test_solicita_apenas_falta_e_nao_usa_saldo_de_outra_obra(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        self.registrar_entrada(self.outra, Decimal("20"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("10"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("6"))

    def test_excecao_exige_justificativa_e_registra_operador(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        with self.assertRaises(ValidationError):
            incluir_necessidade(
                processo=self.processo, material=self.material, quantidade=Decimal("5"),
                usuario=self.usuario, excecao_estoque=True,
            )
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("5"),
            usuario=self.usuario, excecao_estoque=True,
            justificativa_excecao="Estoque reservado para outra frente",
        )
        self.assertEqual(necessidade.quantidade_incluida, Decimal("5"))
        evento = HistoricoProcessoCompra.objects.get(
            processo=self.processo, tipo="EXCECAO_ESTOQUE"
        )
        self.assertEqual(evento.usuario, self.usuario)
        self.assertIn("reservado", evento.descricao.lower())

    def test_especificacao_divergente_nao_bloqueia_automaticamente(self):
        self.registrar_entrada(self.obra, Decimal("10"), especificacao="Granito B")
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("5"),
            usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_incluida, Decimal("5"))

    def test_reserva_impede_dupla_cobertura_e_saida_exige_vinculo(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        primeira = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        reserva = ReservaEstoqueCompra.objects.get(necessidade=primeira)
        self.assertEqual(reserva.quantidade_disponivel, Decimal("4"))

        outro_processo = ProcessoCompra.objects.create(
            numero="PC-COB-02", obra=self.obra, titulo="Segunda necessidade"
        )
        segunda = incluir_necessidade(
            processo=outro_processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        self.assertEqual(segunda.quantidade_incluida, Decimal("10"))

        self.client.force_login(self.usuario)
        url = reverse("obras:saida_estoque", args=[self.obra.pk])
        item = chave_estoque(self.material.pk, self.material.nome, "UN")
        resposta = self.client.post(url, {"item": item, "quantidade": "4"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(MovimentoEstoque.objects.filter(obra_origem=self.obra).exists())

        resposta = self.client.post(url, {
            "item": item, "quantidade": "4", "reserva_id": reserva.pk,
        })
        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentoEstoque.objects.get(obra_origem=self.obra)
        self.assertEqual(movimento.reserva_id, reserva.pk)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.CONSUMIDA)
        revalidar_necessidade(primeira)
        with self.assertRaises(ValidationError):
            editar_necessidade(
                processo=self.processo, necessidade=primeira, material=self.material,
                quantidade=Decimal("8"), observacao="", usuario=self.usuario,
            )
        with self.assertRaises(ValidationError):
            excluir_necessidade(
                processo=self.processo, necessidade=primeira, usuario=self.usuario,
            )
        primeira.refresh_from_db()
        self.assertEqual(primeira.quantidade_necessaria, Decimal("10"))

    def test_revalidacao_detecta_novo_estoque_antes_da_aprovacao(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        self.registrar_entrada(self.obra, Decimal("4"))
        with self.assertRaises(ValidationError):
            revalidar_necessidade(necessidade)

    def test_pedido_do_mesmo_suprimento_nao_cobre_demanda_independente(self):
        importacao = ImportacaoCronogramaSuprimentos.objects.create()
        cronograma = CronogramaSuprimentosObra.objects.create(
            importacao=importacao, obra=self.obra,
            nome_aba="Obra cobertura", codigo_aba="OB-COB-01",
        )
        suprimento = ItemCronogramaSuprimento.objects.create(
            cronograma_obra=cronograma, item="Bancadas", categoria="MATERIAL",
        )
        primeiro = ProcessoCompra.objects.create(
            numero="PC-PEND-01", obra=self.obra,
            item_cronograma=suprimento, titulo="Primeira frente",
        )
        necessidade_antiga = NecessidadeCompra.objects.create(
            processo=primeiro, material=self.material, descricao=self.material.nome,
            especificacao=self.material.especificacao, unidade="UN",
            quantidade_necessaria=Decimal("5"), quantidade_incluida=Decimal("5"),
        )
        pedido = PedidoCompra.objects.create(
            numero="PED-PEND-01", processo=primeiro, obra=self.obra,
            fornecedor=self.fornecedor,
        )
        PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade_antiga,
            descricao=self.material.nome, especificacao=self.material.especificacao,
            unidade="UN", quantidade=Decimal("5"),
            valor_unitario=Decimal("1"), valor_total=Decimal("5"),
        )
        segundo = ProcessoCompra.objects.create(
            numero="PC-PEND-02", obra=self.obra,
            item_cronograma=suprimento, titulo="Segunda frente",
        )
        cobertura = obter_cobertura(
            obra=self.obra, material=self.material, unidade="UN",
            especificacao=self.material.especificacao,
            quantidade=Decimal("5"), processo=segundo,
        )
        self.assertEqual(cobertura["pendente_potencial"], Decimal("5"))
        self.assertEqual(cobertura["descoberta"], Decimal("5"))
        nova = incluir_necessidade(
            processo=segundo, material=self.material,
            quantidade=Decimal("5"), usuario=self.usuario,
        )
        self.assertEqual(nova.quantidade_incluida, Decimal("5"))
