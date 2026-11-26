from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import HistoricoProcessoCompra, NecessidadeCompra, ParcelaPrevistaPedido, PedidoCompra, PedidoCompraItem, ProcessoCompra, RecebimentoPedido, RecebimentoPedidoItem
from compras.services.pedidos import cancelar_pedido
from financeiro.models import Pagamento, TituloPagar
from financeiro.services.compromissos import pedidos_comprometidos, totais_pedidos
from financeiro.services.fluxo_caixa import serie_desembolsos
from financeiro.services.planejamento_financeiro import recorte_planejamento, resumo_planejamento
from obras.models import Obra


class CompromissosTest(TestCase):
    def test_etapas_do_compromisso_e_projecao_datada_sem_dupla_contagem(self):
        obra = Obra.objects.create(nome="Obra sintética de projeção", codigo="OB-PROJ")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético de projeção")
        processo = ProcessoCompra.objects.create(numero="PC-PROJ", obra=obra, titulo="Projeção sem duplicidade")
        pedido = PedidoCompra.objects.create(
            numero="PED-PROJ", processo=processo, obra=obra, fornecedor=fornecedor,
            valor_total=Decimal("100000.00"),
        )
        vencimento = timezone.localdate() + timedelta(days=10)
        ParcelaPrevistaPedido.objects.create(pedido=pedido, valor=Decimal("100000.00"), data_prevista=vencimento)
        self.assertFalse(TituloPagar.objects.filter(pedido=pedido).exists())
        projeção = serie_desembolsos(inicio=vencimento, dias=0, obra_id=obra.pk)
        self.assertEqual(projeção["total"], Decimal("100000.00"))

        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material sintético", unidade="UN", quantidade_necessaria=100,
            quantidade_incluida=100,
        )
        item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Material sintético", unidade="UN",
            quantidade=100, valor_unitario=1000, valor_total=100000,
        )
        for indice, (status, valor) in enumerate([
            (TituloPagar.Status.AGUARDANDO_APROVACAO, Decimal("10000.00")),
            (TituloPagar.Status.APROVADO, Decimal("20000.00")),
            (TituloPagar.Status.PAGO, Decimal("30000.00")),
        ], start=1):
            recebimento = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal=f"NF-PROJ-{indice}")
            RecebimentoPedidoItem.objects.create(
                recebimento=recebimento, item_pedido=item, quantidade=valor / 1000, valor_recebido=valor,
            )
            titulo = TituloPagar.objects.create(
                numero=f"TIT-PROJ-{indice}", descricao="Parcela sintética", pedido=pedido, recebimento=recebimento,
                obra=obra, fornecedor=fornecedor, origem=TituloPagar.Origem.COMPRA, status=status,
                vencimento=vencimento, valor_original=valor,
            )
            if status == TituloPagar.Status.PAGO:
                Pagamento.objects.create(titulo=titulo, data_pagamento=timezone.localdate(), valor=valor)
        linha = pedidos_comprometidos(obra_id=obra.pk).get()
        self.assertEqual(linha.saldo_receber, Decimal("40000.00"))
        self.assertEqual(linha.recebido_aguardando_aprovacao, Decimal("10000.00"))
        self.assertEqual(linha.aprovado_a_pagar, Decimal("20000.00"))
        self.assertEqual(linha.pago_efetivado, Decimal("30000.00"))
        self.assertEqual(linha.saldo_financeiro, Decimal("70000.00"))
        self.assertEqual(serie_desembolsos(inicio=vencimento, dias=0, obra_id=obra.pk)["total"], Decimal("70000.00"))
        planejamento = resumo_planejamento(recorte_planejamento({"mes": vencimento.strftime("%Y-%m"), "obra": obra.pk}))
        self.assertEqual(planejamento["totais"]["COMPROMISSO_FUTURO"], Decimal("40000.00"))
        self.assertEqual(planejamento["totais"]["SALDO"], Decimal("30000.00"))

    def test_cancelamento_integral_audita_saldo_sem_ocultar_pago(self):
        """Fixture sintética: 1000 contratado, 800 recebido/pago, 200 cancelado."""
        usuario = get_user_model().objects.create_superuser(
            username="comp_cancel_admin", email="comp_cancel@example.test", password="teste"
        )
        obra = Obra.objects.create(nome="Obra cancelamento", codigo="OB-CAN-COMP")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor cancelamento")
        processo = ProcessoCompra.objects.create(numero="PC-CAN-COMP", obra=obra, titulo="Cancelamento")
        pedido = PedidoCompra.objects.create(
            numero="PED-CAN-COMP", processo=processo, obra=obra,
            fornecedor=fornecedor, valor_total=Decimal("1000.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Material", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )
        recebimento = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal="NF-CAN-COMP")
        RecebimentoPedidoItem.objects.create(
            recebimento=recebimento, item_pedido=item,
            quantidade=Decimal("8"), valor_recebido=Decimal("800.00"),
        )
        # O título provisório não representa o pagamento da entrega parcial.
        titulo = TituloPagar.objects.create(
            numero="PREV-CAN-LEGADO", pedido=pedido, obra=obra, fornecedor=fornecedor,
            referencia_externa=f"COMPRA_PEDIDO:{pedido.pk}", origem=TituloPagar.Origem.COMPRA,
            descricao="Previsão legada", valor_original=Decimal("1000.00"), status=TituloPagar.Status.CANCELADO,
        )
        titulo_800 = TituloPagar.objects.create(
            numero="T-CAN-COMP", pedido=pedido, obra=obra, fornecedor=fornecedor,
            origem=TituloPagar.Origem.COMPRA, descricao="Entrega parcial",
            valor_original=Decimal("800.00"), status=TituloPagar.Status.PAGO,
        )
        Pagamento.objects.create(
            titulo=titulo_800, data_pagamento=pedido.data, valor=Decimal("800.00")
        )
        cancelar_pedido(pedido=pedido, usuario=usuario, motivo="Fornecedor não entregará duas unidades")

        linha = pedidos_comprometidos(obra_id=obra.pk, status=PedidoCompra.Status.CANCELADO).get(pk=pedido.pk)
        self.assertEqual(linha.valor_total, Decimal("1000.00"))
        self.assertEqual(linha.recebido_identificado, Decimal("800.00"))
        self.assertEqual(linha.pago_efetivado, Decimal("800.00"))
        self.assertEqual(linha.saldo_cancelado, Decimal("200.00"))
        self.assertEqual(linha.saldo_financeiro, Decimal("0.00"))
        totais = totais_pedidos(pedidos_comprometidos(obra_id=obra.pk))
        self.assertEqual(totais["saldo_cancelado"], Decimal("200.00"))
        self.assertEqual(totais["saldo_cancelamento_pendente"], Decimal("0.00"))
        self.assertEqual(totais["pago_efetivado"], Decimal("800.00"))
        titulo_800.refresh_from_db()
        self.assertEqual((titulo_800.status, titulo_800.valor_original),
                         (TituloPagar.Status.PAGO, Decimal("800.00")))
        pedido.refresh_from_db()
        self.assertEqual(pedido.motivo_cancelamento, "Fornecedor não entregará duas unidades")
        self.assertEqual(pedido.cancelado_por, usuario)
        self.assertTrue(HistoricoProcessoCompra.objects.filter(
            processo=processo, tipo="PEDIDO_CANCELADO", usuario=usuario,
            dados__pedido_id=pedido.pk,
        ).exists())

        # Um título provisório ainda ativo impede mostrar o saldo como extinto.
        titulo.status = TituloPagar.Status.PREVISTA
        titulo.save(update_fields=["status"])
        linha = pedidos_comprometidos(obra_id=obra.pk).get(pk=pedido.pk)
        self.assertEqual(linha.saldo_cancelado, Decimal("0.00"))
        self.assertEqual(linha.saldo_cancelamento_pendente, Decimal("200.00"))
        titulo.status = TituloPagar.Status.CANCELADO
        titulo.save(update_fields=["status"])

        # Valores ausentes em qualquer recebimento exigem conferência da origem.
        outro = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal="NF-SEM-VALOR")
        RecebimentoPedidoItem.objects.create(
            recebimento=outro, item_pedido=item,
            quantidade=Decimal("1"), valor_recebido=None,
        )
        linha = pedidos_comprometidos(obra_id=obra.pk).get(pk=pedido.pk)
        self.assertEqual(linha.saldo_cancelado, Decimal("0.00"))
        self.assertEqual(linha.saldo_cancelamento_pendente, Decimal("200.00"))

        comum = get_user_model().objects.create_user(username="comp_cancel_comum", password="teste")
        self.client.force_login(comum)
        self.assertEqual(self.client.get(reverse("financeiro:compromissos")).status_code, 403)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("financeiro:compromissos"), {"status": "CANCELADO"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "PED-CAN-COMP")
        self.assertContains(resposta, "Fornecedor não entregará duas unidades")

    def test_recebimentos_e_pagamento_nao_duplicam_pedido(self):
        """Fixture sintética: contratado 1000, recebido 800, pago 800."""
        obra = Obra.objects.create(nome="Obra compromisso", codigo="OB-COMP-01")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor compromisso")
        processo = ProcessoCompra.objects.create(numero="PC-COMP-01", obra=obra, titulo="Teste")
        pedido = PedidoCompra.objects.create(
            numero="PED-COMP-01", processo=processo, obra=obra, fornecedor=fornecedor,
            valor_total=Decimal("1000.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material de teste", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        item = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Material de teste", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )
        for indice in range(2):
            recebimento = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal=f"NF-COMP-{indice}")
            RecebimentoPedidoItem.objects.create(
                recebimento=recebimento, item_pedido=item,
                quantidade=Decimal("4"), valor_recebido=Decimal("400.00"),
            )
        titulo = TituloPagar.objects.create(
            numero="COMP-PAGO-LEGADO", pedido=pedido, obra=obra, fornecedor=fornecedor,
            origem=TituloPagar.Origem.COMPRA, descricao="Obrigação histórica",
            valor_original=Decimal("1000.00"), status=TituloPagar.Status.PAGO,
        )
        Pagamento.objects.create(titulo=titulo, data_pagamento=pedido.data, valor=Decimal("800.00"))

        linha = pedidos_comprometidos(obra_id=obra.pk).get(pk=pedido.pk)
        self.assertEqual(linha.valor_total, Decimal("1000.00"))
        self.assertEqual(linha.recebido_identificado, Decimal("800.00"))
        self.assertEqual(linha.pago_efetivado, Decimal("800.00"))
        self.assertEqual(linha.liberado_financeiramente, Decimal("0.00"))
        self.assertEqual(linha.saldo_financeiro, Decimal("200.00"))
        self.assertEqual(totais_pedidos(pedidos_comprometidos(obra_id=obra.pk))["contratado"], Decimal("1000.00"))

        outro_recebimento = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal="NF-COMP-SEM-VALOR")
        RecebimentoPedidoItem.objects.create(
            recebimento=outro_recebimento, item_pedido=item, quantidade=Decimal("1"), valor_recebido=None,
        )
        linha = pedidos_comprometidos(obra_id=obra.pk).get(pk=pedido.pk)
        self.assertEqual(linha.recebido_identificado, Decimal("800.00"))
        self.assertEqual(linha.itens_recebidos_sem_valor, 1)

        Pagamento.objects.filter(titulo=titulo).update(status=Pagamento.Status.ESTORNADO)
        linha = pedidos_comprometidos(obra_id=obra.pk).get(pk=pedido.pk)
        self.assertEqual(linha.pago_efetivado, Decimal("0.00"))
        self.assertEqual(linha.saldo_financeiro, Decimal("1000.00"))
