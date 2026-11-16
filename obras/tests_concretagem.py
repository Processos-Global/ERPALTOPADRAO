"""Testes da concretagem (fase 1: locais, solicitação, envio, resposta pública, reagendamento).

Rodar com banco isolado em memória:
    manage.py test obras.tests_concretagem --settings=obras.test_settings_concretagem
"""
import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor
from obras.models import (
    Concretagem, ContatoEmailConcreteira, EnvioMensagemConcretagem, HistoricoConcretagem, LocalUsoObra, Obra,
)
from obras.services.concretagem import fluxo
from usuarios.models import Notificacao, PermissaoAcao, PermissaoModulo

User = get_user_model()
S = Concretagem.Status


class BaseConcretagem(TestCase):
    @classmethod
    def setUpTestData(cls):
        assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
        cls.leitor = cls._usuario("leitor")
        # Permissão única "Concretagem": eng e gerente têm os mesmos poderes.
        cls.eng = cls._usuario("eng", acoes=["concretagem"])
        cls.gerente = cls._usuario("gerente", acoes=["concretagem"])
        cls.obra = Obra.objects.create(nome="Residencial Teste", codigo="OBRA-T1")
        cls.outra_obra = Obra.objects.create(nome="Outra Obra", codigo="OBRA-T2")
        cls.forn = Fornecedor.objects.create(nome="Concreteira Alfa LTDA", email="vendas@alfa.test")
        cls.laje = LocalUsoObra.objects.create(obra=cls.obra, nome="Laje 2º pavimento", tipo="LAJE")
        cls.piscina = LocalUsoObra.objects.create(obra=cls.obra, nome="Piscina", tipo="PISCINA")
        cls.local_outra = LocalUsoObra.objects.create(obra=cls.outra_obra, nome="Muro", tipo="MURO")

    @staticmethod
    def _usuario(nome, acoes=()):
        u = User.objects.create_user(username=nome, password="x", email=f"{nome}@test.local")
        PermissaoModulo.objects.create(usuario=u, modulo="OBRAS", nivel="EDICAO", ativo=True)
        for acao in acoes:
            PermissaoAcao.objects.create(usuario=u, modulo="OBRAS", acao=acao, permitido=True)
        return u

    def _post_nova(self, **extra):
        dados = {
            "obra": self.obra.pk, "concreteira": self.forn.pk, "engenheiro": self.eng.pk,
            "data_programada": "2026-12-01", "horario_programado": "07:30",
            "fck_projeto": "30", "volume_solicitado": "18.5", "slump": "10±2",
            "item_local": [str(self.laje.pk), str(self.piscina.pk)], "item_descricao": ["", "Pilares P1-P8"],
            "item_volume": ["15", "3,5"],
        }
        dados.update(extra)
        return self.client.post(reverse("obras:concretagem_nova"), dados)

    def _criar(self, usuario=None, **campos):
        base = dict(
            obra=self.obra, concreteira=self.forn, engenheiro=self.eng, data_programada=datetime.date(2026, 12, 1),
            horario_programado=datetime.time(7, 30), fck_projeto=Decimal("30"), volume_solicitado=Decimal("10"),
        )
        base.update(campos)
        return fluxo.criar_concretagem(
            Concretagem(**base), [{"local": self.laje, "descricao": "", "volume_previsto": Decimal("10")}],
            usuario or self.eng,
        )


class PermissoesTests(BaseConcretagem):
    def test_leitor_ve_painel_mas_nao_cria(self):
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.get(reverse("obras:concretagem_painel")).status_code, 200)
        self.assertEqual(self.client.get(reverse("obras:concretagem_nova")).status_code, 403)
        self.assertEqual(self._post_nova().status_code, 403)
        self.assertFalse(Concretagem.objects.exists())

    def test_so_quem_tem_concretagem_aceita_manualmente(self):
        conc = self._criar()
        fluxo.solicitar(conc, self.eng)
        self.client.force_login(self.leitor)  # só acesso ao módulo Obras
        resp = self.client.post(reverse("obras:concretagem_aceitar_manual", args=[conc.pk]))
        self.assertEqual(resp.status_code, 403)
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.SOLICITADA)

    def test_permissao_unica_no_cadastro_de_usuarios(self):
        from usuarios.services.registro_permissoes import ACOES_MODULO

        codigos = [c for c, _ in ACOES_MODULO["OBRAS"]]
        self.assertIn("concretagem", codigos)
        self.assertNotIn("preencher_concretagem", codigos)
        self.assertNotIn("gerente_concretagem", codigos)

    def test_gerente_aceita_manualmente(self):
        conc = self._criar()
        fluxo.solicitar(conc, self.eng)
        self.client.force_login(self.gerente)
        self.client.post(reverse("obras:concretagem_aceitar_manual", args=[conc.pk]), {"observacao": "por telefone"})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.CONFIRMADA)
        self.assertEqual(conc.confirmacao_cliente, "ACEITO")
        self.assertEqual(conc.aceite_manual_por, self.gerente)

    def test_paginas_renderizam(self):
        conc = self._criar()
        self.client.force_login(self.gerente)
        for nome, args in [
            ("concretagem_painel", []), ("concretagem_obra", [self.obra.pk]),
            ("concretagem_locais", [self.obra.pk]), ("concretagem_nova", []),
            ("concretagem_detalhe", [conc.pk]), ("concretagem_editar", [conc.pk]),
        ]:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(f"obras:{nome}", args=args)).status_code, 200)


