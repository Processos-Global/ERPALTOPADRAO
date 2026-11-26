from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from pos_obra.models import Cliente
from usuarios.context_processors import erp_layout
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoFinanceiro, PermissaoModulo


class NavegacaoERPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operador-redesign")
        self.factory = RequestFactory()

    def layout(self, route, args=None):
        path = reverse(route, args=args)
        request = self.factory.get(path)
        request.user = self.user
        request.session = {}
        request.resolver_match = resolve(path)
        return erp_layout(request)

    def routes(self, context):
        return [
            entry["route"]
            for group in context["erp_nav_groups"]
            for entry in group["entries"]
        ]

    def test_operador_sem_modulos_nao_recebe_rotas_internas(self):
        self.assertEqual(self.routes(self.layout("core:index")), [])

    def test_financeiro_reutiliza_acoes_granulares(self):
        PermissaoModulo.objects.create(
            usuario=self.user, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.EDICAO, ativo=True,
        )
        granular = PermissaoFinanceiro.objects.create(usuario=self.user, ativo=True, visualizar=True, lancar_titulos=False)
        visible = self.routes(self.layout("core:index"))
        self.assertIn("financeiro:titulos", visible)
        self.assertNotIn("financeiro:titulo_novo", visible)
        granular.visualizar = False
        granular.lancar_titulos = True
        granular.save()
        self.user.refresh_from_db()
        visible = self.routes(self.layout("core:index"))
        self.assertIn("financeiro:titulo_novo", visible)
        self.assertNotIn("financeiro:titulos", visible)

    def test_rota_de_detalhe_destaca_lista_pai_sem_registrar_url_do_objeto(self):
        self.user.is_superuser = True
        context = self.layout("financeiro:titulo_detalhe", [47])
        self.assertEqual(context["erp_nav_branch"]["route"], "financeiro:titulos")
        self.assertFalse(context["erp_nav_branch"]["current"])
        self.assertNotIn("financeiro:titulo_detalhe", self.routes(context))
        routes = self.routes(context)
        self.assertEqual(len(routes), len(set(routes)))

    def test_planejamento_aparece_com_suprimentos_sem_expor_cronograma_fisico(self):
        PermissaoModulo.objects.create(
            usuario=self.user, modulo=ModuloSistema.SUPRIMENTOS, nivel=NivelPermissao.LEITURA, ativo=True,
        )
        visible = self.routes(self.layout("core:index"))
        self.assertIn("planejamento:painel_cronograma_suprimentos", visible)
        self.assertNotIn("planejamento:painel_cronograma", visible)

    def test_cargo_de_pos_obra_sem_acao_de_visualizacao_nao_recebe_rota_interna(self):
        self.user.perfil_erp.cargo = "POS_OBRA"
        self.user.perfil_erp.save()
        PermissaoModulo.objects.create(usuario=self.user, modulo=ModuloSistema.POS_OBRA)
        self.assertNotIn("pos_obra:painel", self.routes(self.layout("core:index")))

    def test_conta_de_cliente_nao_renderiza_rotas_internas_na_busca(self):
        Cliente.objects.create(nome="Cliente sintético", usuario=self.user, portal_habilitado=True)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, 'data-nav-link="pos_obra:portal"')
        self.assertNotContains(response, 'data-nav-link="pos_obra:painel"')
        self.assertNotContains(response, 'data-nav-link="financeiro:titulos"')
        self.assertNotContains(response, "data-notification-center")
