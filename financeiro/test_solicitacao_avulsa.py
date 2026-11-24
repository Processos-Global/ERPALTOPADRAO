from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor
from financeiro.models import Pagamento, PlanoFinanceiro, TituloPagar
from financeiro.models.titulos import SolicitacaoAvulsa
from financeiro.services.titulos import atualizar_titulo
from financeiro.views.titulos import titulo_novo
from obras.models import Obra
from usuarios.models import Notificacao


def dados_sinteticos():
    obra = Obra.objects.create(nome="Obra de teste", codigo="OB-TST-AVULSA")
    fornecedor = Fornecedor.objects.create(nome="Beneficiário de teste")
    classe = PlanoFinanceiro.objects.create(codigo="AV", nome="Classe de teste")
    apropriacao = PlanoFinanceiro.objects.create(codigo="AV.01", nome="Apropriação de teste", pai=classe)
    return {
        "obra": obra.pk, "fornecedor": fornecedor.pk, "plano_financeiro": apropriacao.pk,
        "tipo_pagamento": "OUTRO", "descricao": "Reparo", "especificacao_pagamento": "Manutenção de teste",
        "valor_original": "100.00", "desconto": "0", "juros": "0", "multa": "0",
        "outros_acrescimos": "0", "vencimento": "2026-11-30", "quantidade_parcelas": 3, "intervalo_dias": 30,
    }


def criar_usuario(nome):
    return get_user_model().objects.create_superuser(username=nome, password="teste")


def chave_da_pagina(response):
    return response.context["form"]["chave_idempotencia"].value()


