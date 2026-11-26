from datetime import date
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from openpyxl import load_workbook

from cadastros.models import Fornecedor
from compras.models import ParcelaPrevistaPedido, PedidoCompra, ProcessoCompra, RecebimentoPedido
from financeiro.models import LiberacaoFinanceiraPedido, PlanoFinanceiro, TituloPagar
from financeiro.services.titulos import atualizar_titulo, cancelar_titulo
from obras.models import Obra
from pos_obra.models import Cliente
from usuarios.models import ModuloSistema, NivelPermissao, Notificacao, PermissaoModulo


class CentralAprovacoesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        usuario_model = get_user_model()
        cls.aprovador = usuario_model.objects.create_user(username="central-aprovador")
        cls.solicitante = usuario_model.objects.create_user(username="central-solicitante")
        cls.leitor = usuario_model.objects.create_user(username="central-leitor")
        for usuario, nivel in (
            (cls.aprovador, NivelPermissao.APROVACAO),
            (cls.solicitante, NivelPermissao.EDICAO),
            (cls.leitor, NivelPermissao.LEITURA),
        ):
            PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=nivel)
        cls.obra = Obra.objects.create(codigo="CENT-A", nome="Obra sintética central")
        cls.outra_obra = Obra.objects.create(codigo="CENT-B", nome="Outra obra sintética")
        cls.fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético central")
        cls.apropriacao = PlanoFinanceiro.objects.create(codigo="CENT", nome="Apropriação sintética")
        cls.processo = ProcessoCompra.objects.create(numero="PROC-CENT", obra=cls.obra, titulo="Processo sintético")
        cls.pedido = PedidoCompra.objects.create(
            numero="PED-CENT", obra=cls.obra, processo=cls.processo, fornecedor=cls.fornecedor, valor_total=Decimal("250"),
        )
        cls.recebimento = RecebimentoPedido.objects.create(pedido=cls.pedido, numero_nota_fiscal="NF-CENT")
        cls.nota_irma = RecebimentoPedido.objects.create(pedido=cls.pedido, numero_nota_fiscal="NF-IRMA")

    def titulo(self, numero, **ajustes):
        dados = {
            "obra": self.obra, "fornecedor": self.fornecedor, "plano_financeiro": self.apropriacao,
            "descricao": "Aquisição sintética", "especificacao_pagamento": "Descrição para análise",
            "valor_original": Decimal("110.00"), "status": TituloPagar.Status.AGUARDANDO_APROVACAO,
            "vencimento": date(2027, 1, 4), "criado_por": self.solicitante, "ciclo_aprovacao": 1,
        }
        return TituloPagar.objects.create(numero=numero, **(dados | ajustes))

    def setUp(self):
        self.client.force_login(self.aprovador)

    def decidir(self, titulo, decisao="APROVADO", **dados):
        return self.client.post(reverse("financeiro:titulo_decidir", args=[titulo.pk]), {
            "decisao": decisao, "ciclo": titulo.ciclo_aprovacao, **dados,
        })

    def test_a_mesma_central_exibe_origens_com_filtros_e_status(self):
        manual = self.titulo("FIN-AVULSA", obra=self.outra_obra)
        compra = self.titulo("FIN-COMPRA", origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, recebimento=self.recebimento)
        prevista = self.titulo(
            "FIN-PREVISTA", origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, recebimento=self.nota_irma,
            status=TituloPagar.Status.PREVISTA, vencimento=None, ciclo_aprovacao=0,
        )
        url = reverse("financeiro:aprovacoes")
        self.assertCountEqual(self.client.get(url).context["titulos"], [manual, compra, prevista])
        filtros = {"origem": "COMPRA", "obra": self.obra.pk, "status": "AGUARDANDO_APROVACAO"}
        self.assertEqual(list(self.client.get(url, filtros).context["titulos"]), [compra])
        aprovada = self.titulo("FIN-APROVADA", status=TituloPagar.Status.APROVADO)
        self.assertEqual(list(self.client.get(url, {"status": "APROVADO"}).context["titulos"]), [aprovada])

    def test_decisao_desatualizada_e_sem_ciclo_preservam_titulo(self):
        titulo = self.titulo("FIN-VERSAO")
        novo = atualizar_titulo(titulo, usuario=self.solicitante, dados={"valor_original": Decimal("120.00")})
        self.assertEqual(novo.ciclo_aprovacao, 2)
        self.assertEqual(self.decidir(titulo).status_code, 409)
        self.assertEqual(self.decidir(novo, ciclo="").status_code, 409)
        self.assertFalse(titulo.aprovacoes.exists())
        self.assertEqual(self.decidir(novo).status_code, 302)
        self.assertEqual(titulo.aprovacoes.get().ciclo, 2)

    def test_divergencia_exige_ciencia_e_justificativa_individual(self):
        titulo = self.titulo("FIN-DIVERGE", conferencia=TituloPagar.Conferencia.DIVERGENCIA)
        self.decidir(titulo, observacao="Conferi o documento.")
        self.decidir(titulo, ciencia_divergencia="1", observacao="  ")
        self.assertFalse(titulo.aprovacoes.exists())
        self.decidir(titulo, ciencia_divergencia="1", observacao="Conferi o documento.")
        self.assertEqual(titulo.aprovacoes.get().observacao, "Conferi o documento.")
        self.assertTrue(titulo.historico.filter(evento="APROVADO", dados__ciencia_divergencia=True).exists())

    def test_lote_aprova_contas_regulares_e_informa_divergencia(self):
        a = self.titulo("FIN-LOTE-A")
        b = self.titulo("FIN-LOTE-B")
        divergente = self.titulo("FIN-LOTE-D", conferencia=TituloPagar.Conferencia.DIVERGENCIA)
        resposta = self.client.post(reverse("financeiro:aprovacoes_lote"), {
            "titulo": [f"{t.pk}:{t.ciclo_aprovacao}" for t in (a, b, divergente)],
            "ciencia_divergencia": "1", "observacao": "Não é justificativa individual.",
        }, follow=True)
        self.assertContains(resposta, "FIN-LOTE-D")
        self.assertContains(resposta, "análise individual")
        self.assertTrue(a.aprovacoes.exists())
        self.assertTrue(b.aprovacoes.exists())
        self.assertFalse(divergente.aprovacoes.exists())

    def test_correcao_notifica_e_reenvio_exige_novo_ciclo(self):
        titulo = self.titulo("FIN-CORRIGIR")
        self.decidir(titulo, "CORRECAO_SOLICITADA", observacao="Atualize a descrição do serviço.")
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, "CORRECAO_SOLICITADA")
        self.assertEqual(titulo.aprovacoes.get().decisao, "CORRECAO_SOLICITADA")
        self.assertTrue(Notificacao.objects.filter(usuario=self.solicitante, evento="FINANCEIRO_CORRECAO_SOLICITADA").exists())
        self.assertEqual(self.client.post(reverse("financeiro:titulo_enviar_aprovacao", args=[titulo.pk])).status_code, 302)
        self.assertEqual(self.decidir(titulo).status_code, 409)
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(titulo.ciclo_aprovacao, 2)
        self.decidir(titulo, "REJEITADO", observacao="Cancelamento do contrato confirmado.")
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, TituloPagar.Status.REJEITADO)
        self.assertEqual(titulo.aprovacoes.count(), 2)

    def test_leitor_nao_decide_e_post_exige_csrf(self):
        titulo = self.titulo("FIN-SEGURANCA")
        self.client.force_login(self.leitor)
        self.assertEqual(self.decidir(titulo).status_code, 403)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.aprovador)
        self.assertEqual(cliente.post(reverse("financeiro:titulo_decidir", args=[titulo.pk]), {
            "decisao": "APROVADO", "ciclo": 1,
        }).status_code, 403)
        self.assertFalse(titulo.aprovacoes.exists())

    def test_previsao_de_compra_normal_nao_avanca_antes_do_recebimento(self):
        comum = self.titulo(
            "FIN-PREVISAO-NORMAL", status=TituloPagar.Status.PREVISTA, ciclo_aprovacao=0,
            origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, referencia_externa=f"COMPRA_PEDIDO:{self.pedido.pk}",
        )
        marco = ParcelaPrevistaPedido.objects.create(
            pedido=self.pedido, ordem=1, evento_gatilho=ParcelaPrevistaPedido.Gatilho.ASSINATURA,
        )
        contratual = self.titulo(
            "FIN-MARCO", status=TituloPagar.Status.PREVISTA, ciclo_aprovacao=0,
            origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, referencia_externa=f"COMPRA_PARCELA:{marco.pk}",
        )
        resposta = self.client.post(reverse("financeiro:titulo_enviar_aprovacao", args=[comum.pk]), follow=True)
        self.assertContains(resposta, "Aguarde o recebimento")
        comum.refresh_from_db()
        self.assertEqual(comum.status, TituloPagar.Status.PREVISTA)
        self.assertEqual(comum.ciclo_aprovacao, 0)
        self.client.post(reverse("financeiro:titulo_enviar_aprovacao", args=[contratual.pk]))
        contratual.refresh_from_db()
        self.assertEqual(contratual.status, TituloPagar.Status.AGUARDANDO_APROVACAO)

    def test_divergencia_comercial_filtra_exportacao_e_bloqueia_aprovacao_sem_ciencia(self):
        titulo = self.titulo(
            "FIN-ORCAMENTO", origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, recebimento=self.recebimento,
            conferencia=TituloPagar.Conferencia.CONFERIDO,
        )
        self.titulo("FIN-REGULAR")
        liberacao = LiberacaoFinanceiraPedido.objects.create(
            pedido=self.pedido, recebimento=self.recebimento, titulo=titulo, referencia="RECEBIMENTO:CENTRAL",
            tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO, status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
            valor=Decimal("110.00"), valor_origem=Decimal("110.00"), valor_esperado=Decimal("100.00"),
            divergencias_comerciais=["Preço unitário superior ao contratado."],
        )
        detalhe = self.client.get(reverse("financeiro:titulo_detalhe", args=[titulo.pk]))
        self.assertEqual(detalhe.context["origem_recebimento"]["diferenca"], Decimal("10.00"))
        self.assertEqual(detalhe.context["origem_recebimento"]["percentual"], Decimal("10.00"))
        self.assertContains(detalhe, "Preço unitário superior ao contratado.")
        self.assertContains(detalhe, "name=\"ciclo\" value=\"1\"")
        central = self.client.get(reverse("financeiro:aprovacoes"), {"divergencia": "sim"})
        self.assertEqual(list(central.context["titulos"]), [titulo])
        self.assertNotContains(central, f"value=\"{titulo.pk}:1\"")
        resposta = self.client.get(reverse("financeiro:exportar", args=["aprovacoes", "xlsx"]), {"divergencia": "sim"})
        planilha = load_workbook(BytesIO(resposta.content), read_only=True)
        self.addCleanup(planilha.close)
        self.assertEqual([linha[0] for linha in list(planilha.active.values)[1:]], [titulo.numero])
        self.decidir(titulo, observacao="Documento lido.")
        self.assertFalse(titulo.aprovacoes.exists())
        liberacao.status = LiberacaoFinanceiraPedido.Status.DIVERGENTE
        liberacao.save(update_fields=["status"])
        self.decidir(titulo, observacao="Aprovado após análise.", ciencia_divergencia="1")
        self.assertFalse(titulo.aprovacoes.exists())

    def test_cancelamento_de_parcela_preserva_as_irmas_e_saldo_da_liberacao(self):
        liberacao = LiberacaoFinanceiraPedido.objects.create(
            pedido=self.pedido, recebimento=self.recebimento, referencia="RECEBIMENTO:PARCELAS",
            tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO, status=LiberacaoFinanceiraPedido.Status.AUTORIZADA,
            valor=Decimal("110.00"), valor_origem=Decimal("110.00"), valor_esperado=Decimal("100.00"),
        )
        parametros = {"origem": TituloPagar.Origem.COMPRA, "pedido": self.pedido, "recebimento": self.recebimento}
        primeira = self.titulo("FIN-PARC-1", valor_original=Decimal("45"), referencia_externa=f"COMPRA_LIBERACAO:{liberacao.pk}", **parametros)
        segunda = self.titulo("FIN-PARC-2", valor_original=Decimal("65"), referencia_externa=f"COMPRA_LIBERACAO:{liberacao.pk}:2", **parametros)
        liberacao.titulo = primeira
        liberacao.save(update_fields=["titulo"])
        cancelar_titulo(segunda, usuario=self.solicitante, motivo="Ajuste sintético")
        liberacao.refresh_from_db()
        primeira.refresh_from_db()
        self.assertEqual(primeira.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.assertEqual(liberacao.status, LiberacaoFinanceiraPedido.Status.AUTORIZADA)
        self.assertEqual(liberacao.valor, Decimal("45.00"))
        cancelar_titulo(primeira, usuario=self.solicitante, motivo="Cancelamento sintético")
        liberacao.refresh_from_db()
        self.assertEqual(liberacao.status, LiberacaoFinanceiraPedido.Status.CANCELADA)
        self.assertEqual(liberacao.valor_origem, Decimal("110.00"))

    @override_settings(MIDDLEWARE=[*settings.MIDDLEWARE, "pos_obra.middleware.IsolamentoPortalClienteMiddleware"])
    def test_nota_fiscal_restrita_ao_recebimento_do_titulo_e_leitor_financeiro(self):
        for recebimento in (self.recebimento, self.nota_irma):
            recebimento.arquivo_nota_fiscal.save(f"{recebimento.numero_nota_fiscal}.pdf", ContentFile(b"%PDF-sintetico"))
            self.addCleanup(recebimento.arquivo_nota_fiscal.delete, save=False)
        titulo = self.titulo("FIN-NF", origem=TituloPagar.Origem.COMPRA, pedido=self.pedido, recebimento=self.recebimento)
        nome = "financeiro:baixar_nota_fiscal_pedido_titulo"
        url = reverse(nome, args=[titulo.pk, self.recebimento.pk])
        self.client.force_login(self.leitor)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), b"%PDF-sintetico")
        self.assertTrue(resposta.closed)
        self.assertEqual(resposta.headers["Cache-Control"], "private, no-store")
        outra_nota = self.client.get(reverse(nome, args=[titulo.pk, self.nota_irma.pk]))
        if outra_nota.streaming:
            b"".join(outra_nota.streaming_content)
        self.assertEqual(outra_nota.status_code, 404)
        externo = get_user_model().objects.create_user(username="central-portal")
        self.client.force_login(externo)
        self.assertEqual(self.client.get(url).status_code, 403)
        Cliente.objects.create(nome="Cliente sintético", usuario=externo, portal_habilitado=True)
        self.assertRedirects(self.client.get(url), reverse("core:index"), fetch_redirect_response=False)
