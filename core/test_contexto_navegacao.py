from urllib.parse import parse_qs, urlsplit

from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils.html import escape


class RetornoListagemTests(SimpleTestCase):
    def setUp(self):
        self.lista = reverse("financeiro:titulos")
        self.agenda = reverse("financeiro:agenda")
        self.detalhe = reverse("financeiro:titulo_detalhe", args=[1])
        self.factory = RequestFactory()

    def renderizar_retorno(self, destino):
        request = self.factory.get(self.detalhe, {"retorno": destino})
        template = Template(
            "{% load saari_contexto %}"
            "{% retorno_listagem request 'financeiro:titulos' 'financeiro:agenda' as voltar_url %}"
            "{{ voltar_url }}"
        )
        return template.render(Context({"request": request}))

    def test_recupera_pesquisa_periodo_e_pagina_de_uma_lista_conhecida(self):
        destino = f"{self.agenda}?obra=3&q=Funda%C3%A7%C3%A3o&status=A&status=B&page=2"
        self.assertEqual(self.renderizar_retorno(destino), escape(destino))

    def test_fallback_para_destinos_externos_e_rotas_fora_do_fluxo(self):
        for destino in (
            "",
            f"https://example.com{self.lista}?page=2",
            f"//example.com{self.lista}?page=2",
            f"/{self.lista}?page=2",
            f"{self.lista}externo/",
            reverse("financeiro:pagamentos"),
        ):
            with self.subTest(destino=destino):
                self.assertEqual(self.renderizar_retorno(destino), self.lista)

    def test_preserva_valores_codificados_e_descarta_retorno_aninhado(self):
        destino = f"{self.lista}?q=%3Cx%3E+%26+%23&retorno=https%3A%2F%2Fexample.com"
        resultado = urlsplit(self.renderizar_retorno(destino))
        self.assertEqual(resultado.path, self.lista)
        self.assertEqual(parse_qs(resultado.query), {"q": ["<x> & #"]})

    def test_descarta_fragmento_recebido(self):
        self.assertEqual(self.renderizar_retorno(f"{self.lista}?page=2#outro-painel"), f"{self.lista}?page=2")
