from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import (NecessidadeCompra, ParcelaPrevistaPedido, PedidoCompra,
                            PedidoCompraItem, ProcessoCompra, RecebimentoPedido,
                            RecebimentoPedidoItem)
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from financeiro.services.liberacoes import (autorizar_liberacao,
    registrar_liberacao_condicional, registrar_recebimento_para_liberacao)
from financeiro.services.pagamentos import registrar_pagamento
from financeiro.services.previsoes import sincronizar_contas_pedido
from financeiro.services.titulos import cancelar_titulo
from financeiro.services.compromissos import pedidos_comprometidos, totais_pedidos
from obras.models import Obra


class LiberacoesPedidoTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="liberacao_admin", email="liberacao@example.test", password="teste"
        )
        obra = Obra.objects.create(nome="Obra liberação", codigo="OB-LIB-1")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor liberação")
        processo = ProcessoCompra.objects.create(numero="PC-LIB-1", obra=obra, titulo="Compra liberação")
        self.pedido = PedidoCompra.objects.create(
            numero="PED-LIB-1", processo=processo, obra=obra, fornecedor=fornecedor,
            valor_total=Decimal("1000.00"),
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Material", unidade="UN",
            quantidade_necessaria=Decimal("10"), quantidade_incluida=Decimal("10"),
        )
        self.item = PedidoCompraItem.objects.create(
            pedido=self.pedido, necessidade=necessidade, descricao="Material", unidade="UN",
            quantidade=Decimal("10"), valor_unitario=Decimal("100"), valor_total=Decimal("1000"),
        )

    def recebimento(self, numero, quantidade, valor, nota=None):
        rec = RecebimentoPedido.objects.create(
            pedido=self.pedido, numero_nota_fiscal=numero,
            valor_total_nota=Decimal(nota) if nota else None,
        )
        RecebimentoPedidoItem.objects.create(
            recebimento=rec, item_pedido=self.item, quantidade=Decimal(quantidade),
            valor_recebido=Decimal(valor) if valor is not None else None,
        )
        return rec

    def test_recebimento_parcial_gera_titulos_separados_sem_recriar_integral(self):
        placeholder = TituloPagar.objects.get(pedido=self.pedido)
        primeira = registrar_recebimento_para_liberacao(self.recebimento("NF-800", "8", "800", "800"))
        self.assertEqual(primeira, registrar_recebimento_para_liberacao(primeira.recebimento))
        titulo_800 = autorizar_liberacao(primeira, usuario=self.usuario)
        self.assertEqual(titulo_800.valor_original, Decimal("800.00"))
        self.assertEqual(autorizar_liberacao(primeira, usuario=self.usuario).pk, titulo_800.pk)
        linha = pedidos_comprometidos(obra_id=self.pedido.obra_id).get(pk=self.pedido.pk)
        self.assertEqual(linha.liberado_financeiramente, Decimal("800.00"))
        self.assertEqual(totais_pedidos(pedidos_comprometidos(obra_id=self.pedido.obra_id))["liberado_financeiramente"], Decimal("800.00"))
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.status, TituloPagar.Status.CANCELADO)
        sincronizar_contas_pedido(self.pedido)
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.status, TituloPagar.Status.CANCELADO)
        ParcelaPrevistaPedido.objects.create(
            pedido=self.pedido, ordem=1, valor=Decimal("200.00"),
            evento_gatilho=ParcelaPrevistaPedido.Gatilho.ENTREGA,
        )
        self.assertFalse(TituloPagar.objects.filter(
            pedido=self.pedido, referencia_externa__startswith="COMPRA_PARCELA:",
        ).exists())
        TituloPagar.objects.filter(pk=titulo_800.pk).update(status=TituloPagar.Status.APROVADO)
        registrar_pagamento(titulo=titulo_800, usuario=self.usuario)

        segunda = registrar_recebimento_para_liberacao(self.recebimento("NF-200", "2", "200", "200"))
        titulo_200 = autorizar_liberacao(segunda, usuario=self.usuario)
        self.assertEqual(titulo_200.valor_original, Decimal("200.00"))
        self.assertEqual(TituloPagar.objects.filter(pedido=self.pedido, status=TituloPagar.Status.PAGO).count(), 1)
        self.assertEqual(self.pedido.liberacoes_financeiras.filter(status="AUTORIZADA").count(), 2)
        self.assertEqual(sum(self.pedido.liberacoes_financeiras.filter(status="AUTORIZADA")
                             .values_list("valor", flat=True), Decimal("0")), Decimal("1000.00"))

    def test_nota_divergente_e_valor_ausente_nao_sao_autorizaveis(self):
        divergente = registrar_recebimento_para_liberacao(self.recebimento("NF-DIV", "8", "800", "900"))
        self.assertEqual(divergente.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)
        with self.assertRaises(ValidationError):
            autorizar_liberacao(divergente, usuario=self.usuario)
        sem_valor = registrar_recebimento_para_liberacao(self.recebimento("NF-NULL", "1", None))
        self.assertEqual(sem_valor.status, LiberacaoFinanceiraPedido.Status.DIVERGENTE)

    def test_titulo_legado_pago_nao_e_reescrito(self):
        antigo = TituloPagar.objects.get(pedido=self.pedido)
        antigo.status = TituloPagar.Status.PAGO
        antigo.save(update_fields=["status"])
        Pagamento.objects.create(titulo=antigo, data_pagamento=self.pedido.data, valor=Decimal("1000"))
        liberacao = registrar_recebimento_para_liberacao(self.recebimento("NF-LEGADO", "8", "800", "800"))
        with self.assertRaises(ValidationError):
            autorizar_liberacao(liberacao, usuario=self.usuario)
        antigo.refresh_from_db()
        self.assertEqual((antigo.status, antigo.valor_original), (TituloPagar.Status.PAGO, Decimal("1000.00")))

    def test_antecipacao_com_parcela_e_teto_contratual(self):
        parcela = ParcelaPrevistaPedido.objects.create(
            pedido=self.pedido, ordem=1, valor=Decimal("200"),
            evento_gatilho=ParcelaPrevistaPedido.Gatilho.ASSINATURA,
        )
        liberacao = registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            valor=Decimal("200"), referencia="ASSINATURA:1", usuario=self.usuario,
            parcela=parcela, justificativa="Antecipação prevista no contrato",
        )
        self.assertEqual(autorizar_liberacao(liberacao, usuario=self.usuario).valor_original, Decimal("200.00"))
        self.assertEqual(registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            valor=Decimal("200"), referencia="ASSINATURA:1", usuario=self.usuario,
            parcela=parcela, justificativa="Antecipação prevista no contrato",
        ).pk, liberacao.pk)
        excedente = registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.CONDICAO,
            valor=Decimal("801"), referencia="CONDICAO:2", usuario=self.usuario,
            justificativa="Condição contratual específica",
        )
        with self.assertRaises(ValidationError):
            autorizar_liberacao(excedente, usuario=self.usuario)

    def test_autorizacao_exige_permissao_e_post(self):
        comum = get_user_model().objects.create_user(username="liberacao_comum", password="teste")
        liberacao = registrar_recebimento_para_liberacao(self.recebimento("NF-PERM", "8", "800", "800"))
        with self.assertRaises(PermissionDenied):
            autorizar_liberacao(liberacao, usuario=comum)
        self.client.force_login(comum)
        url = reverse("financeiro:liberacao_autorizar", args=[liberacao.pk])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        liberacao.refresh_from_db()
        self.assertEqual(liberacao.status, LiberacaoFinanceiraPedido.Status.AUTORIZADA)

    def test_lista_exibe_origem_e_titulo_autorizado(self):
        liberacao = registrar_recebimento_para_liberacao(self.recebimento("NF-LISTA", "8", "800", "800"))
        titulo = autorizar_liberacao(liberacao, usuario=self.usuario)
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("financeiro:liberacoes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "NF-LISTA")
        self.assertContains(response, titulo.numero)

    def test_antecipacao_compensada_no_recebimento_sem_duplicar_pagavel(self):
        antecipacao = registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            valor=Decimal("200"), referencia="SINAL-200", usuario=self.usuario,
            justificativa="Sinal contratual",
        )
        titulo_antecipacao = autorizar_liberacao(antecipacao, usuario=self.usuario)
        recebimento = registrar_recebimento_para_liberacao(self.recebimento("NF-REC-800", "8", "800", "800"))
        titulo_recebimento = autorizar_liberacao(recebimento, usuario=self.usuario)
        recebimento.refresh_from_db()
        self.assertEqual(recebimento.valor_origem, Decimal("800.00"))
        self.assertEqual(recebimento.valor_compensado, Decimal("200.00"))
        self.assertEqual(titulo_recebimento.valor_original, Decimal("600.00"))
        self.assertEqual(titulo_antecipacao.valor_original + titulo_recebimento.valor_original, Decimal("800.00"))
        with self.assertRaises(ValueError):
            cancelar_titulo(titulo_antecipacao, usuario=self.usuario, motivo="Tentativa após compensação")

    def test_cancelamento_de_titulo_liberado_concilia_saldo_sem_recriar_integral(self):
        placeholder = TituloPagar.objects.get(pedido=self.pedido)
        cancelar_titulo(placeholder, usuario=self.usuario, motivo="Previsão substituída")
        liberacao = registrar_recebimento_para_liberacao(self.recebimento("NF-CAN-800", "8", "800", "800"))
        titulo = autorizar_liberacao(liberacao, usuario=self.usuario)
        cancelar_titulo(titulo, usuario=self.usuario, motivo="Liberação indevida")
        liberacao.refresh_from_db()
        self.assertEqual(liberacao.status, LiberacaoFinanceiraPedido.Status.CANCELADA)
        self.assertEqual(liberacao.motivo_cancelamento, "Liberação indevida")
        self.assertEqual(totais_pedidos(pedidos_comprometidos(obra_id=self.pedido.obra_id))["liberado_financeiramente"], Decimal("0.00"))
        sincronizar_contas_pedido(self.pedido)
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.status, TituloPagar.Status.CANCELADO)

    def test_recebimento_totalmente_coberto_por_antecipacao_nao_cria_titulo(self):
        antecipacao = registrar_liberacao_condicional(
            self.pedido, tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
            valor=Decimal("200"), referencia="SINAL-TOTAL", usuario=self.usuario,
            justificativa="Sinal contratual",
        )
        autorizar_liberacao(antecipacao, usuario=self.usuario)
        recebimento = registrar_recebimento_para_liberacao(self.recebimento("NF-COMP-200", "2", "200", "200"))
        self.assertIsNone(autorizar_liberacao(recebimento, usuario=self.usuario))
        self.assertIsNone(autorizar_liberacao(recebimento, usuario=self.usuario))
        recebimento.refresh_from_db()
        self.assertEqual(recebimento.status, LiberacaoFinanceiraPedido.Status.COMPENSADA)
        self.assertEqual(recebimento.valor_compensado, Decimal("200.00"))
        self.assertFalse(TituloPagar.objects.filter(pedido=self.pedido, recebimento=recebimento.recebimento).exists())
        sincronizar_contas_pedido(self.pedido)
        self.assertEqual(TituloPagar.objects.filter(pedido=self.pedido, status=TituloPagar.Status.PREVISTA).count(), 1)
