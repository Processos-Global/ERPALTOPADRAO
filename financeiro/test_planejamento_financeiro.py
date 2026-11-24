from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import ContratoCompra, PedidoCompra, ProcessoCompra
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, PlanoFinanceiro, PrevisaoFinanceira, ProgramacaoPagamento, TituloPagar
from financeiro.services.fluxo_caixa import serie_desembolsos
from financeiro.services.planejamento_financeiro import recorte_planejamento
from obras.models import Obra


class PlanejamentoFinanceiroTests(TestCase):
    novembro = date(2026, 11, 1)
    vencimento = date(2026, 11, 10)
    dezembro = date(2026, 12, 5)

    @classmethod
    def setUpTestData(cls):
        # Todas as entidades e quantias são sintéticas.
        cls.usuario = get_user_model().objects.create_superuser("financeiro-planejamento")
        cls.obra = Obra.objects.create(codigo="FIN-B10", nome="Obra do planejamento")
        cls.fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético")
        cls.plano = PlanoFinanceiro.objects.create(codigo="B10", nome="Apropriação do planejamento")

    def previsao(self, descricao, valor, **campos):
        padrao = {"obra": self.obra, "fornecedor": self.fornecedor, "plano_financeiro": self.plano,
                  "data_prevista": self.vencimento}
        return PrevisaoFinanceira.objects.create(descricao=descricao, valor_previsto=Decimal(valor), **(padrao | campos))

    def titulo(self, numero, valor, **campos):
        padrao = {"obra": self.obra, "fornecedor": self.fornecedor, "plano_financeiro": self.plano,
                  "vencimento": self.vencimento}
        return TituloPagar.objects.create(numero=numero, descricao=numero, valor_original=Decimal(valor), **(padrao | campos))

    def test_previsao_formalizada_fica_fora_do_fluxo_mesmo_quando_titulo_tem_outra_data(self):
        formalizada = self.previsao("Formalizada", "102.49")
        self.titulo("TIT-FORMAL", "104.75", previsao_origem=formalizada, vencimento=self.dezembro)
        cancelada = self.previsao("Título cancelado", "9.05")
        self.titulo("TIT-CANCEL", "9.05", previsao_origem=cancelada, status=TituloPagar.Status.CANCELADO)
        self.previsao("Previsão de compra", "600.00", origem=PrevisaoFinanceira.Origem.COMPRA)
        self.previsao("Despesa recorrente", "12.07", origem=PrevisaoFinanceira.Origem.RECORRENTE)

        serie = serie_desembolsos(inicio=self.vencimento, dias=0)
        self.assertEqual(serie["total"], Decimal("21.12"))
        serie_recorrente = serie_desembolsos(inicio=self.vencimento, dias=0, origem=PrevisaoFinanceira.Origem.RECORRENTE)
        self.assertEqual(serie_recorrente["total"], Decimal("12.07"))
        self.assertTrue(PrevisaoFinanceira.objects.get(pk=formalizada.pk).ativa)

    def test_desembolso_usa_programacao_ativa_do_ciclo_vigente_e_exclui_pago(self):
        for numero, valor, ciclo, ativa in (("VIGENTE", "80.12", 2, True), ("ANTIGO", "9.90", 1, True),
                                            ("INATIVO", "4.03", 2, False)):
            titulo = self.titulo(numero, valor, status=TituloPagar.Status.APROVADO, ciclo_aprovacao=2)
            ProgramacaoPagamento.objects.create(titulo=titulo, data_programada=self.dezembro, ciclo_aprovacao=ciclo, ativa=ativa)
        pago = self.titulo("QUITADO", "60.00", status=TituloPagar.Status.PAGO)
        Pagamento.objects.create(titulo=pago, data_pagamento=self.vencimento, valor=Decimal("60.00"))

        self.assertEqual(serie_desembolsos(inicio=self.vencimento, dias=0)["total"], Decimal("13.93"))
        self.assertEqual(serie_desembolsos(inicio=self.dezembro, dias=0)["total"], Decimal("80.12"))

    def test_pagina_reconcilia_recorte_e_saldo_programado_sem_soma_duplicada(self):
        titulo = self.titulo("PROGRAMADO", "10.47", status=TituloPagar.Status.APROVADO,
                             ciclo_aprovacao=1, vencimento=self.dezembro)
        ProgramacaoPagamento.objects.create(titulo=titulo, data_programada=self.vencimento, ciclo_aprovacao=1)
        for i in range(44):
            self.previsao(f"Previsão {i:02d}", "1.01")
        self.previsao("Outro mês", "800.00", data_prevista=self.dezembro)
        self.previsao("Sem fornecedor", "500.00", fornecedor=None)
        pago = self.titulo("PAGO-NOV", "5.31", status=TituloPagar.Status.PAGO, vencimento=self.dezembro)
        Pagamento.objects.create(titulo=pago, data_pagamento=self.vencimento, valor=Decimal("5.31"))
        estornado = self.titulo("ESTORNADO-NOV", "8.21", status=TituloPagar.Status.APROVADO, vencimento=self.dezembro)
        Pagamento.objects.create(titulo=estornado, data_pagamento=self.vencimento, valor=Decimal("8.21"), status=Pagamento.Status.ESTORNADO)

        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("financeiro:previsoes"), {
            "mes": "2026-11", "obra": self.obra.pk, "fornecedor": self.fornecedor.pk,
            "apropriacao": self.plano.pk, "origem": TituloPagar.Origem.MANUAL,
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["totais"]["PREVISAO"], Decimal("44.44"))
        self.assertEqual(resposta.context["totais"]["PAGO"], Decimal("5.31"))
        self.assertEqual(resposta.context["totais"]["SALDO"], Decimal("10.47"))
        self.assertEqual(resposta.context["totais"]["PROGRAMADO"], Decimal("10.47"))
        self.assertEqual(resposta.context["page_obj"].paginator.count, 46)
        self.assertEqual(len(resposta.context["page_obj"].object_list), 40)

    def test_compromissos_liberações_e_previsao_vinculada_ficam_em_camadas_separadas(self):
        processo = ProcessoCompra.objects.create(
            numero="B10-PROCESSO", obra=self.obra, apropriacao=self.plano,
        )
        # Simula pedido legado preservado, já com uma liberação individual.
        (pedido,) = PedidoCompra.objects.bulk_create([PedidoCompra(
            numero="B10-PEDIDO", processo=processo, obra=self.obra, fornecedor=self.fornecedor,
            subtotal=Decimal("100.05"), frete=Decimal("7.02"), valor_total=Decimal("107.07"),
        )])
        pedido = PedidoCompra.objects.get(
            numero="B10-PEDIDO",
            processo=processo,
        )
        PedidoCompra.objects.filter(pk=pedido.pk).update(data=self.vencimento)
        pedido.refresh_from_db()
        assinado_em = timezone.make_aware(datetime(2026, 11, 14, 11, 30))
        ContratoCompra.objects.create(
            numero="B10-CONTRATO", processo=processo, obra=self.obra, fornecedor=self.fornecedor,
            valor_total=Decimal("107.07"), data_contrato=self.novembro, assinado_em=assinado_em,
            objeto_contrato="Contrato do mesmo processo", status=ContratoCompra.Status.ASSINADO,
            criado_por=self.usuario,
        )
        previsao = self.previsao("Previsão da liberação", "30.12")
        titulo = self.titulo("B10-TITULO", "30.12", pedido=pedido, origem=TituloPagar.Origem.COMPRA, previsao_origem=previsao)
        LiberacaoFinanceiraPedido.objects.create(
            pedido=pedido, titulo=titulo, referencia="B10-LIB", valor=Decimal("30.12"),
            tipo=LiberacaoFinanceiraPedido.Tipo.PARCELA, status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
            autorizado_em=assinado_em,
        )
        LiberacaoFinanceiraPedido.objects.create(
            pedido=pedido, referencia="B10-COMPENSADA", valor=Decimal("0"), valor_origem=Decimal("30.12"),
            tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO, status=LiberacaoFinanceiraPedido.Status.COMPENSADA,
            autorizado_em=assinado_em,
        )

        filtros = {"mes": "2026-11", "apropriacao": str(self.plano.pk)}
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("financeiro:previsoes"), filtros)
        self.assertEqual(resposta.context["totais"], {
            "PREVISAO": Decimal("0.00"), "PEDIDO": Decimal("107.07"), "CONTRATO": Decimal("107.07"),
            "LIBERACAO": Decimal("30.12"), "PAGO": Decimal("0.00"), "SALDO": Decimal("30.12"),
            "PROGRAMADO": Decimal("0.00"),
        })
        exportacao = recorte_planejamento(filtros)["linhas"].iterator()
        self.assertEqual({linha["tipo"]: linha["valor"] for linha in exportacao}, {
            "PEDIDO": Decimal("107.07"), "CONTRATO": Decimal("107.07"),
            "LIBERACAO": Decimal("30.12"), "SALDO": Decimal("30.12"),
        })
        self.assertContains(resposta, "Previsão da liberação")

    def test_sem_data_e_certeza_nao_atribuem_dados_a_registro_legado(self):
        self.previsao("Sem data", "1.46", certeza=PrevisaoFinanceira.Certeza.CONTRATADO, data_prevista=None)
        self.previsao("Sem data de outro nível", "2.00", data_prevista=None)
        self.titulo("CONTA-SEM-DATA", "3.03", vencimento=None)
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("financeiro:previsoes"), {
            "sem_data": "1", "certeza": PrevisaoFinanceira.Certeza.CONTRATADO,
        })
        self.assertEqual(resposta.context["totais"]["PREVISAO"], Decimal("1.46"))
        self.assertEqual(resposta.context["totais"]["SALDO"], Decimal("0.00"))
        self.assertEqual(resposta.context["page_obj"].paginator.count, 1)
        self.assertIsNone(resposta.context["page_obj"].object_list[0]["data"])