class DetalheEstadosTests(BaseConcretagem):
    def _render(self, conc, usuario):
        self.client.force_login(usuario)
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[conc.pk]))
        self.assertEqual(resp.status_code, 200)
        return resp

    def test_detalhe_em_cada_situacao(self):
        solicitada = fluxo.solicitar(self._criar(), self.eng)
        resp = self._render(solicitada, self.gerente)
        self.assertContains(resp, "Aceitar manualmente")
        self.assertContains(resp, "Abrir no WhatsApp")
        resp = self._render(solicitada, self.eng)
        self.assertContains(resp, "Aceitar manualmente")  # permissão única: todos aceitam
        self.assertNotContains(self._render(solicitada, self.leitor), "Aceitar manualmente")

        reag = fluxo.pedir_reagendamento(
            fluxo.solicitar(self._criar(), self.eng), datetime.date(2026, 12, 9), None, "Ana",
        )
        self.assertContains(self._render(reag, self.eng), "Aceitar data sugerida")

        confirmada = fluxo.aceitar(fluxo.solicitar(self._criar(), self.eng), self.gerente)
        self.assertContains(self._render(confirmada, self.eng), "Concretagem confirmada")

        cancelada = fluxo.cancelar(self._criar(), self.eng, "Chuva forte")
        self.assertContains(self._render(cancelada, self.leitor), "Chuva forte")


class SolicitacaoTests(BaseConcretagem):
    def test_cria_rascunho_com_codigo_e_itens(self):
        self.client.force_login(self.eng)
        resp = self._post_nova()
        conc = Concretagem.objects.get()
        self.assertRedirects(resp, reverse("obras:concretagem_detalhe", args=[conc.pk]))
        self.assertRegex(conc.codigo, r"^CONC-\d{4}-0001$")
        self.assertEqual(conc.status, S.RASCUNHO)
        itens = list(conc.itens_planejados.all())
        self.assertEqual([i.local_id for i in itens], [self.laje.pk, self.piscina.pk])
        self.assertEqual(itens[1].volume_previsto, Decimal("3.50"))
        self.assertTrue(conc.historicos.filter(acao="CRIACAO").exists())

    def test_codigo_sequencial(self):
        a, b = self._criar(), self._criar()
        self.assertEqual(int(b.codigo[-4:]), int(a.codigo[-4:]) + 1)

    def test_rejeita_local_de_outra_obra(self):
        self.client.force_login(self.eng)
        resp = self._post_nova(item_local=[str(self.local_outra.pk)], item_descricao=[""], item_volume=["5"])
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Concretagem.objects.exists())

    def test_rejeita_volume_invalido(self):
        self.client.force_login(self.eng)
        self._post_nova(item_local=[str(self.laje.pk)], item_descricao=[""], item_volume=["0"])
        self.assertFalse(Concretagem.objects.exists())

    def test_nao_libera_sem_dados_essenciais(self):
        conc = self._criar(fck_projeto=None, concreteira=None)
        with self.assertRaises(fluxo.FluxoError):
            fluxo.solicitar(conc, self.eng)
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.RASCUNHO)

    def test_liberar_notifica_gerente(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_solicitar", args=[conc.pk]))
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.SOLICITADA)
        self.assertIsNotNone(conc.solicitada_em)
        self.assertTrue(Notificacao.objects.filter(usuario=self.gerente, evento="concretagem.solicitada").exists())
        self.assertFalse(conc.drive_pasta_id)  # Drive desligado nos testes

    def test_editar_so_em_rascunho(self):
        conc = self._criar()
        fluxo.solicitar(conc, self.eng)
        self.client.force_login(self.eng)
        resp = self.client.get(reverse("obras:concretagem_editar", args=[conc.pk]))
        self.assertRedirects(resp, reverse("obras:concretagem_detalhe", args=[conc.pk]))

    def test_mensagem_contem_link_publico_e_itens(self):
        conc = self._criar()
        from obras.services.concretagem.mensagem import gerar_texto
        texto = gerar_texto(conc)
        self.assertIn(str(conc.token_confirmacao), texto)
        self.assertIn("LAJE 2º PAVIMENTO", texto)
        self.assertIn("FCK: 30 MPA", texto)

    def test_envio_email_registra_e_salva_contato(self):
        conc = self._criar()
        fluxo.solicitar(conc, self.eng)
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_enviar_email", args=[conc.pk]), {
            "emails": ["vendas@alfa.test"], "emails_extras": "prog@alfa.test", "salvar_extras": "1",
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].to), {"vendas@alfa.test", "prog@alfa.test"})
        self.assertTrue(EnvioMensagemConcretagem.objects.filter(concretagem=conc, canal="EMAIL").exists())
        self.assertTrue(ContatoEmailConcreteira.objects.filter(fornecedor=self.forn, email="prog@alfa.test").exists())

    def test_email_invalido_nao_envia(self):
        conc = self._criar()
        fluxo.solicitar(conc, self.eng)
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_enviar_email", args=[conc.pk]), {"emails_extras": "nao-e-email"})
        self.assertEqual(len(mail.outbox), 0)

    def test_cancelar_exige_motivo(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_cancelar", args=[conc.pk]), {"motivo": ""})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.RASCUNHO)
        self.client.post(reverse("obras:concretagem_cancelar", args=[conc.pk]), {"motivo": "Chuva"})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.CANCELADA)

    def test_encerrada_nao_edita_e_nao_cancela_depois_de_executada(self):
        conc = self._criar()
        fluxo.cancelar(conc, self.eng, "teste")
        self.client.force_login(self.eng)
        resp = self.client.get(reverse("obras:concretagem_editar", args=[conc.pk]))
        self.assertRedirects(resp, reverse("obras:concretagem_detalhe", args=[conc.pk]), fetch_redirect_response=False)
        html = self.client.get(reverse("obras:concretagem_detalhe", args=[conc.pk])).content.decode()
        self.assertNotIn(">Editar</a>", html)
        self.assertIn("← Obra", html)
        executada = self._criar()
        Concretagem.objects.filter(pk=executada.pk).update(status=S.EXECUTADA)
        executada.refresh_from_db()
        with self.assertRaises(fluxo.FluxoError):
            fluxo.cancelar(executada, self.eng, "tarde demais")
        self.assertNotIn('data-cc-open="modal-cancelar"', self.client.get(reverse("obras:concretagem_detalhe", args=[executada.pk])).content.decode())


