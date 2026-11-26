from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.urls import reverse

from financeiro.models import PlanoFinanceiro, TituloPagar
from financeiro.services.aprovacoes import enviar_para_aprovacao
from financeiro.services.permissoes import possui_acao_financeiro
from usuarios.models import ModuloSistema, NivelPermissao, Notificacao, PermissaoFinanceiro, PermissaoModulo


class NotificacoesAprovacaoFinanceiraTests(TestCase):
    """Usuários, permissões e contas sintéticos para o fluxo de aprovação."""

    @classmethod
    def setUpTestData(cls):
        cls.raiz = get_user_model().objects.create_superuser(username="super_fin")
        plano = PlanoFinanceiro.objects.create(codigo="10", nome="Apropriação sintética")
        cls.titulo = TituloPagar.objects.create(
            numero="FIN-NOTIFICACAO", descricao="Serviço sintético", beneficiario_nome="Beneficiário sintético",
            especificacao_pagamento="Manutenção", plano_financeiro=plano, vencimento=date(2026, 11, 30),
            valor_original=Decimal("100.00"),
        )

    def usuario_com_permissao(self, nome, nivel=None, *, modulo_ativo=True, ativo=True, granular=None):
        usuario = get_user_model().objects.create_user(username=nome, is_active=ativo)
        if nivel:
            PermissaoModulo.objects.create(
                usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=nivel, ativo=modulo_ativo,
            )
        if granular is not None:
            PermissaoFinanceiro.objects.create(usuario=usuario, **granular)
        return usuario

    def test_envio_notifica_apenas_usuarios_com_acao_aprovar(self):
        permitido = [
            self.raiz,
            self.usuario_com_permissao("legado", NivelPermissao.APROVACAO),
            self.usuario_com_permissao(
                "legado_granular_inativo", NivelPermissao.ADMINISTRADOR, granular={"ativo": False},
            ),
            self.usuario_com_permissao(
                "aprova", NivelPermissao.LEITURA, granular={"aprovar_pagamentos": True},
            ),
            self.usuario_com_permissao(
                "administra", NivelPermissao.LEITURA, granular={"administrar": True},
            ),
        ]
        negado = [
            self.usuario_com_permissao(
                "negado_aprovacao", NivelPermissao.APROVACAO, granular={"aprovar_pagamentos": False},
            ),
            self.usuario_com_permissao(
                "negado_admin", NivelPermissao.ADMINISTRADOR, granular={"administrar": False},
            ),
            self.usuario_com_permissao("somente_leitura", NivelPermissao.LEITURA),
            self.usuario_com_permissao("sem_modulo", granular={"aprovar_pagamentos": True}),
            self.usuario_com_permissao(
                "modulo_inativo", NivelPermissao.APROVACAO, modulo_ativo=False, granular={"administrar": True},
            ),
            self.usuario_com_permissao("usuario_inativo", NivelPermissao.APROVACAO, ativo=False),
        ]
        for usuario in permitido + negado:
            with self.subTest(usuario=usuario.username):
                self.assertEqual(possui_acao_financeiro(usuario, "APROVAR"), usuario in permitido)

        with self.captureOnCommitCallbacks() as callbacks:
            enviar_para_aprovacao(self.titulo, usuario=self.raiz)
            enviar_para_aprovacao(self.titulo, usuario=self.raiz)

        notificacoes = Notificacao.objects.filter(evento="FINANCEIRO_APROVACAO")
        self.assertCountEqual(notificacoes.values_list("usuario_id", flat=True), [u.pk for u in permitido])
        url_titulo = reverse("financeiro:titulo_detalhe", args=[self.titulo.pk])
        for notificacao in notificacoes:
            self.assertEqual(notificacao.url, url_titulo)
            self.assertEqual(notificacao.dados, {"titulo_id": self.titulo.pk})
            self.assertIn(":ciclo:1:", notificacao.chave_unica)
        self.assertEqual(callbacks, [])

    def test_rollback_descarta_notificacao_titulo_e_historico(self):
        with self.assertRaisesMessage(RuntimeError, "interrupção sintética"):
            with transaction.atomic():
                enviar_para_aprovacao(self.titulo, usuario=self.raiz)
                self.assertTrue(Notificacao.objects.filter(evento="FINANCEIRO_APROVACAO").exists())
                raise RuntimeError("interrupção sintética")

        self.titulo.refresh_from_db()
        self.assertEqual((self.titulo.status, self.titulo.ciclo_aprovacao), (TituloPagar.Status.PREVISTA, 0))
        self.assertFalse(self.titulo.historico.exists())
        self.assertFalse(Notificacao.objects.filter(evento="FINANCEIRO_APROVACAO").exists())
