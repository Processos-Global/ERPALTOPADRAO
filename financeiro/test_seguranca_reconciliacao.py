from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, modify_settings
from django.urls import reverse
from openpyxl import load_workbook

from cadastros.models import Fornecedor
from compras.models import PedidoCompra, ProcessoCompra
from financeiro.models import (
    AnexoTituloPagar, AprovacaoTituloFinanceiro, LiberacaoFinanceiraPedido,
    ItemRelatorioPagamento, Pagamento, PlanoFinanceiro, ProgramacaoPagamento, RelatorioPagamento, TituloPagar,
)
from financeiro.services.compromissos import pedidos_comprometidos, totais_pedidos
from financeiro.services.fluxo_caixa import serie_desembolsos
from financeiro.services.pagamentos import estornar_pagamento
from financeiro.services.titulos import atualizar_titulo, criar_titulos_manuais
from obras.models import Obra
from pos_obra.models import Cliente
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoFinanceiro, PermissaoModulo


class SegurancaReconciliacaoFinanceiraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.leitor = cls.usuario_financeiro("leitor")
        cls.aprovador = cls.usuario_financeiro("aprovador", aprovar_pagamentos=True)
        cls.pagador = cls.usuario_financeiro("pagador", registrar_pagamentos=True)
        cls.editor = cls.usuario_financeiro("editor", editar_titulos=True)
        cls.vencimento = date(2026, 10, 1)
        cls.obra = Obra.objects.create(nome="Obra sintética", codigo="OB-QA-FIN")
        cls.fornecedor = Fornecedor.objects.create(nome="Beneficiário sintético")
        cls.titulo = TituloPagar.objects.create(
            numero="QA-FIN-APROVAR", origem=TituloPagar.Origem.MANUAL,
            status=TituloPagar.Status.AGUARDANDO_APROVACAO, ciclo_aprovacao=1,
            descricao="Obrigação sintética aguardando aprovação",
            obra=cls.obra, fornecedor=cls.fornecedor, vencimento=cls.vencimento,
            valor_original=Decimal("100.00"), desconto=Decimal("5.00"),
            juros=Decimal("2.00"), multa=Decimal("3.00"),
        )

    @classmethod
    def usuario_financeiro(cls, nome, **acoes):
        usuario = get_user_model().objects.create_user(username=f"qa_fin_{nome}")
        cls.conceder_acoes_financeiras(usuario, **acoes)
        return usuario

    @staticmethod
    def conceder_acoes_financeiras(usuario, **acoes):
        PermissaoModulo.objects.create(
            usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.APROVACAO,
        )
        PermissaoFinanceiro.objects.create(usuario=usuario, **acoes)

    def efetivar_titulo(self, titulo):
        self.client.force_login(self.pagador)
        url = reverse("financeiro:pagamento_confirmar_direto", args=[titulo.pk])
        resposta = self.client.post(url)
        self.assertEqual(resposta.status_code, 200)
        titulo.refresh_from_db()
        return Pagamento.objects.get(titulo=titulo)

    def test_permissoes_granulares_protegem_acoes_mesmo_com_nivel_legado_de_aprovacao(self):
        decidir = reverse("financeiro:titulo_decidir", args=[self.titulo.pk])
        confirmar = reverse("financeiro:pagamento_confirmar_direto", args=[self.titulo.pk])
        cancelar = reverse("financeiro:titulo_cancelar", args=[self.titulo.pk])
        editar = reverse("financeiro:titulo_editar", args=[self.titulo.pk])
        for usuario in (self.leitor, self.pagador, self.editor):
            with self.subTest(usuario=usuario.username, acao="aprovar"):
                self.client.force_login(usuario)
                self.assertEqual(self.client.post(decidir, {"decisao": "APROVADO"}).status_code, 403)

        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.get(decidir).status_code, 405)
        self.assertEqual(self.client.post(decidir, {
            "decisao": "APROVADO", "ciclo": self.titulo.ciclo_aprovacao,
        }).status_code, 302)
        self.titulo.refresh_from_db()
        self.assertEqual(self.titulo.status, TituloPagar.Status.APROVADO)
        self.assertEqual(self.titulo.aprovacoes.get().usuario, self.aprovador)
        self.assertEqual(self.client.post(cancelar).status_code, 403)
        self.assertEqual(
            self.client.post(editar, {"valor_original": "999.00", "beneficiario_banco": "Outro banco"}).status_code,
            403,
        )
        for usuario in (self.leitor, self.aprovador, self.editor):
            with self.subTest(usuario=usuario.username, acao="pagar"):
                self.client.force_login(usuario)
                self.assertEqual(self.client.post(confirmar).status_code, 403)
        self.assertFalse(Pagamento.objects.filter(titulo=self.titulo).exists())

        pagamento = self.efetivar_titulo(self.titulo)
        url_estorno = reverse("financeiro:pagamento_estornar", args=[pagamento.pk])
        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.post(url_estorno, {"motivo": "Indevido"}).status_code, 403)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, Pagamento.Status.EFETIVADO)

    def test_liberacao_exige_aprovar_e_fica_idempotente(self):
        categoria = PlanoFinanceiro.objects.create(codigo="QA-LIB", nome="Categoria sintética")
        apropriacao = PlanoFinanceiro.objects.create(
            codigo="QA-LIB-01", nome="Apropriação sintética", pai=categoria,
        )
        processo = ProcessoCompra.objects.create(
            numero="PC-QA-FIN", obra=self.obra, titulo="Compra sintética", apropriacao=apropriacao,
        )
        pedido = PedidoCompra.objects.create(
            numero="PED-QA-FIN", processo=processo, obra=self.obra, fornecedor=self.fornecedor,
            valor_total=Decimal("150.00"),
        )
        liberacao = LiberacaoFinanceiraPedido.objects.create(
            pedido=pedido, tipo=LiberacaoFinanceiraPedido.Tipo.CONDICAO,
            referencia="QA-FIN-LIBERACAO", valor=Decimal("75.01"),
            valor_origem=Decimal("75.01"), justificativa="Condição contratual sintética",
        )
        url = reverse("financeiro:liberacao_autorizar", args=[liberacao.pk])
        self.client.force_login(self.pagador)
        self.assertEqual(self.client.post(url).status_code, 403)
        liberacao.refresh_from_db()
        self.assertIsNone(liberacao.titulo_id)

        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url).status_code, 302)
        liberacao.refresh_from_db()
        titulo = liberacao.titulo
        self.assertEqual(liberacao.status, LiberacaoFinanceiraPedido.Status.AUTORIZADA)
        self.assertEqual(liberacao.autorizado_por, self.aprovador)
        self.assertEqual(titulo.valor_original, Decimal("75.01"))
        self.assertEqual(self.client.post(url).status_code, 302)
        liberacao.refresh_from_db()
        self.assertEqual(liberacao.titulo_id, titulo.pk)
        self.assertEqual(
            TituloPagar.objects.filter(pedido=pedido, valor_original=Decimal("75.01")).count(), 1,
        )
        compromissos = pedidos_comprometidos(obra_id=self.obra.pk)
        totais = totais_pedidos(compromissos)
        self.assertEqual(totais["contratado"], Decimal("150.00"))
        self.assertEqual(totais["liberado_financeiramente"], Decimal("75.01"))
        self.assertEqual(totais["pago_efetivado"], Decimal("0.00"))
        self.assertEqual(totais["saldo_financeiro"], Decimal("150.00"))

        self.client.force_login(self.editor)
        configurar = reverse("financeiro:titulo_configurar", args=[titulo.pk])
        self.assertEqual(self.client.post(configurar, {"vencimento": self.vencimento.isoformat()}).status_code, 302)
        self.aprovar_titulo(titulo)
        pagamento = self.efetivar_titulo(titulo)
        totais = totais_pedidos(compromissos)
        self.assertEqual(totais["liberado_financeiramente"], Decimal("75.01"))
        self.assertEqual(totais["pago_efetivado"], Decimal("75.01"))
        self.assertEqual(totais["saldo_financeiro"], Decimal("74.99"))

        estornar = reverse("financeiro:pagamento_estornar", args=[pagamento.pk])
        self.assertEqual(self.client.post(estornar, {"motivo": "Estorno sintético"}).status_code, 302)
        totais = totais_pedidos(compromissos)
        self.assertEqual(totais["pago_efetivado"], Decimal("0.00"))
        self.assertEqual(totais["saldo_financeiro"], Decimal("150.00"))

    @modify_settings(MIDDLEWARE={"append": "django.middleware.csrf.CsrfViewMiddleware"})
    def test_confirmacao_exige_post_e_csrf_e_repeticao_preserva_um_pagamento(self):
        self.aprovar_titulo(self.titulo)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.pagador)
        confirmar = reverse("financeiro:pagamento_confirmar_direto", args=[self.titulo.pk])
        self.assertEqual(cliente.get(confirmar).status_code, 405)
        self.assertEqual(cliente.post(confirmar).status_code, 403)
        self.assertFalse(Pagamento.objects.filter(titulo=self.titulo).exists())

        formulario = reverse("financeiro:pagamento_novo", args=[self.titulo.pk])
        self.assertEqual(cliente.get(formulario).status_code, 200)
        csrf = cliente.cookies["csrftoken"].value
        self.assertEqual(cliente.post(confirmar, headers={"X-CSRFToken": csrf}).status_code, 200)
        pagamento = Pagamento.objects.get(titulo=self.titulo)
        repeticao = cliente.post(confirmar, headers={"X-CSRFToken": csrf})
        self.assertEqual(repeticao.status_code, 400)
        self.assertFalse(repeticao.json()["ok"])
        self.assertEqual(Pagamento.objects.get(titulo=self.titulo).pk, pagamento.pk)
        self.assertEqual(self.titulo.historico.filter(evento="PAGAMENTO").count(), 1)

    def test_confirmacao_rejeita_titulo_sem_aprovacao_ou_sem_saldo_positivo(self):
        self.client.force_login(self.pagador)
        confirmar = reverse("financeiro:pagamento_confirmar_direto", args=[self.titulo.pk])
        self.assertEqual(self.client.post(confirmar).status_code, 400)
        self.titulo.refresh_from_db()
        self.assertEqual(self.titulo.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
        self.aprovar_titulo(self.titulo)
        self.client.force_login(self.pagador)
        self.titulo.desconto = Decimal("105.00")
        self.titulo.save(update_fields=["desconto"])
        self.assertEqual(self.client.post(confirmar).status_code, 400)
        self.assertFalse(Pagamento.objects.filter(titulo=self.titulo).exists())
        self.titulo.refresh_from_db()
        self.assertEqual(self.titulo.status, TituloPagar.Status.APROVADO)

    @modify_settings(MIDDLEWARE={"append": "pos_obra.middleware.IsolamentoPortalClienteMiddleware"})
    def test_conta_portal_nao_alcanca_rotas_financeiras_mesmo_com_permissao_granular(self):
        cliente_portal = get_user_model().objects.create_user(username="qa_fin_portal")
        Cliente.objects.create(nome="Cliente sintético", usuario=cliente_portal, portal_habilitado=True)
        # Simula um cadastro legado com concessão posterior incompatível com o portal.
        self.conceder_acoes_financeiras(cliente_portal, registrar_pagamentos=True)
        self.titulo.status = TituloPagar.Status.APROVADO
        self.titulo.save(update_fields=["status"])
        self.client.force_login(cliente_portal)
        detalhe = reverse("financeiro:titulo_detalhe", args=[self.titulo.pk])
        confirmar = reverse("financeiro:pagamento_confirmar_direto", args=[self.titulo.pk])
        self.assertRedirects(self.client.get(detalhe), reverse("core:index"), fetch_redirect_response=False)
        self.assertEqual(self.client.post(confirmar).status_code, 403)
        self.assertFalse(Pagamento.objects.filter(titulo=self.titulo).exists())

    def test_download_de_anexo_verifica_titulo_e_permissao_e_usa_armazenamento_privado(self):
        conteudo = b"%PDF-1.4\nDocumento sintetico de reconciliacao\n"
        anexo = AnexoTituloPagar.objects.create(
            titulo=self.titulo, arquivo=SimpleUploadedFile("qa.pdf", conteudo, "application/pdf"),
            nome_original="qa.pdf", enviado_por=self.editor,
        )
        self.addCleanup(anexo.arquivo.delete, save=False)
        self.assertTrue(Path(anexo.arquivo.path).is_relative_to(settings.PRIVATE_MEDIA_ROOT))
        url = reverse("financeiro:baixar_anexo_titulo", args=[self.titulo.pk, anexo.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        usuario_sem_acesso = get_user_model().objects.create_user(username="qa_fin_sem_modulo")
        self.client.force_login(usuario_sem_acesso)
        self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.leitor)
        outro_titulo = TituloPagar.objects.create(
            numero="QA-FIN-OUTRO", descricao="Outro título sintético", valor_original=Decimal("25.00"),
        )
        url_incorreta = reverse("financeiro:baixar_anexo_titulo", args=[outro_titulo.pk, anexo.pk])
        self.assertEqual(self.client.get(url_incorreta).status_code, 404)
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Cache-Control"], "private, no-store")
        self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(resposta.streaming_content), conteudo)

    def test_estorno_repetido_com_instancia_antiga_preserva_autor_e_evento(self):
        self.aprovar_titulo(self.titulo)
        pagamento = self.efetivar_titulo(self.titulo)
        leitura_alternativa = Pagamento.objects.get(pk=pagamento.pk)
        segundo_pagador = self.usuario_financeiro("segundo_pagador", registrar_pagamentos=True)
        estornar_pagamento(pagamento, usuario=self.pagador, motivo="Primeira solicitação")
        estornar_pagamento(leitura_alternativa, usuario=segundo_pagador, motivo="Solicitação repetida")
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, Pagamento.Status.ESTORNADO)
        self.assertEqual(pagamento.estornado_por, self.pagador)
        self.assertEqual(pagamento.motivo_estorno, "Primeira solicitação")
        evento = self.titulo.historico.get(evento="ESTORNO")
        self.assertEqual(evento.usuario, self.pagador)
        self.assertEqual(evento.dados["valor_anterior"], "100.00")
        self.assertEqual(evento.dados["valor_novo"], "0.00")
        self.assertEqual(evento.dados["motivo"], "Primeira solicitação")

    def test_edicao_iniciada_antes_da_confirmacao_nao_altera_titulo_pago(self):
        self.aprovar_titulo(self.titulo)
        leitura_anterior = TituloPagar.objects.get(pk=self.titulo.pk)
        pagamento = self.efetivar_titulo(self.titulo)
        with self.assertRaises(ValueError):
            atualizar_titulo(
                leitura_anterior, usuario=self.editor,
                dados={"valor_original": Decimal("999.00"), "beneficiario_banco": "Outro banco"},
            )
        self.titulo.refresh_from_db()
        self.assertEqual(self.titulo.status, TituloPagar.Status.PAGO)
        self.assertEqual(self.titulo.valor_original, Decimal("100.00"))
        self.assertEqual(self.titulo.beneficiario_banco, "")
        self.assertEqual(self.titulo.total_pago, Decimal("100.00"))
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.status, Pagamento.Status.EFETIVADO)
        self.assertFalse(self.titulo.historico.filter(evento="ATUALIZADO").exists())

    def aprovar_titulo(self, titulo):
        self.client.force_login(self.aprovador)
        titulo.refresh_from_db()
        decidir = reverse("financeiro:titulo_decidir", args=[titulo.pk])
        self.assertEqual(self.client.post(decidir, {
            "decisao": "APROVADO", "ciclo": titulo.ciclo_aprovacao,
        }).status_code, 302)
        titulo.refresh_from_db()
        return titulo.aprovacoes.get(ciclo=titulo.ciclo_aprovacao)

    def emitir_malote(self, *aprovacoes):
        self.client.force_login(self.pagador)
        emitir = reverse("financeiro:relatorio_pagamento_emitir")
        dados = {"aprovacoes": [aprovacao.pk for aprovacao in aprovacoes]}
        dados.update({f"meio_{aprovacao.pk}": "BOLETO" for aprovacao in aprovacoes})
        self.assertEqual(self.client.post(emitir, dados).status_code, 302)

    def test_malote_rejeita_aprovacao_do_ciclo_anterior(self):
        anterior = self.aprovar_titulo(self.titulo)
        atualizar_titulo(self.titulo, usuario=self.editor, dados={"desconto": Decimal("6.00")})
        atual = self.aprovar_titulo(self.titulo)
        self.assertGreater(atual.ciclo, anterior.ciclo)
        self.emitir_malote(anterior)
        self.assertFalse(RelatorioPagamento.objects.exists())
        self.emitir_malote(atual)
        relatorio = RelatorioPagamento.objects.get()
        self.assertEqual(relatorio.itens.get().aprovacao, atual)
        self.assertEqual(relatorio.valor_total, Decimal("99.00"))

    def test_malote_rejeita_segunda_emissao_do_titulo_sem_documento_apos_reaprovacao(self):
        self.assertFalse(self.titulo.documento_numero)
        primeira_aprovacao = self.aprovar_titulo(self.titulo)
        self.emitir_malote(primeira_aprovacao)
        primeiro_malote = RelatorioPagamento.objects.get()
        atualizar_titulo(self.titulo, usuario=self.editor, dados={"desconto": Decimal("6.00")})
        nova_aprovacao = self.aprovar_titulo(self.titulo)
        self.emitir_malote(nova_aprovacao)
        self.assertEqual(RelatorioPagamento.objects.count(), 1)
        self.assertEqual(primeiro_malote.itens.get().aprovacao, primeira_aprovacao)
        self.assertEqual(primeiro_malote.itens.get().valor, Decimal("100.00"))

    def test_reemissao_filtrada_por_obra_reconcilia_somente_itens_exportados(self):
        outra_obra = Obra.objects.create(nome="Outra obra sintética", codigo="OB-QA-FIN-2")
        outro_titulo = TituloPagar.objects.create(
            numero="QA-FIN-OUTRA-OBRA", origem=TituloPagar.Origem.MANUAL,
            status=TituloPagar.Status.AGUARDANDO_APROVACAO, ciclo_aprovacao=1,
            descricao="Obrigação sintética de outra obra", obra=outra_obra,
            fornecedor=self.fornecedor, vencimento=self.vencimento, valor_original=Decimal("12.34"),
        )
        aprovacoes = [self.aprovar_titulo(self.titulo), self.aprovar_titulo(outro_titulo)]
        malote = RelatorioPagamento.objects.create(
            numero="MALOTE-LEGADO-QA", periodo_inicio=self.vencimento, periodo_fim=self.vencimento,
            valor_total=Decimal("112.34"), quantidade_itens=2, emitido_por=self.pagador,
        )
        for aprovacao in aprovacoes:
            titulo = aprovacao.titulo
            ItemRelatorioPagamento.objects.create(
                relatorio=malote, aprovacao=aprovacao, titulo=titulo, data_aprovacao=aprovacao.criado_em,
                conta_numero=titulo.numero, beneficiario_nome=titulo.beneficiario_exibicao, obra_nome=titulo.obra.nome,
                descricao=titulo.descricao, vencimento=titulo.vencimento, valor=titulo.saldo_aberto,
            )

        self.client.force_login(self.leitor)
        url = reverse("financeiro:relatorio_pagamento_excel", args=[malote.pk])
        resposta = self.client.get(url, {"formato": "xlsx", "obra": outra_obra.pk})
        self.assertEqual(resposta.status_code, 200)
        planilha = load_workbook(BytesIO(resposta.content), read_only=True, data_only=True)
        self.addCleanup(planilha.close)
        self.assertEqual(planilha.active["A2"].value, outro_titulo.numero)
        self.assertEqual(planilha.active.max_row, 2)
        controle = planilha["Controle da emissão"]
        self.assertEqual(controle["B6"].value, 1)
        self.assertEqual(Decimal(str(controle["B7"].value)), Decimal("12.34"))

    def test_excel_do_malote_trata_nome_do_emissor_como_texto(self):
        texto = "=1+1"
        self.pagador.first_name = texto
        self.pagador.last_name = ""
        self.pagador.save(update_fields=["first_name", "last_name"])
        self.emitir_malote(self.aprovar_titulo(self.titulo))
        malote = RelatorioPagamento.objects.get()
        url = reverse("financeiro:relatorio_pagamento_excel", args=[malote.pk])

        resposta = self.client.get(url, {"formato": "xlsx"})

        self.assertEqual(resposta.status_code, 200)
        planilha = load_workbook(BytesIO(resposta.content), read_only=True)
        self.addCleanup(planilha.close)
        emissor = planilha["Controle da emissão"]["B4"]
        self.assertEqual(emissor.value, texto)
        self.assertEqual(emissor.data_type, "s")

    def test_titulo_legado_reconcilia_aprovado_pacote_pago_estornado_e_cancelado(self):
        legado = TituloPagar.objects.create(
            numero="QA-FIN-LEGADO", origem=TituloPagar.Origem.DESPESA,
            status=TituloPagar.Status.AGUARDANDO_APROVACAO, ciclo_aprovacao=1,
            descricao="Título histórico sintético", beneficiario_nome="Beneficiário histórico",
            vencimento=self.vencimento, valor_original=Decimal("120.03"),
            desconto=Decimal("15.01"), juros=Decimal("1.05"), multa=Decimal("0.10"),
            outros_acrescimos=Decimal("0.20"),
        )
        self.assertIsNone(legado.obra_id)
        self.assertIsNone(legado.fornecedor_id)
        self.assertIsNone(legado.plano_financeiro_id)
        esperado_liquido = Decimal("106.37")
        decidir = reverse("financeiro:titulo_decidir", args=[legado.pk])
        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.post(decidir, {
            "decisao": "APROVADO", "ciclo": legado.ciclo_aprovacao,
        }).status_code, 302)
        legado.refresh_from_db()
        aprovacao = legado.aprovacoes.get()
        self.assertEqual(aprovacao.decisao, AprovacaoTituloFinanceiro.Decisao.APROVADO)
        self.assertEqual(legado.saldo_aberto, esperado_liquido)
        self.assertEqual(serie_desembolsos(inicio=self.vencimento, dias=0)["total"], Decimal("206.37"))

        emitir = reverse("financeiro:relatorio_pagamento_emitir")
        dados = {"aprovacoes": [aprovacao.pk], f"meio_{aprovacao.pk}": "BOLETO"}
        self.assertEqual(self.client.post(emitir, dados).status_code, 403)
        self.client.force_login(self.pagador)
        self.assertEqual(self.client.post(emitir, dados).status_code, 302)
        relatorio = RelatorioPagamento.objects.get()
        self.assertEqual(relatorio.valor_total, esperado_liquido)
        self.assertEqual(relatorio.itens.get().valor, esperado_liquido)
        self.assertFalse(Pagamento.objects.filter(titulo=legado).exists())
        legado.refresh_from_db()
        self.assertEqual(legado.status, TituloPagar.Status.APROVADO)
        self.assertEqual(self.client.post(emitir, dados).status_code, 302)
        self.assertEqual(RelatorioPagamento.objects.count(), 1)

        exportar = reverse("financeiro:relatorio_pagamento_excel", args=[relatorio.pk])
        self.client.force_login(get_user_model().objects.create_user(username="qa_fin_exportacao_negada"))
        self.assertEqual(self.client.get(exportar, {"formato": "xlsx"}).status_code, 403)
        self.client.force_login(self.leitor)
        resposta = self.client.get(exportar, {"formato": "xlsx"})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("attachment", resposta["Content-Disposition"])
        planilha = load_workbook(BytesIO(resposta.content), read_only=True, data_only=True)
        self.addCleanup(planilha.close)
        self.assertEqual(Decimal(str(planilha.active["I2"].value)), esperado_liquido)
        controle = planilha["Controle da emissão"]
        self.assertEqual(controle["B6"].value, 1)
        self.assertEqual(Decimal(str(controle["B7"].value)), esperado_liquido)

        programar = reverse("financeiro:pagamento_programar", args=[legado.pk])
        dados_programacao = {"data_programada": "2026-12-15", "motivo": "Programação sintética"}
        self.client.force_login(self.aprovador)
        self.assertEqual(self.client.post(programar, dados_programacao).status_code, 403)
        self.client.force_login(self.pagador)
        self.assertEqual(self.client.post(programar, dados_programacao).status_code, 302)
        programacao = ProgramacaoPagamento.objects.get(titulo=legado)
        self.assertTrue(programacao.ativa)
        self.assertEqual(programacao.ciclo_aprovacao, aprovacao.ciclo)
        legado.refresh_from_db()
        self.assertEqual(legado.vencimento, self.vencimento)
        self.assertEqual(legado.total_pago, Decimal("0.00"))
        resposta = self.client.get(reverse("financeiro:pagamentos"), {"aba": "programados"})
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            [(titulo.numero, titulo.saldo_aberto) for titulo in resposta.context["page_obj"]],
            [(legado.numero, esperado_liquido)],
        )

        pagamento = self.efetivar_titulo(legado)
        programacao.refresh_from_db()
        self.assertFalse(programacao.ativa)
        self.assertEqual(pagamento.valor, esperado_liquido)
        self.assertEqual(legado.total_pago, esperado_liquido)
        self.assertEqual(legado.saldo_aberto, Decimal("0.00"))
        self.assertEqual(serie_desembolsos(inicio=self.vencimento, dias=0)["total"], Decimal("100.00"))

        estornar = reverse("financeiro:pagamento_estornar", args=[pagamento.pk])
        self.assertEqual(self.client.post(estornar, {"motivo": "Estorno sintético"}).status_code, 302)
        pagamento.refresh_from_db()
        legado.refresh_from_db()
        self.assertEqual(pagamento.status, Pagamento.Status.ESTORNADO)
        self.assertEqual(pagamento.valor, esperado_liquido)
        self.assertEqual(legado.total_pago, Decimal("0.00"))
        self.assertEqual(legado.saldo_aberto, esperado_liquido)
        self.assertEqual(serie_desembolsos(inicio=self.vencimento, dias=0)["total"], Decimal("206.37"))

        self.client.force_login(self.editor)
        cancelar = reverse("financeiro:titulo_cancelar", args=[legado.pk])
        self.assertEqual(self.client.post(cancelar, {"motivo": "Cancelamento sintético"}).status_code, 302)
        legado.refresh_from_db()
        self.assertEqual(legado.status, TituloPagar.Status.CANCELADO)
        self.assertEqual(legado.valor_original, Decimal("120.03"))
        self.assertEqual(legado.desconto, Decimal("15.01"))
        self.assertEqual(relatorio.itens.get().valor, esperado_liquido)
        self.assertEqual(serie_desembolsos(inicio=self.vencimento, dias=0)["total"], Decimal("100.00"))

    def test_parcelamento_manual_preserva_centavos_e_vencimentos(self):
        parcelas = criar_titulos_manuais(
            usuario=self.editor, quantidade_parcelas=3, intervalo_dias=30,
            obra=self.obra, fornecedor=self.fornecedor, vencimento=self.vencimento,
            descricao="Parcelamento sintético", especificacao_pagamento="Três parcelas",
            valor_original=Decimal("100.00"),
        )
        self.assertEqual(
            [(p.parcela_ordem, p.parcela_total, p.valor_original, p.vencimento) for p in parcelas],
            [
                (1, 3, Decimal("33.34"), date(2026, 10, 1)),
                (2, 3, Decimal("33.33"), date(2026, 10, 31)),
                (3, 3, Decimal("33.33"), date(2026, 11, 30)),
            ],
        )
        self.assertEqual(sum((p.saldo_aberto for p in parcelas), Decimal("0.00")), Decimal("100.00"))