class PublicaTests(BaseConcretagem):
    def setUp(self):
        self.conc = fluxo.solicitar(self._criar(), self.eng)
        self.url = reverse("obras:concretagem_publica", args=[self.conc.token_confirmacao])

    def test_get_nao_altera_e_nao_exige_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.SOLICITADA)
        self.assertEqual(self.conc.confirmacao_cliente, "")

    def test_aceitar_confirma_e_notifica_e_resposta_unica(self):
        self.client.post(self.url, {"acao": "aceitar"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)
        self.assertIsNone(self.conc.aceite_manual_por)
        self.assertTrue(Notificacao.objects.filter(usuario=self.eng, evento="concretagem.resposta").exists())
        resp = self.client.post(self.url, {"acao": "recusar"})
        self.assertContains(resp, "já foi confirmada")
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)

    def test_recusar_cancela(self):
        self.client.post(self.url, {"acao": "recusar", "observacao": "sem caminhão"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CANCELADA)
        self.assertIn("sem caminhão", self.conc.motivo_cancelamento)

    def test_reagendamento_mantem_status_e_reabre_com_data_sugerida(self):
        self.client.post(self.url, {"acao": "reagendar", "data": "2026-12-03", "horario": "08:00", "solicitante": "Ana"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.SOLICITADA)
        self.assertTrue(self.conc.pediu_reagendamento)
        token_antigo = self.conc.token_confirmacao
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_reagendar", args=[self.conc.pk]), {
            "data": "2026-12-03", "horario": "08:00",
        })
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.RASCUNHO)
        self.assertEqual(self.conc.data_programada, datetime.date(2026, 12, 3))
        self.assertEqual(self.conc.confirmacao_cliente, "")
        self.assertNotEqual(self.conc.token_confirmacao, token_antigo)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_reagendamento_sem_data_falha(self):
        resp = self.client.post(self.url, {"acao": "reagendar", "data": ""})
        self.assertContains(resp, "Informe a data sugerida")
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.confirmacao_cliente, "")


class ReagendarTests(BaseConcretagem):
    def test_engenheiro_reagenda_confirmada_mantendo_data(self):
        conc = fluxo.aceitar(fluxo.solicitar(self._criar(), self.eng), self.gerente)
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_reagendar", args=[conc.pk]), {"data": "", "horario": ""})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.RASCUNHO)
        self.assertEqual(conc.data_programada, datetime.date(2026, 12, 1))
        self.assertTrue(HistoricoConcretagem.objects.filter(concretagem=conc, acao="REAGENDAMENTO").exists())

    def test_nao_reagenda_rascunho(self):
        conc = self._criar()
        with self.assertRaises(fluxo.FluxoError):
            fluxo.reagendar(conc, self.eng)


