from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import StringIO
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.models import (
    AdjudicacaoCompra, AprovacaoCompra, CompatibilizacaoItem, CotacaoFornecedor, CotacaoFornecedorItem,
    HistoricoProcessoCompra, NecessidadeCompra, PedidoCompra, PedidoCompraItem,
    ProcessoCompra, RecebimentoPedido, RecebimentoPedidoItem, ReservaEstoqueCompra,
)
from compras.services.cobertura_estoque import obter_cobertura, resumir_cobertura_necessidade
from compras.services.etapas import (
    decidir_aprovacao, enviar_cotacao_para_aprovacao, enviar_cotacao_para_compatibilizacao,
    enviar_cotacao_para_negociacao,
)
from compras.services.pedidos import cancelar_pedido, gerar_pedidos, registrar_recebimento
from compras.services.processos import editar_necessidade, excluir_necessidade, incluir_necessidade
from obras.models import MovimentoEstoque, Obra
from obras.services.estoque import chave_estoque
from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra, ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)


class FixtureCoberturaEstoqueCompra:
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
        self.entradas = 0

    def registrar_entrada(self, obra, quantidade, *, especificacao="Granito A"):
        self.entradas += 1
        processo = ProcessoCompra.objects.create(
            numero=f"PC-ORIG-{self.entradas}", obra=obra, titulo="Origem"
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


class CoberturaEstoqueCompraTest(FixtureCoberturaEstoqueCompra, TestCase):
    def test_compra_integral_mesmo_quando_estoque_cobre_a_demanda(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("5"),
            usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("5"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("5"))
        self.assertFalse(ReservaEstoqueCompra.objects.filter(necessidade=necessidade).exists())

    def test_resumo_cobertura_distingue_pedido_proprio_parcial_e_controle_de_acesso(self):
        self.registrar_entrada(self.obra, Decimal("55"))
        outra_necessidade = NecessidadeCompra.objects.create(
            processo=self.processo, material=self.material, descricao=self.material.nome,
            especificacao=self.material.especificacao, unidade="UN",
            quantidade_necessaria=100, quantidade_incluida=100,
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=self.processo, material=self.material, descricao=self.material.nome,
            especificacao=self.material.especificacao, unidade="UN",
            quantidade_necessaria=100, quantidade_incluida=100,
        )
        ReservaEstoqueCompra.objects.create(
            necessidade=outra_necessidade, obra=self.obra, material=self.material,
            especificacao=self.material.especificacao, unidade="UN",
            quantidade_original=20, quantidade_disponivel=20,
        )
        for i, (vinculo, qtd, recebido, status) in enumerate([
            (necessidade, 35, 5, PedidoCompra.Status.ENTREGA_PARCIAL),
            (necessidade, 70, 0, PedidoCompra.Status.CANCELADO),
            (outra_necessidade, 60, 0, PedidoCompra.Status.CONFIRMADO),
        ]):
            pedido = PedidoCompra.objects.create(
                obra=self.obra, processo=self.processo, fornecedor=self.fornecedor,
                numero=f"PC-COB-SALDO-{i}", status=status,
            )
            item = PedidoCompraItem.objects.create(
                pedido=pedido, necessidade=vinculo, descricao=self.material.nome,
                especificacao=self.material.especificacao, unidade="UN",
                quantidade=qtd, quantidade_recebida=recebido, valor_unitario=1, valor_total=qtd,
            )
            if recebido:
                entrada = RecebimentoPedido.objects.create(pedido=pedido)
                RecebimentoPedidoItem.objects.create(
                    recebimento=entrada, item_pedido=item, quantidade=recebido, valor_recebido=recebido,
                )
        url = reverse("compras:cobertura_necessidade", args=[self.processo.pk, necessidade.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.usuario)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        cobertura = resposta.context["cobertura"]
        self.assertEqual(cobertura["saldo_fisico"], Decimal("60"))
        self.assertEqual(cobertura["reservado"], Decimal("20"))
        self.assertEqual(cobertura["disponivel"], Decimal("40"))
        self.assertEqual(cobertura["contratado"], Decimal("35"))
        self.assertEqual(cobertura["recebido"], Decimal("5"))
        self.assertEqual(cobertura["pendente_proprio"], Decimal("30"))
        self.assertEqual(cobertura["descoberta"], Decimal("30"))
        origem = ProcessoCompra.objects.get(numero="PC-ORIG-1")
        self.assertEqual(
            self.client.get(reverse("compras:cobertura_necessidade", args=[origem.pk, necessidade.pk])).status_code,
            404,
        )
        self.client.force_login(get_user_model().objects.create_user(username="sem-permissao-compras"))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_estoques_parcial_e_de_outra_obra_nao_reduzem_a_compra(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        self.registrar_entrada(self.outra, Decimal("20"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("10"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("10"))

    def test_define_quantidade_comercial_sem_permissao_de_excecao(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        usuario = get_user_model().objects.create_user(username="comprador-sem-excecao")
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("5"),
            usuario=usuario, quantidade_compra=Decimal("3"),
        )
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("5"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("3"))
        self.assertFalse(self.processo.historico.filter(tipo="EXCECAO_ESTOQUE").exists())

    def test_valida_limite_e_precisao_da_quantidade_comercial(self):
        for quantidade_compra in (0, -1, Decimal("0.00001"), 11, Decimal("NaN")):
            with self.subTest(quantidade_compra=quantidade_compra), self.assertRaises(ValidationError):
                incluir_necessidade(
                    processo=self.processo, material=self.material, quantidade=10,
                    usuario=self.usuario, quantidade_compra=quantidade_compra,
                )
        self.assertFalse(self.processo.necessidades.exists())

    def test_especificacao_divergente_nao_bloqueia_automaticamente(self):
        self.registrar_entrada(self.obra, Decimal("10"), especificacao="Granito B")
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("5"),
            usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_incluida, Decimal("5"))

    def test_saida_fisica_independe_de_reserva_legada_e_valida_saldo(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        primeira = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        reserva, _ = ReservaEstoqueCompra.objects.get_or_create(
            necessidade=primeira, defaults={
                "obra": self.obra, "material": self.material, "unidade": "UN",
                "especificacao": self.material.especificacao,
                "quantidade_original": 4, "quantidade_disponivel": 4,
            },
        )

        self.client.force_login(self.usuario)
        url = reverse("obras:saida_estoque", args=[self.obra.pk])
        item = chave_estoque(self.material.pk, self.material.nome, "UN")
        resposta = self.client.post(url, {"item": item, "quantidade": "5"})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(MovimentoEstoque.objects.filter(obra_origem=self.obra).exists())

        resposta = self.client.post(url, {"item": item, "quantidade": "4"})
        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentoEstoque.objects.get(obra_origem=self.obra)
        self.assertIsNone(movimento.reserva_id)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.ATIVA)
        self.assertEqual(reserva.quantidade_disponivel, Decimal("4"))

    def test_estoque_novo_nao_impede_emissao_da_quantidade_comercial(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=Decimal("10"),
            usuario=self.usuario,
        )
        self.registrar_entrada(self.obra, Decimal("4"))
        pedido = self.emitir_pedido(necessidade)
        self.assertEqual(pedido.itens.get().quantidade, Decimal("10"))

    def test_compra_legada_com_novo_estoque_avanca_da_negociacao_a_aprovacao(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=10, usuario=self.usuario,
        )
        HistoricoProcessoCompra.objects.create(
            processo=self.processo, usuario=self.usuario, tipo="COBERTURA_ESTOQUE_AVALIADA",
            descricao="Cobertura antes da entrada física.",
            dados={"necessidade_id": necessidade.pk},
        )
        self.registrar_entrada(self.obra, Decimal("15"))
        cotacao = CotacaoFornecedor.objects.create(
            processo=self.processo, fornecedor=self.fornecedor,
        )
        item = CotacaoFornecedorItem.objects.create(
            cotacao=cotacao, necessidade=necessidade, quantidade=10, valor_unitario_cotado=10,
        )
        enviar_cotacao_para_compatibilizacao(cotacao, self.usuario)
        CompatibilizacaoItem.objects.create(
            item_cotado=item, resultado=CompatibilizacaoItem.Resultado.APROVADO, responsavel=self.usuario,
        )
        cotacao = enviar_cotacao_para_negociacao(cotacao, self.usuario)
        enviar_cotacao_para_aprovacao(cotacao, self.usuario)
        item.refresh_from_db()
        aprovacao = decidir_aprovacao(
            self.processo, self.usuario, AprovacaoCompra.Decisao.APROVADO, selecoes=[{"item_cotado": item}],
        )
        self.assertEqual(aprovacao.decisao, AprovacaoCompra.Decisao.APROVADO)
        self.assertEqual(self.processo.pedidos.get().itens.get().quantidade, Decimal("10"))
        self.assertFalse(ReservaEstoqueCompra.objects.filter(necessidade=necessidade).exists())

    def test_transferencia_fisica_independe_de_reserva_legada(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=10, usuario=self.usuario,
        )
        reserva = ReservaEstoqueCompra.objects.create(
            necessidade=necessidade, obra=self.obra, material=self.material, unidade="UN",
            especificacao=self.material.especificacao, quantidade_original=4, quantidade_disponivel=4,
        )
        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("obras:transferencia_estoque", args=[self.obra.pk]), {
            "item": chave_estoque(self.material.pk, self.material.nome, "UN"),
            "quantidade": "4", "obra_destino": self.outra.pk,
        })
        self.assertEqual(resposta.status_code, 302)
        movimento = MovimentoEstoque.objects.get(obra_origem=self.obra)
        self.assertEqual(movimento.obra_destino_id, self.outra.pk)
        self.assertEqual(movimento.quantidade, Decimal("4"))
        self.assertIsNone(movimento.reserva_id)
        reserva.refresh_from_db()
        self.assertEqual(reserva.quantidade_disponivel, Decimal("4"))

    def emitir_pedido(self, necessidade):
        cotacao = CotacaoFornecedor.objects.create(processo=self.processo, fornecedor=self.fornecedor)
        item = CotacaoFornecedorItem.objects.create(
            cotacao=cotacao, necessidade=necessidade, quantidade=necessidade.quantidade_incluida,
            valor_unitario_cotado=10,
        )
        AdjudicacaoCompra.objects.create(
            processo=self.processo, necessidade=necessidade, cotacao=cotacao, item_cotado=item,
            quantidade=necessidade.quantidade_incluida, valor_unitario_final=10,
        )
        self.processo.status = ProcessoCompra.Status.APROVADO
        self.processo.save(update_fields=["status"])
        return gerar_pedidos(self.processo, self.usuario)[0]

    def receber(self, pedido, quantidade, nota):
        item = pedido.itens.get()
        return registrar_recebimento(
            pedido=pedido, quantidades={item.pk: Decimal(quantidade)},
            valores_itens={item.pk: Decimal(quantidade) * 10},
            usuario=self.usuario, numero_nota_fiscal=nota, valor_total_nota=Decimal(quantidade) * 10,
            arquivo_nota_fiscal=None, dados_fiscais_opcionais=True,
        )

    def consumir(self, quantidade, reserva=None):
        self.client.force_login(self.usuario)
        dados = {"item": chave_estoque(self.material.pk, self.material.nome, "UN"), "quantidade": str(quantidade)}
        if reserva:
            dados["reserva_id"] = reserva.pk
        resposta = self.client.post(reverse("obras:saida_estoque", args=[self.obra.pk]), dados)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(MovimentoEstoque.objects.filter(obra_origem=self.obra, quantidade=quantidade).exists())

    def test_recebimento_parcial_e_consumo_integral_preservam_cobertura_da_necessidade(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=100, usuario=self.usuario,
        )
        pedido = self.emitir_pedido(necessidade)
        self.receber(pedido, 40, "NF-40")
        parcial = resumir_cobertura_necessidade(necessidade)
        self.assertEqual(parcial["recebido"], Decimal("40"))
        self.assertEqual(parcial["pendente_proprio"], Decimal("60"))
        self.assertEqual(parcial["descoberta"], Decimal("0"))
        self.receber(pedido, 60, "NF-60")
        self.consumir(100)
        cobertura = resumir_cobertura_necessidade(necessidade)
        self.assertEqual(cobertura["saldo_fisico"], Decimal("0"))
        self.assertEqual(cobertura["atendida"], Decimal("100"))
        self.assertEqual(cobertura["descoberta"], Decimal("0"))
        self.assertEqual(gerar_pedidos(self.processo, self.usuario)[0].pk, pedido.pk)

    def test_cancelamento_parcial_preserva_entrega_e_bloqueia_reemissao_integral(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=100, usuario=self.usuario,
        )
        pedido = self.emitir_pedido(necessidade)
        self.receber(pedido, 40, "NF-PARCIAL")
        cancelar_pedido(pedido=pedido, usuario=self.usuario, motivo="Fornecedor não entregará o restante")
        self.consumir(40)
        cobertura = resumir_cobertura_necessidade(necessidade)
        self.assertEqual(cobertura["contratado"], Decimal("0"))
        self.assertEqual(cobertura["recebido"], Decimal("40"))
        self.assertEqual(cobertura["pendente_proprio"], Decimal("0"))
        self.assertEqual(cobertura["descoberta"], Decimal("60"))
        with self.assertRaises(ValidationError):
            gerar_pedidos(self.processo, self.usuario)
        self.assertEqual(self.processo.pedidos.count(), 1)
        self.assertEqual(pedido.recebimentos.count(), 1)

    def test_edicao_preserva_quantidade_original_e_evento_legado(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=10,
            usuario=self.usuario,
        )
        HistoricoProcessoCompra.objects.create(
            processo=self.processo, usuario=self.usuario, tipo="EXCECAO_ESTOQUE",
            descricao="Demanda emergencial",
        )
        necessidade = editar_necessidade(
            processo=self.processo, necessidade=necessidade, material=self.material,
            quantidade=7, observacao="", usuario=self.usuario,
        )
        self.assertEqual(necessidade.quantidade_necessaria, Decimal("10"))
        self.assertEqual(necessidade.quantidade_incluida, Decimal("7"))
        self.assertTrue(self.processo.historico.filter(tipo="EXCECAO_ESTOQUE").exists())

    def test_edicao_e_exclusao_preservam_movimento_de_reserva_consumida(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=20, usuario=self.usuario,
        )
        reserva = ReservaEstoqueCompra.objects.create(
            necessidade=necessidade, obra=self.obra, material=self.material, unidade="UN",
            especificacao=self.material.especificacao, quantidade_original=3,
            quantidade_disponivel=0, status=ReservaEstoqueCompra.Status.CONSUMIDA,
        )
        movimento = MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.SAIDA, obra_origem=self.obra, material=self.material,
            reserva=reserva, descricao_item=self.material.nome, unidade="UN", quantidade=3,
        )
        novo_material = Material.objects.create(
            nome="Bancada teste alternativa", especificacao="Granito B", unidade=self.unidade,
        )
        necessidade = editar_necessidade(
            processo=self.processo, necessidade=necessidade, material=novo_material,
            quantidade=12, observacao="", usuario=self.usuario,
        )
        cobertura = resumir_cobertura_necessidade(necessidade)
        self.assertEqual(cobertura["reserva_historica"].material_id, self.material.pk)
        self.assertEqual(cobertura["reserva_consumida_historica"], Decimal("3"))
        self.assertEqual(cobertura["atendida"], Decimal("0"))
        excluir_necessidade(processo=self.processo, necessidade=necessidade, usuario=self.usuario)
        necessidade.refresh_from_db()
        reserva.refresh_from_db()
        movimento.refresh_from_db()
        self.assertEqual(necessidade.situacao, NecessidadeCompra.Situacao.CANCELADA)
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.CONSUMIDA)
        self.assertEqual(movimento.reserva_id, reserva.pk)
        self.assertEqual(movimento.quantidade, Decimal("3"))

    def test_comando_so_libera_reserva_legada_com_opcao_explicita(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=20, usuario=self.usuario,
        )
        reserva = ReservaEstoqueCompra.objects.create(
            necessidade=necessidade, obra=self.obra, material=self.material, unidade="UN",
            especificacao=self.material.especificacao, quantidade_original=10, quantidade_disponivel=7,
        )
        MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.SAIDA, obra_origem=self.obra, material=self.material,
            reserva=reserva, descricao_item=self.material.nome, unidade="UN", quantidade=3,
        )
        PedidoCompra.objects.bulk_create([
            PedidoCompra(
                processo=self.processo, obra=self.obra, fornecedor=self.fornecedor,
                numero=f"PED-RESERVA-{indice}", status=status,
            )
            for indice, status in enumerate((PedidoCompra.Status.ENTREGA_PARCIAL, PedidoCompra.Status.ENTREGUE), start=1)
        ])
        saida = StringIO()
        call_command("diagnosticar_reservas_compra", stdout=saida)
        relatorio = saida.getvalue()
        self.assertIn(f"reserva={reserva.pk}", relatorio)
        self.assertIn("cobertura_original=PARCIAL", relatorio)
        self.assertIn("ENTREGA_PARCIAL=1", relatorio)
        self.assertIn("ENTREGUE=1", relatorio)
        self.assertIn("PEDIDO_EMITIDO=0", relatorio)
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.ATIVA)
        call_command("diagnosticar_reservas_compra", "--aplicar", stdout=StringIO())
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.LIBERADA)
        self.assertEqual(reserva.quantidade_disponivel, Decimal("0"))
        self.assertEqual(reserva.movimentos.get().quantidade, Decimal("3"))
        atualizado_em = reserva.atualizado_em
        call_command("diagnosticar_reservas_compra", "--aplicar", stdout=StringIO())
        reserva.refresh_from_db()
        self.assertEqual(reserva.atualizado_em, atualizado_em)

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


class ConcorrenciaCoberturaEstoqueCompraTest(FixtureCoberturaEstoqueCompra, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_necessidades_concorrentes_na_mesma_obra_preservam_as_quantidades(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        outro_processo = ProcessoCompra.objects.create(
            numero="PC-COB-CONCORRENTE", obra=self.obra, titulo="Segunda necessidade concorrente",
        )
        inicio = Barrier(2)

        def incluir(processo):
            try:
                inicio.wait(timeout=10)
                return incluir_necessidade(
                    processo=processo, material=self.material, quantidade=Decimal("10"),
                    usuario=self.usuario,
                )
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            tarefas = [executor.submit(incluir, processo) for processo in (self.processo, outro_processo)]
            for tarefa in tarefas:
                self.assertEqual(tarefa.result(timeout=15).quantidade_incluida, Decimal("10"))
        self.assertFalse(ReservaEstoqueCompra.objects.filter(obra=self.obra, material=self.material).exists())
