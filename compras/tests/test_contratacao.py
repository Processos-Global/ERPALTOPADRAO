from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from cadastros.models import Fornecedor
from compras.models import (
    AdjudicacaoCompra,
    ContratacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    NecessidadeCompra,
    ProcessoCompra,
)
from compras.services.contratacao import anexar_documento_fornecedor, formalizar_fornecedor
from obras.models import Obra


def criar_compra_aprovada():
    obra = Obra.objects.create(nome="Obra teste contratação", codigo="OB-CONTR-1")
    processo = ProcessoCompra.objects.create(
        numero="PC-CONTR-1",
        obra=obra,
        titulo="Compra teste contratação",
        status=ProcessoCompra.Status.APROVADO,
    )
    fornecedor = Fornecedor.objects.create(nome="Fornecedor teste contratação")
    return processo, fornecedor


def adjudicar(processo, fornecedor):
    necessidade = NecessidadeCompra.objects.create(
        processo=processo, descricao="Material sintético", unidade="UN",
        quantidade_necessaria=1, quantidade_incluida=1,
    )
    cotacao = CotacaoFornecedor.objects.create(processo=processo, fornecedor=fornecedor)
    item = CotacaoFornecedorItem.objects.create(
        cotacao=cotacao, necessidade=necessidade, quantidade=1, valor_unitario_cotado=10,
    )
    AdjudicacaoCompra.objects.create(
        processo=processo, necessidade=necessidade, cotacao=cotacao,
        item_cotado=item, quantidade=1, valor_unitario_final=10,
    )


class ContratacaoCompraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.processo, cls.fornecedor = criar_compra_aprovada()

    def criar_contratacao(self, **dados):
        return ContratacaoCompra.objects.create(
            processo=self.processo, fornecedor=self.fornecedor, **dados
        )

    def test_banco_impede_segunda_contratacao_ativa(self):
        self.criar_contratacao()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.criar_contratacao()

    def test_chave_unica_inclui_o_marcador_gerado(self):
        with connection.cursor() as cursor:
            restricoes = connection.introspection.get_constraints(
                cursor, ContratacaoCompra._meta.db_table
            )
        self.assertIn(
            ["processo_id", "fornecedor_id", "marcador_ativa"],
            [restricao["columns"] for restricao in restricoes.values() if restricao["unique"]],
        )

    def test_banco_preserva_canceladas_e_rejeita_reativacao_em_conflito(self):
        antiga = self.criar_contratacao(cancelada=True)
        primeira = self.criar_contratacao()
        ContratacaoCompra.objects.filter(pk=primeira.pk).update(cancelada=True)
        atual = self.criar_contratacao()

        with self.assertRaises(IntegrityError), transaction.atomic():
            ContratacaoCompra.objects.filter(pk=antiga.pk).update(cancelada=False)

        self.assertCountEqual(
            self.processo.contratacoes.values_list("pk", "cancelada"),
            [(antiga.pk, True), (primeira.pk, True), (atual.pk, False)],
        )

    def test_banco_permite_contratacoes_ativas_em_pares_distintos(self):
        self.criar_contratacao()
        outro_processo = ProcessoCompra.objects.create(
            numero="PC-CONTR-2", obra_id=self.processo.obra_id, titulo="Outra compra",
        )
        outro_fornecedor = Fornecedor.objects.create(nome="Outro fornecedor teste")
        ContratacaoCompra.objects.bulk_create([
            ContratacaoCompra(processo=outro_processo, fornecedor=self.fornecedor),
            ContratacaoCompra(processo=self.processo, fornecedor=outro_fornecedor),
        ])
        self.assertEqual(ContratacaoCompra.objects.filter(cancelada=False).count(), 3)

    def test_formalizar_e_anexar_reutilizam_contratacao_ativa(self):
        adjudicar(self.processo, self.fornecedor)
        anterior = self.criar_contratacao(cancelada=True, documento="anterior.pdf")
        primeira = anexar_documento_fornecedor(
            processo=self.processo, fornecedor=self.fornecedor, usuario=None, documento="anexo.pdf",
        )
        formalizada = formalizar_fornecedor(
            processo=self.processo, fornecedor=self.fornecedor, usuario=None,
            tipo_formalizacao=ContratacaoCompra.TipoFormalizacao.CONTRATO, referencia_contrato="TESTE-1",
        )
        self.assertEqual(primeira.pk, formalizada.pk)
        self.assertEqual(formalizada.documento.name, "anexo.pdf")
        self.assertEqual(formalizada.referencia_contrato, "TESTE-1")
        anterior.refresh_from_db()
        self.assertEqual(anterior.documento.name, "anterior.pdf")
        self.assertEqual(self.processo.contratacoes.count(), 2)

    def test_servicos_revalidam_status_bloqueado_do_processo(self):
        adjudicar(self.processo, self.fornecedor)
        ProcessoCompra.objects.filter(pk=self.processo.pk).update(status=ProcessoCompra.Status.CANCELADO)
        dados = {"processo": self.processo, "fornecedor": self.fornecedor, "usuario": None}

        with self.assertRaises(ValidationError):
            anexar_documento_fornecedor(**dados, documento="anexo.pdf")
        with self.assertRaises(ValidationError):
            formalizar_fornecedor(**dados, tipo_formalizacao=ContratacaoCompra.TipoFormalizacao.PEDIDO)
        self.assertFalse(self.processo.contratacoes.exists())

    def test_diagnostico_desconsidera_historico_cancelado(self):
        self.criar_contratacao()
        self.criar_contratacao(cancelada=True)
        self.criar_contratacao(cancelada=True)
        stdout = StringIO()

        call_command("diagnosticar_contratacoes_duplicadas", database="default", stdout=stdout)

        self.assertIn("Nenhuma contratação ativa duplicada", stdout.getvalue())
        self.assertEqual(self.processo.contratacoes.count(), 3)


class ConcorrenciaContratacaoCompraTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_formalizacao_e_anexo_concorrentes_reutilizam_a_mesma_contratacao(self):
        processo, fornecedor = criar_compra_aprovada()
        adjudicar(processo, fornecedor)
        bloqueio_formalizar = Event()
        bloqueio_anexar = Event()

        def executar(acao, bloqueio_iniciado, **dados):
            conexao = connections["default"]

            def sinalizar_bloqueio(execute, sql, params, many, context):
                if "compras_processocompra" in sql and "FOR UPDATE" in sql:
                    bloqueio_iniciado.set()
                return execute(sql, params, many, context)

            try:
                with conexao.execute_wrapper(sinalizar_bloqueio):
                    return acao(processo=processo, fornecedor=fornecedor, usuario=None, **dados).pk
            finally:
                conexao.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            with transaction.atomic():
                ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
                formalizacao = executor.submit(
                    executar, formalizar_fornecedor, bloqueio_formalizar,
                    tipo_formalizacao=ContratacaoCompra.TipoFormalizacao.CONTRATO,
                    referencia_contrato="CONCORRENCIA",
                )
                anexo = executor.submit(
                    executar, anexar_documento_fornecedor, bloqueio_anexar, documento="anexo.pdf",
                )
                self.assertTrue(bloqueio_formalizar.wait(10))
                self.assertTrue(bloqueio_anexar.wait(10))
                self.assertFalse(formalizacao.done())
                self.assertFalse(anexo.done())
            self.assertEqual(formalizacao.result(timeout=10), anexo.result(timeout=10))

        contratacao = processo.contratacoes.get(cancelada=False)
        self.assertEqual(contratacao.referencia_contrato, "CONCORRENCIA")
        self.assertEqual(contratacao.documento.name, "anexo.pdf")