class RegrasAjustadasTests(BaseConcretagem):
    """Concreteira obrigatória, bombista depois, mensagem só após liberar, e-mails."""

    def test_concreteira_obrigatoria(self):
        self.client.force_login(self.eng)
        resp = self._post_nova(concreteira="")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Concretagem.objects.exists())

    def test_form_ignora_bombista(self):
        self.client.force_login(self.eng)
        self._post_nova(com_bomba="on", nome_bombista="Zé")
        conc = Concretagem.objects.get()
        self.assertTrue(conc.com_bomba)
        self.assertEqual(conc.nome_bombista, "")

    def test_rascunho_nao_expoe_mensagem_nem_link(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[conc.pk]))
        self.assertNotContains(resp, str(conc.token_confirmacao))
        self.assertNotContains(resp, "CONCRETAGEM RESIDENCIAL TESTE")
        self.assertNotContains(resp, "Abrir no WhatsApp")
        fluxo.solicitar(conc, self.eng)
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[conc.pk]))
        self.assertContains(resp, str(conc.token_confirmacao))

    def test_liberar_ja_envia_email(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_solicitar", args=[conc.pk]), {"emails": ["vendas@alfa.test"]})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.SOLICITADA)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["vendas@alfa.test"])
        self.assertIn(str(conc.token_confirmacao), mail.outbox[0].body)
        self.assertTrue(EnvioMensagemConcretagem.objects.filter(concretagem=conc, canal="EMAIL").exists())

    def test_liberar_sem_email(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_solicitar", args=[conc.pk]))
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.SOLICITADA)
        self.assertEqual(len(mail.outbox), 0)

    def test_liberar_com_email_invalido_nao_libera(self):
        conc = self._criar()
        self.client.force_login(self.eng)
        self.client.post(reverse("obras:concretagem_solicitar", args=[conc.pk]), {"emails_extras": "xx"})
        conc.refresh_from_db()
        self.assertEqual(conc.status, S.RASCUNHO)

    def test_aceite_pelo_link_envia_email_ao_engenheiro(self):
        conc = fluxo.solicitar(self._criar(), self.eng)
        self.client.post(reverse("obras:concretagem_publica", args=[conc.token_confirmacao]), {"acao": "aceitar"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["eng@test.local"])
        self.assertIn("aceita", mail.outbox[0].subject.lower())

    def test_recusa_nao_envia_email_de_aceite(self):
        conc = fluxo.solicitar(self._criar(), self.eng)
        self.client.post(reverse("obras:concretagem_publica", args=[conc.token_confirmacao]), {"acao": "recusar"})
        self.assertEqual(len(mail.outbox), 0)

    def test_bombista_depois_de_liberar(self):
        conc = self._criar(com_bomba=True)
        self.client.force_login(self.eng)
        url = reverse("obras:concretagem_bombista", args=[conc.pk])
        self.client.post(url, {"nome_bombista": "Zé"})
        conc.refresh_from_db()
        self.assertEqual(conc.nome_bombista, "")  # rascunho: ainda não
        fluxo.solicitar(conc, self.eng)
        self.client.post(url, {"nome_bombista": "Zé da Bomba"})
        conc.refresh_from_db()
        self.assertEqual(conc.nome_bombista, "Zé da Bomba")


class LocaisTests(BaseConcretagem):
    def test_cria_local_por_ajax_e_bloqueia_duplicado(self):
        self.client.force_login(self.eng)
        url = reverse("obras:concretagem_local_criar", args=[self.obra.pk])
        ajax = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}
        resp = self.client.post(url, {"nome": "Reservatório", "tipo": "RESERVATORIO", "ordem": 3}, **ajax)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        resp = self.client.post(url, {"nome": "piscina", "tipo": "PISCINA", "ordem": 0}, **ajax)
        self.assertEqual(resp.status_code, 400)

    def test_leitor_nao_cria_local(self):
        self.client.force_login(self.leitor)
        resp = self.client.post(reverse("obras:concretagem_local_criar", args=[self.obra.pk]), {"nome": "X", "tipo": "OUTRO", "ordem": 0})
        self.assertEqual(resp.status_code, 403)

    def test_api_lista_so_ativos_da_obra(self):
        self.piscina.ativo = False
        self.piscina.save()
        self.client.force_login(self.leitor)
        dados = self.client.get(reverse("obras:concretagem_api_locais", args=[self.obra.pk])).json()
        self.assertEqual([l["nome"] for l in dados["locais"]], ["Laje 2º pavimento"])
