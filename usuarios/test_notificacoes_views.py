from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from usuarios.models import Notificacao


class NotificacoesViewsTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("destinatario")
        self.notificacao = Notificacao.objects.create(
            usuario=self.usuario, titulo="Notificação sintética", mensagem="Pendência interna",
            url=reverse("core:index"),
        )
        self.url = reverse("usuarios:abrir_notificacao", args=[self.notificacao.pk])
        self.lista = reverse("usuarios:notificacoes")
        self.cliente = Client(enforce_csrf_checks=True)
        self.cliente.force_login(self.usuario)

    def test_leitura_so_muda_por_post_com_csrf(self):
        self.assertRedirects(self.cliente.get(self.url), self.notificacao.url, fetch_redirect_response=False)
        self.assertEqual(self.cliente.post(self.url).status_code, 403)
        self.notificacao.refresh_from_db()
        self.assertFalse(self.notificacao.lida)

        self.assertContains(self.cliente.get(self.lista), f'action="{self.url}"')
        token = self.cliente.cookies["csrftoken"].value
        resposta = self.cliente.post(self.url, {"csrfmiddlewaretoken": token})
        self.assertRedirects(resposta, self.notificacao.url, fetch_redirect_response=False)
        self.notificacao.refresh_from_db()
        self.assertTrue(self.notificacao.lida)

    def test_destino_precisa_ser_do_proprio_site(self):
        self.notificacao.url = "//exemplo.invalid/notificacao"
        self.notificacao.save(update_fields=["url"])
        self.assertRedirects(self.cliente.get(self.url), self.lista, fetch_redirect_response=False)

    def test_notificacao_de_outro_usuario_nao_pode_ser_aberta(self):
        self.cliente = Client()
        self.cliente.force_login(get_user_model().objects.create_user("outro-usuario"))
        self.assertEqual(self.cliente.post(self.url).status_code, 404)
        self.notificacao.refresh_from_db()
        self.assertFalse(self.notificacao.lida)