class SolicitacaoAvulsaTests(TestCase):
    def setUp(self):
        self.usuario = criar_usuario("lancador_avulsa")
        self.client.force_login(self.usuario)
        self.novo = reverse("financeiro:titulo_novo")
        self.dados = dados_sinteticos()
        self.chave = chave_da_pagina(self.client.get(self.novo))
        midia = TemporaryDirectory()
        self.addCleanup(midia.cleanup)
        self.enterContext(self.settings(PRIVATE_MEDIA_ROOT=midia.name))
        self.midia = Path(midia.name)

    def post(self, *, chave=None, arquivo=None, **dados):
        carga = {**self.dados, **dados, "chave_idempotencia": self.chave if chave is None else chave}
        if arquivo is not None:
            carga["anexos"] = SimpleUploadedFile("documento.pdf", arquivo, content_type="application/pdf")
        return self.client.post(self.novo, carga)

    def test_reenvio_ignora_reprocessamento_de_parcelas_historico_e_anexos(self):
        primeiro = self.post(arquivo=b"%PDF-1.4 documento ficticio")
        repetido = self.post(arquivo=b"%PDF-1.4 documento ficticio")
        tentativa = SolicitacaoAvulsa.objects.get()
        self.assertRedirects(primeiro, f"{reverse('financeiro:titulos')}?solicitacao={tentativa.pk}")
        self.assertEqual(repetido.url, primeiro.url)

        titulos = list(TituloPagar.objects.order_by("parcela_ordem"))
        self.assertEqual([t.valor_original for t in titulos], [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual([t.vencimento for t in titulos], [date(2026, 11, 30), date(2026, 12, 30), date(2027, 1, 29)])
        for titulo in titulos:
            self.assertEqual(titulo.status, TituloPagar.Status.AGUARDANDO_APROVACAO)
            self.assertEqual(titulo.ciclo_aprovacao, 1)
            self.assertEqual(list(titulo.historico.values_list("evento", flat=True)), ["CRIADO_MANUAL"])
            anexo = titulo.anexos.get()
            with anexo.arquivo.open("rb") as arquivo:
                self.assertEqual(arquivo.read(), b"%PDF-1.4 documento ficticio")
        self.assertEqual(Notificacao.objects.filter(evento="FINANCEIRO_APROVACAO").count(), 3)

    def test_falha_apos_gravar_anexo_reverte_tentativa_arquivo_e_titulos(self):
        with patch("financeiro.services.solicitacoes_avulsas.notificar_aprovadores", side_effect=RuntimeError("falha simulada")):
            with self.assertRaisesMessage(RuntimeError, "falha simulada"):
                self.post(arquivo=b"%PDF-1.4 documento ficticio")
        self.assertFalse(TituloPagar.objects.exists())
        self.assertFalse(SolicitacaoAvulsa.objects.exists())
        self.assertFalse(any(caminho.is_file() for caminho in self.midia.rglob("*")))
        self.assertEqual(self.post(arquivo=b"%PDF-1.4 documento ficticio").status_code, 302)
        self.assertEqual(TituloPagar.objects.count(), 3)

    def test_reenvio_apos_resposta_perdida_redireciona_ao_mesmo_titulo(self):
        self.post(quantidade_parcelas=1)
        repetido = self.post(quantidade_parcelas=1)
        titulo = TituloPagar.objects.order_by("pk").first()
        detalhe = reverse("financeiro:titulo_detalhe", kwargs={"pk": titulo.pk})
        self.assertRedirects(repetido, detalhe)
        self.assertEqual(TituloPagar.objects.count(), 1)

    def test_mesma_chave_com_conteudo_ou_anexo_divergente_retorna_conflito(self):
        self.assertEqual(self.post(quantidade_parcelas=1, arquivo=b"%PDF-1.4 A").status_code, 302)
        self.assertEqual(self.post(quantidade_parcelas=1, descricao="Serviço diferente", arquivo=b"%PDF-1.4 A").status_code, 409)
        self.assertEqual(self.post(quantidade_parcelas=1, arquivo=b"%PDF-1.4 B").status_code, 409)
        self.assertEqual(TituloPagar.objects.get().anexos.count(), 1)

    def test_novas_tentativas_com_os_mesmos_dados_sao_permitidas(self):
        outro = chave_da_pagina(self.client.get(self.novo))
        primeiro = self.post(quantidade_parcelas=1)
        segundo = self.post(chave=outro, quantidade_parcelas=1)
        self.assertNotEqual(primeiro.url, segundo.url)
        self.assertEqual(TituloPagar.objects.count(), 2)

    def test_chave_de_outro_usuario_e_chave_invalida_nao_criam_titulo(self):
        self.client.force_login(criar_usuario("outro_lancador"))
        self.assertEqual(self.post(quantidade_parcelas=1).status_code, 400)
        self.assertEqual(self.post(chave="fraude", quantidade_parcelas=1).status_code, 400)
        self.assertFalse(TituloPagar.objects.exists())

    def test_reenvio_permanece_valido_apos_inativacao_de_apropriacao(self):
        criado = self.post(quantidade_parcelas=1)
        PlanoFinanceiro.objects.filter(pk=self.dados["plano_financeiro"]).update(ativo=False)
        repetido = self.post(quantidade_parcelas=1)
        self.assertEqual(repetido.url, criado.url)
        self.assertEqual(TituloPagar.objects.count(), 1)

    def test_corrigir_formulario_invalido_preserva_tentativa(self):
        invalido = self.post(quantidade_parcelas=1, vencimento="")
        self.assertEqual(invalido.status_code, 200)
        self.assertFalse(TituloPagar.objects.exists())
        self.assertEqual(chave_da_pagina(invalido), self.chave)
        self.assertEqual(self.post(quantidade_parcelas=1).status_code, 302)

    def test_fin_pula_codigo_historico_e_preserva_numero_original(self):
        ano = timezone.localdate().year
        existente = TituloPagar.objects.create(numero=f"FIN-{ano}-00001", descricao="Histórico", valor_original=Decimal("40.00"))
        self.assertEqual(self.post(quantidade_parcelas=1).status_code, 302)
        existente.refresh_from_db()
        self.assertEqual(existente.numero, f"FIN-{ano}-00001")
        self.assertTrue(TituloPagar.objects.filter(numero=f"FIN-{ano}-00002").exists())

    def test_envio_e_decisao_repetidos_preservam_titulo_ciclo_e_historico(self):
        self.post(quantidade_parcelas=1)
        titulo = TituloPagar.objects.get()
        enviar = reverse("financeiro:titulo_enviar_aprovacao", args=[titulo.pk])
        decidir = reverse("financeiro:titulo_decidir", args=[titulo.pk])
        self.client.post(enviar)
        self.client.post(decidir, {"decisao": "APROVADO"})
        self.client.post(decidir, {"decisao": "APROVADO"})
        self.client.post(enviar)
        titulo.refresh_from_db()
        self.assertEqual(titulo.status, TituloPagar.Status.APROVADO)
        self.assertEqual(titulo.ciclo_aprovacao, 1)
        self.assertEqual(list(titulo.aprovacoes.values_list("ciclo", "decisao")), [(1, "APROVADO")])
        self.assertCountEqual(titulo.historico.values_list("evento", flat=True), ["CRIADO_MANUAL", "APROVADO"])
        self.assertEqual(TituloPagar.objects.count(), 1)
        self.assertEqual(Notificacao.objects.filter(evento="FINANCEIRO_APROVACAO").count(), 1)

    def test_edicao_com_instancia_desatualizada_protege_pagamento_efetivado(self):
        self.post(quantidade_parcelas=1)
        titulo_desatualizado = TituloPagar.objects.get()
        Pagamento.objects.create(
            titulo=titulo_desatualizado, valor=Decimal("100.00"), data_pagamento=date(2026, 11, 30),
        )
        with self.assertRaisesMessage(ValueError, "Conta paga não pode ser alterada"):
            atualizar_titulo(titulo_desatualizado, usuario=self.usuario, dados={"desconto": Decimal("10.01")})
        titulo_desatualizado.refresh_from_db()
        self.assertEqual(titulo_desatualizado.valor_liquido, Decimal("100.00"))
        self.assertFalse(titulo_desatualizado.historico.filter(evento="ATUALIZADO").exists())

    def test_auditoria_de_edicao_grava_valor_e_campos_sem_expor_dados_bancarios(self):
        self.post(quantidade_parcelas=1)
        titulo = TituloPagar.objects.get()
        atualizar_titulo(titulo, usuario=self.usuario, dados={"desconto": Decimal("9.99"), "beneficiario_pix": "chave-ficticia"})
        evento = titulo.historico.get(evento="ATUALIZADO")
        self.assertEqual(evento.usuario, self.usuario)
        self.assertEqual(evento.dados["valor_liquido_anterior"], "100.00")
        self.assertEqual(evento.dados["valor_liquido_posterior"], "90.01")
        self.assertCountEqual(evento.dados["campos_criticos_alterados"], ["desconto", "beneficiario_pix"])
        self.assertNotIn("chave-ficticia", str(evento.dados))


class SolicitacaoAvulsaConcorrenciaTests(TransactionTestCase):
    def test_duplo_clique_e_dois_usuarios_com_tentativas_simultaneas(self):
        url = reverse("financeiro:titulo_novo")
        dados = {**dados_sinteticos(), "quantidade_parcelas": 1}
        primeiro = criar_usuario("financeiro_concorrente_a")
        segundo = criar_usuario("financeiro_concorrente_b")
        chaves = []
        for usuario in (primeiro, segundo):
            self.client.force_login(usuario)
            chaves.append(chave_da_pagina(self.client.get(url)))
        barreira = Barrier(3)

        def enviar(usuario, chave):
            close_old_connections()
            try:
                request = RequestFactory().post(url, {**dados, "chave_idempotencia": chave})
                request.user = usuario
                request._messages = CookieStorage(request)
                barreira.wait(timeout=5)
                resposta = titulo_novo(request)
                return resposta.status_code, resposta.get("Location")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=3) as executor:
            tarefas = [executor.submit(enviar, primeiro, chaves[0]) for _ in range(2)]
            tarefas.append(executor.submit(enviar, segundo, chaves[1]))
            a, repetido, b = (tarefa.result(timeout=15) for tarefa in tarefas)

        self.assertEqual([a[0], repetido[0], b[0]], [302, 302, 302])
        self.assertEqual(a, repetido)
        self.assertNotEqual(a, b)
        self.assertEqual(TituloPagar.objects.count(), 2)
        self.assertEqual(TituloPagar.objects.values("numero").distinct().count(), 2)
