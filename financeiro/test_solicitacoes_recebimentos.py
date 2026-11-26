import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import NecessidadeCompra, PedidoCompra, PedidoCompraItem, ProcessoCompra, RecebimentoPedido
from compras.services.pedidos import cancelar_pedido, registrar_recebimento, sincronizar_parcelas_previstas_condicao
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, PlanoFinanceiro, TituloPagar
from financeiro.services.compromissos import pedidos_comprometidos
from financeiro.services.liberacoes import autorizar_liberacao, registrar_liberacao_condicional
from financeiro.services.solicitacoes_recebimentos import registrar_solicitacao_recebimento
from obras.models import Obra


class DadosRecebimentos:
    @classmethod
    def criar_dados(cls):
        cls.usuario = get_user_model().objects.create_superuser(username="recebimentos_novos")
        obra = Obra.objects.create(nome="Obra sintética", codigo="OB-SREC")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético")
        classe = PlanoFinanceiro.objects.create(codigo="12", nome="Materiais")
        apropriacao = PlanoFinanceiro.objects.create(codigo="12.1", nome="Obra", pai=classe)
        processo = ProcessoCompra.objects.create(numero="PC-SREC", obra=obra, titulo="Compra", apropriacao=apropriacao)
        cls.pedido = PedidoCompra.objects.create(
            numero="PED-SREC", processo=processo, obra=obra, fornecedor=fornecedor,
            subtotal=Decimal("1000.00"), frete=Decimal("100.00"), valor_total=Decimal("1100.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        cls.item = PedidoCompraItem.objects.create(
            pedido=cls.pedido, necessidade=necessidade, descricao="Material", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100.00"), valor_total=Decimal("1000.00"),
        )

    def receber(self, numero, quantidade, valor_item, valor_nota, **extras):
        return registrar_recebimento(
            pedido=self.pedido, usuario=self.usuario,
            quantidades={self.item.pk: quantidade}, valores_itens={self.item.pk: valor_item},
            numero_nota_fiscal=numero, valor_total_nota=valor_nota,
            arquivo_nota_fiscal=SimpleUploadedFile(f"{numero}.xml", b"<NF-SINTETICA/>"),
            **extras,
        )


class SolicitacoesRecebimentosTests(DadosRecebimentos, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.criar_dados()

    def test_pedido_presente_no_planejamento_sem_solicitacao(self):
        self.assertFalse(TituloPagar.objects.filter(pedido=self.pedido).exists())
        compromisso = pedidos_comprometidos().get(pk=self.pedido.pk)
        self.assertEqual(compromisso.valor_total, Decimal("1100.00"))

    def test_recebimentos_emitem_somente_seus_valores_e_nf_divergente(self):
        vencimento = timezone.localdate()
        primeiro = self.receber("NF-A", "8", "810", "810", vencimento_nota=vencimento)
        segundo = self.receber("NF-B", "2", "200", "300", valor_frete_nota="100", vencimento_nota=vencimento)
        titulo_a = primeiro.titulos_financeiros.get()
        titulo_b = segundo.titulos_financeiros.get()
        self.assertEqual(titulo_a.valor_original, Decimal("810.00"))
        self.assertEqual(titulo_b.valor_original, Decimal("300.00"))
        self.assertEqual(titulo_a.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(titulo_b.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(titulo_a.vencimento, vencimento)
        self.assertEqual(titulo_a.documento_numero, "NF-A")
        self.assertEqual(primeiro.liberacao_financeira.valor_esperado, Decimal("800.00"))
        self.assertTrue(primeiro.liberacao_financeira.divergencias_comerciais)
        self.assertEqual(segundo.liberacao_financeira.valor_esperado, Decimal("300.00"))
        self.assertFalse(segundo.liberacao_financeira.divergencias_comerciais)

    def test_nota_incoerente_preserva_recebimento_e_bloqueia_solicitacao(self):
        recebimento = self.receber("NF-INCOERENTE", "4", "400", "401")
        self.assertEqual(recebimento.liberacao_financeira.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)
        self.assertEqual(recebimento.itens.get().quantidade, Decimal("4"))
        self.assertFalse(TituloPagar.objects.filter(recebimento=recebimento).exists())

    def test_compra_com_nota_ja_recebida_e_reprocessamento_sao_idempotentes(self):
        recebimento = self.receber("NF-UNICA", "3", "300", "300")
        original = recebimento.liberacao_financeira
        self.assertEqual(registrar_solicitacao_recebimento(recebimento, usuario=self.usuario), original)
        with self.assertRaisesMessage(ValidationError, "já foi registrada"):
            self.receber("NF-UNICA", "3", "300", "300")
        self.assertEqual(recebimento.titulos_financeiros.count(), 1)
        self.assertEqual(self.pedido.recebimentos.count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_recebida, Decimal("3"))

    def test_parcelas_por_nota_preservam_centavos_e_intervalos(self):
        self.pedido.condicao_pagamento = "30/60/90 dias"
        self.pedido.save(update_fields=["condicao_pagamento"])
        sincronizar_parcelas_previstas_condicao(self.pedido)
        vencimento = timezone.localdate() + timedelta(days=30)
        recebimento = self.receber("NF-PARCIAL", "4", "400", "400", vencimento_nota=vencimento)
        titulos = recebimento.titulos_financeiros.order_by("parcela_ordem")
        self.assertEqual(list(titulos.values_list("valor_original", flat=True)), [Decimal("133.33"), Decimal("133.33"), Decimal("133.34")])
        self.assertEqual(list(titulos.values_list("vencimento", flat=True)), [vencimento + timedelta(days=dias) for dias in (0, 30, 60)])
        self.assertEqual(set(titulos.values_list("status", flat=True)), {TituloPagar.Status.AGUARDANDO_APROVACAO})
        self.assertEqual(len(set(titulos.values_list("referencia_externa", flat=True))), 3)

    def test_excedente_fisico_e_valor_inferior_sao_divergencias_comerciais(self):
        recebimento = self.receber("NF-EXCEDENTE", "11", "1060", "1160", valor_frete_nota="100")
        liberacao = recebimento.liberacao_financeira
        self.assertEqual(liberacao.valor_esperado, Decimal("1200.00"))
        self.assertEqual(liberacao.valor_origem, Decimal("1160.00"))
        self.assertIn("excedeu", " ".join(liberacao.divergencias_comerciais))
        self.assertIn("proporcional", " ".join(liberacao.divergencias_comerciais))
        self.assertEqual(recebimento.titulos_financeiros.get().valor_original, Decimal("1160.00"))

    def test_descontos_geral_e_por_item_sao_apropriados_so_uma_vez(self):
        self.item.desconto = Decimal("100.00")
        self.item.valor_total = Decimal("900.00")
        self.item.save(update_fields=["desconto", "valor_total"])
        self.pedido.descontos = Decimal("200.00")
        self.pedido.valor_total = Decimal("900.00")
        self.pedido.save(update_fields=["descontos", "valor_total"])

        parcial = self.receber("NF-DESCONTO-1", "4", "320", "320")
        final = self.receber("NF-DESCONTO-2", "6", "480", "580", valor_frete_nota="100")
        self.assertEqual(parcial.liberacao_financeira.valor_esperado, Decimal("320.00"))
        self.assertEqual(final.liberacao_financeira.valor_esperado, Decimal("580.00"))
        self.assertFalse(parcial.liberacao_financeira.divergencias_comerciais)
        self.assertFalse(final.liberacao_financeira.divergencias_comerciais)

    def test_antecipacao_compensada_e_cancelamento_preservam_obrigacao_recebida(self):
        antecipacao = registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO, valor=Decimal("150"),
            referencia="SINAL-SINTETICO", usuario=self.usuario, justificativa="Contrato sintético.",
        )
        titulo_antecipacao = autorizar_liberacao(antecipacao, usuario=self.usuario)
        recebimento = self.receber("NF-COMPENSA", "4", "400", "400", vencimento_nota=timezone.localdate())
        titulo = recebimento.titulos_financeiros.get()
        self.assertEqual(recebimento.liberacao_financeira.valor_compensado, Decimal("150.00"))
        self.assertEqual(titulo.valor_original + titulo_antecipacao.valor_original, Decimal("400.00"))

        cancelar_pedido(pedido=self.pedido, usuario=self.usuario, motivo="Saldo a entregar cancelado.")
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(titulo.valor_original, Decimal("250.00"))

    def test_historico_pago_impede_duplicar_e_diagnostico_preserva_registros(self):
        historico = TituloPagar.objects.create(
            numero="FIN-LEGADO-SREC", pedido=self.pedido, origem=TituloPagar.Origem.COMPRA,
            referencia_externa=f"COMPRA_PEDIDO:{self.pedido.pk}", valor_original=Decimal("1100.00"),
            status=TituloPagar.Status.PAGO,
        )
        pagamento = Pagamento.objects.create(titulo=historico, data_pagamento=timezone.localdate(), valor=Decimal("1100.00"))
        recebimento = self.receber("NF-DO-HISTORICO", "4", "400", "400", vencimento_nota=timezone.localdate())
        self.assertFalse(recebimento.titulos_financeiros.exists())
        self.assertEqual(recebimento.liberacao_financeira.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)

        saida = StringIO()
        call_command("diagnosticar_recebimentos_financeiros", pedido=self.pedido.numero, stdout=saida)
        linha, = csv.DictReader(StringIO(saida.getvalue()), delimiter=";")
        self.assertEqual(linha["nota_fiscal"], "NF-DO-HISTORICO")
        self.assertIn("Há conta anterior", linha["pendencias"])
        historico.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertEqual(historico.status, TituloPagar.Status.PAGO)
        self.assertEqual(pagamento.valor, Decimal("1100.00"))


class ConcorrenciaRecebimentosTests(DadosRecebimentos, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_registros_simultaneos_da_mesma_nota_geram_uma_unica_obrigacao(self):
        self.criar_dados()
        barreira = Barrier(2)

        def receber():
            close_old_connections()
            try:
                barreira.wait(timeout=10)
                return self.receber("NF-SIMULTANEA", "2", "200", "200").pk
            except ValidationError as erro:
                return erro.messages[0]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = [pool.submit(receber) for _ in range(2)]
            resultados = [resultado.result(timeout=30) for resultado in resultados]

        recebimento = RecebimentoPedido.objects.get(pedido=self.pedido, numero_nota_fiscal="NF-SIMULTANEA")
        self.assertIn(recebimento.pk, resultados)
        self.assertTrue(any(isinstance(resultado, str) and "já foi registrada" in resultado for resultado in resultados))
        self.assertEqual(recebimento.titulos_financeiros.count(), 1)
        self.assertEqual(self.pedido.liberacoes_financeiras.count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantidade_recebida, Decimal("2"))
