from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.models import (
    AdjudicacaoCompra, AprovacaoCompra, CotacaoFornecedor, CotacaoFornecedorItem,
    HistoricoProcessoCompra, NecessidadeCompra, PedidoCompra, PedidoCompraItem,
    ProcessoCompra, RecebimentoPedido, RecebimentoPedidoItem, ReservaEstoqueCompra,
)
from compras.services.cobertura_estoque import obter_cobertura, resumir_cobertura_necessidade, revalidar_necessidade
from compras.services.etapas import decidir_aprovacao
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
    def test_bloqueia_compra_totalmente_coberta_na_mesma_obra(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        with self.assertRaises(ValidationError):
            incluir_necessidade(
                processo=self.processo, material=self.material, quantidade=Decimal("5"),
                usuario=self.usuario,
            )
        self.assertFalse(self.processo.necessidades.exists())

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

    def test_edicao_sem_excecao_revoga_autorizacao_anterior(self):
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=10,
            usuario=self.usuario, excecao_estoque=True, justificativa_excecao="Demanda emergencial",
        )
        necessidade = editar_necessidade(
            processo=self.processo, necessidade=necessidade, material=self.material,
            quantidade=10, observacao="", usuario=self.usuario,
        )
        self.registrar_entrada(self.obra, Decimal("4"))
        with self.assertRaises(ValidationError):
            revalidar_necessidade(necessidade)
        self.assertTrue(self.processo.historico.filter(tipo="EXCECAO_ESTOQUE").exists())

    def test_reprovacao_libera_saldo_reservado_e_preserva_atendimento_consumido(self):
        self.registrar_entrada(self.obra, Decimal("10"))
        necessidade = incluir_necessidade(
            processo=self.processo, material=self.material, quantidade=20, usuario=self.usuario,
        )
        reserva = necessidade.reserva_estoque
        self.consumir(3, reserva)
        self.processo.etapa_atual = ProcessoCompra.Etapa.APROVACAO
        self.processo.status = ProcessoCompra.Status.AGUARDANDO_APROVACAO
        self.processo.save(update_fields=["etapa_atual", "status"])
        decidir_aprovacao(self.processo, self.usuario, AprovacaoCompra.Decisao.REPROVADO, "Compra reprovada")
        reserva.refresh_from_db()
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.LIBERADA)
        self.assertEqual(reserva.movimentos.get().quantidade, Decimal("3"))
        cobertura = resumir_cobertura_necessidade(necessidade)
        self.assertEqual(cobertura["disponivel"], Decimal("7"))
        self.assertEqual(cobertura["reserva_consumida"], Decimal("3"))

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
    def test_necessidades_concorrentes_reservam_o_saldo_uma_unica_vez(self):
        self.registrar_entrada(self.obra, Decimal("4"))
        outro_processo = ProcessoCompra.objects.create(
            numero="PC-COB-CONCORRENTE", obra=self.obra, titulo="Segunda necessidade concorrente",
        )
        tentativa_bloqueio = Event()

        def incluir_segunda_necessidade():
            conexao = connections["default"]
            tabela_obra = conexao.ops.quote_name(Obra._meta.db_table)

            def sinalizar_bloqueio(execute, sql, params, many, context):
                if tabela_obra in sql and "FOR UPDATE" in sql:
                    tentativa_bloqueio.set()
                return execute(sql, params, many, context)

            try:
                with conexao.execute_wrapper(sinalizar_bloqueio):
                    return incluir_necessidade(
                        processo=outro_processo, material=self.material, quantidade=Decimal("10"),
                        usuario=self.usuario,
                    ).pk
            finally:
                conexao.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                primeira = incluir_necessidade(
                    processo=self.processo, material=self.material, quantidade=Decimal("10"),
                    usuario=self.usuario,
                )
                self.assertEqual(primeira.reserva_estoque.quantidade_disponivel, Decimal("4"))

                # Mantém a primeira reserva sem commit até a segunda tentar travar a mesma obra.
                concorrente = executor.submit(incluir_segunda_necessidade)
                self.assertTrue(tentativa_bloqueio.wait(timeout=10), "A segunda conexão não tentou bloquear a obra.")
                self.assertFalse(concorrente.done())
            segunda = NecessidadeCompra.objects.get(pk=concorrente.result(timeout=10))

        self.assertEqual(primeira.quantidade_incluida, Decimal("6"))
        self.assertEqual(segunda.quantidade_incluida, Decimal("10"))
        reserva = ReservaEstoqueCompra.objects.get(obra=self.obra, material=self.material)
        self.assertEqual(reserva.necessidade_id, primeira.pk)
        self.assertEqual(reserva.status, ReservaEstoqueCompra.Status.ATIVA)
        self.assertEqual(reserva.quantidade_original, Decimal("4"))
        self.assertEqual(reserva.quantidade_disponivel, Decimal("4"))
