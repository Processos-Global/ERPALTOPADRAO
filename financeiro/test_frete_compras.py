import csv
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import (
    AdjudicacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    NecessidadeCompra,
    NegociacaoItem,
    ProcessoCompra,
)
from compras.services.comercial import total_aprovacao_processo
from compras.services.pedidos import cancelar_pedido, gerar_pedidos, registrar_recebimento
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.liberacoes import autorizar_liberacao
from financeiro.services.matching import avaliar_conferencia
from obras.models import Obra


class FreteComprasTests(TestCase):
    """Reconciliação com valores sintéticos e centavos calculados de forma independente."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(username="frete_admin")
        obra = Obra.objects.create(nome="Obra sintética", codigo="OB-FRETE")
        cls.processo = ProcessoCompra.objects.create(
            numero="PC-FRETE", obra=obra, titulo="Pedido sintético",
            status=ProcessoCompra.Status.APROVADO,
        )

    def cotacao(self, *, nome="Fornecedor sintético A", frete="150.00", desconto="0.00", condicao=""):
        return CotacaoFornecedor.objects.create(
            processo=self.processo, fornecedor=Fornecedor.objects.create(nome=nome),
            frete=Decimal(frete), desconto_proposta=Decimal(desconto), condicao_pagamento=condicao,
        )

    def adjudicar(self, cotacao, preco, *, quantidade="1", desconto="0.00"):
        necessidade = NecessidadeCompra.objects.create(
            processo=self.processo, descricao="Item sintético", unidade="UN",
            quantidade_necessaria=Decimal(quantidade), quantidade_incluida=Decimal(quantidade),
        )
        item = CotacaoFornecedorItem.objects.create(
            cotacao=cotacao, necessidade=necessidade, quantidade=Decimal(quantidade),
            valor_unitario_cotado=Decimal(preco),
        )
        AdjudicacaoCompra.objects.create(
            processo=self.processo, necessidade=necessidade, cotacao=cotacao, item_cotado=item,
            quantidade=Decimal(quantidade), valor_unitario_final=Decimal(preco),
            desconto_final=Decimal(desconto),
        )
        return item

    def receber(self, pedido, *, numero, quantidade, valor_items, valor_nf, **opcionais):
        item = pedido.itens.get()
        return registrar_recebimento(
            pedido=pedido, quantidades={item.pk: Decimal(quantidade)},
            valores_itens={item.pk: Decimal(valor_items)}, usuario=self.usuario,
            numero_nota_fiscal=numero, valor_total_nota=Decimal(valor_nf),
            arquivo_nota_fiscal=SimpleUploadedFile(f"{numero}.xml", b"<NF-sintetica/>"),
            **opcionais,
        ).liberacao_financeira

    def test_parcelas_com_frete_reconciliam_sem_titulo_transitorio_ou_duplicidade(self):
        self.adjudicar(self.cotacao(condicao="Parcelado em 3x"), "1000.00")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        titulos = pedido.titulos_financeiros.order_by("parcela_ordem", "pk")
        esperado = [Decimal("383.33"), Decimal("383.33"), Decimal("383.34")]

        self.assertEqual(pedido.valor_total, Decimal("1150.00"))
        self.assertEqual(titulos.count(), 3)
        self.assertEqual(list(pedido.parcelas_previstas.order_by("ordem").values_list("valor", flat=True)), esperado)
        self.assertEqual(list(titulos.values_list("valor_original", flat=True)), esperado)
        ids = list(titulos.values_list("pk", flat=True))
        self.assertEqual(gerar_pedidos(self.processo, self.usuario), [pedido])
        self.assertEqual(list(titulos.values_list("pk", flat=True)), ids)

    def test_frete_e_desconto_por_fornecedor_sem_repetir_frete_em_itens(self):
        cotacao_a = self.cotacao(desconto="30.00")
        self.adjudicar(cotacao_a, "400.00", desconto="20.00")
        self.adjudicar(cotacao_a, "600.00")
        cotacao_b = self.cotacao(nome="Fornecedor sintético B", frete="20.00")
        self.adjudicar(cotacao_b, "200.00")

        self.assertEqual(total_aprovacao_processo(self.processo), Decimal("1320.00"))
        pedidos = {pedido.fornecedor_id: pedido for pedido in gerar_pedidos(self.processo, self.usuario)}
        for cotacao, frete, total in ((cotacao_a, "150.00", "1100.00"), (cotacao_b, "20.00", "220.00")):
            pedido = pedidos[cotacao.fornecedor_id]
            self.assertEqual(pedido.frete, Decimal(frete))
            self.assertEqual(pedido.valor_total, Decimal(total))
            self.assertEqual(pedido.titulos_financeiros.get().valor_original, Decimal(total))

    def test_frete_zero_na_negociacao_preserva_preco_com_frete_embutido(self):
        item = self.adjudicar(self.cotacao(), "1150.00")
        NegociacaoItem.objects.create(item_cotado=item, frete_negociado=Decimal("0.00"))
        pedido, = gerar_pedidos(self.processo, self.usuario)
        self.assertEqual(pedido.frete, Decimal("0.00"))
        self.assertEqual(pedido.valor_total, Decimal("1150.00"))
        self.assertEqual(pedido.titulos_financeiros.get().valor_original, Decimal("1150.00"))

    def test_nf_parcial_com_frete_explicitado_reconcilia_sem_inferir_frete_na_primeira_entrega(self):
        self.adjudicar(self.cotacao(frete="100.00"), "100.00", quantidade="10")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        primeira = self.receber(pedido, numero="NF-1", quantidade="8", valor_items="800", valor_nf="800")
        primeiro_titulo = autorizar_liberacao(primeira, usuario=self.usuario)
        self.assertEqual(primeiro_titulo.valor_original, Decimal("800.00"))
        segunda = self.receber(
            pedido, numero="NF-2", quantidade="2", valor_items="200", valor_nf="300", valor_frete_nota="100",
        )
        segundo_titulo = autorizar_liberacao(segunda, usuario=self.usuario)

        pedido.refresh_from_db()
        self.assertEqual(segunda.recebimento.valor_frete_nota, Decimal("100.00"))
        self.assertEqual(segundo_titulo.valor_original, Decimal("300.00"))
        self.assertEqual(avaliar_conferencia(segundo_titulo)["status"], TituloPagar.Conferencia.CONFERIDO)
        self.assertEqual(autorizar_liberacao(segunda, usuario=self.usuario), segundo_titulo)
        self.assertEqual(pedido.valor_total, Decimal("1100.00"))
        vigentes = pedido.titulos_financeiros.exclude(status=TituloPagar.Status.CANCELADO)
        self.assertEqual(sum(vigentes.values_list("valor_original", flat=True)), pedido.valor_total)

    def test_nf_divergente_com_diferenca_igual_ao_frete_permanece_sem_liberacao(self):
        self.adjudicar(self.cotacao(frete="100.00"), "100.00", quantidade="10")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        candidata = self.receber(pedido, numero="NF-3", quantidade="8", valor_items="800", valor_nf="900")
        self.assertEqual(candidata.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)
        with self.assertRaises(ValidationError):
            autorizar_liberacao(candidata, usuario=self.usuario)

    def test_frete_documentado_respeita_teto_acumulado_do_pedido(self):
        self.adjudicar(self.cotacao(frete="100.00"), "100.00", quantidade="10")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        primeira = self.receber(
            pedido, numero="NF-4", quantidade="2", valor_items="200", valor_nf="270", valor_frete_nota="70",
        )
        segunda = self.receber(
            pedido, numero="NF-5", quantidade="2", valor_items="200", valor_nf="250", valor_frete_nota="50",
        )
        autorizar_liberacao(primeira, usuario=self.usuario)
        with self.assertRaisesMessage(ValidationError, "frete contratado"):
            autorizar_liberacao(segunda, usuario=self.usuario)

    def test_rota_de_grande_fornecedor_registra_frete_da_nf(self):
        self.processo.fluxo_grande_fornecedor = True
        self.processo.save(update_fields=["fluxo_grande_fornecedor"])
        self.adjudicar(self.cotacao(frete="100.00"), "100.00", quantidade="10")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        item = pedido.itens.get()

        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("compras:gf_receber_pedido", args=[pedido.pk]), {
            f"item_{item.pk}": "2", f"valor_item_{item.pk}": "200.00",
            "numero_nota_fiscal": "NF-GF", "valor_total_nota": "300.00", "valor_frete_nota": "100.00",
            "arquivo_nota_fiscal": SimpleUploadedFile("nf-gf.xml", b"<NF-sintetica />", content_type="application/xml"),
        })

        self.assertEqual(resposta.status_code, 302)
        candidata = pedido.recebimentos.get().liberacao_financeira
        self.assertEqual(candidata.status, LiberacaoFinanceiraPedido.Status.PENDENTE)
        self.assertEqual(candidata.valor, Decimal("300.00"))

    def test_cancelamento_apos_entrega_parcial_preserva_frete_liberado_e_valor_original(self):
        self.adjudicar(self.cotacao(frete="100.00"), "100.00", quantidade="10")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        candidata = self.receber(
            pedido, numero="NF-CANCEL", quantidade="2", valor_items="200", valor_nf="300", valor_frete_nota="100",
        )
        titulo = autorizar_liberacao(candidata, usuario=self.usuario)
        TituloPagar.objects.filter(pk=titulo.pk).update(status=TituloPagar.Status.PAGO)
        pagamento = Pagamento.objects.create(titulo=titulo, valor=Decimal("300"), data_pagamento=pedido.data)

        cancelar_pedido(pedido=pedido, usuario=self.usuario, motivo="Saldo de materiais não entregue")

        pedido.refresh_from_db()
        titulo.refresh_from_db()
        pagamento.refresh_from_db()
        self.assertEqual(pedido.valor_total, Decimal("1100.00"))
        self.assertEqual(pedido.frete, Decimal("100.00"))
        self.assertEqual(titulo.status, TituloPagar.Status.PAGO)
        self.assertEqual(pagamento.valor, Decimal("300.00"))

    def test_diagnostico_encontra_divergencia_historica_e_preserva_titulos_e_pagamentos(self):
        self.adjudicar(self.cotacao(frete="100.00", desconto="50.00"), "1000.00")
        pedido, = gerar_pedidos(self.processo, self.usuario)
        titulo = pedido.titulos_financeiros.get()
        TituloPagar.objects.filter(pk=titulo.pk).update(valor_original=Decimal("950"), status=TituloPagar.Status.PAGO)
        Pagamento.objects.create(titulo=titulo, valor=Decimal("950"), data_pagamento=pedido.data)

        saida = StringIO()
        call_command("diagnosticar_frete_compras", pedido=pedido.numero, stdout=saida)
        registro, = list(csv.DictReader(StringIO(saida.getvalue()), delimiter=";"))
        self.assertEqual(registro["valor_material_bruto"], "1000.00")
        self.assertEqual(registro["descontos"], "50.00")
        self.assertEqual(registro["frete"], "100.00")
        self.assertEqual(registro["valor_contratado"], "1050.00")
        self.assertEqual(registro["total_financeiro"], "950.00")
        self.assertEqual(registro["diferenca_financeiro_contratado"], "-100.00")
        self.assertEqual(registro["total_pago"], "950.00")
        self.assertIn(titulo.numero, registro["titulos"])
        self.assertIn("frete", registro["conferencia"].lower())
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, TituloPagar.Status.PAGO)
        self.assertEqual(titulo.valor_original, Decimal("950"))
        self.assertEqual(Pagamento.objects.get(titulo=titulo).valor, Decimal("950"))
