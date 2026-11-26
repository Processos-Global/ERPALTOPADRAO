from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import CategoriaOcorrencia, Cliente, EmpreendimentoPosObra, TipoProblema
from pos_obra.models import Chamado


class RetornoOrdemServicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser("navegacao_os")
        categoria = CategoriaOcorrencia.objects.create(nome="Acabamento")
        tipo = TipoProblema.objects.create(categoria=categoria, nome="Revestimento")
        obra = EmpreendimentoPosObra.objects.create(
            historica=True, liberada=True, nome_historico="Residencial teste",
        )
        cls.chamado = Chamado.objects.create(
            cliente=Cliente.objects.create(nome="Cliente sintético"), empreendimento=obra,
            tipo_problema=tipo, descricao="Descrição de teste",
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.detalhe = reverse("pos_obra:detalhe", args=[self.chamado.pk])
        self.ancora = f"#chamado-{self.chamado.pk}"

    def test_lista_retorna_aos_filtros_e_a_ordem_de_servico(self):
        origem = reverse("pos_obra:lista", query={"q": "sintético", "ordem": "antigas", "page": 1})
        destino = reverse("pos_obra:detalhe", args=[self.chamado.pk], query={"retorno": origem})
        self.assertContains(self.client.get(origem), f'href="{destino}"')
        self.assertContains(
            self.client.get(destino), f'href="{origem.replace("&", "&amp;")}{self.ancora}"',
        )

    def test_quadro_retorna_ao_quadro_filtrado(self):
        origem = reverse("pos_obra:kanban", query={"q": "sintético"})
        destino = reverse("pos_obra:detalhe", args=[self.chamado.pk], query={"retorno": origem})
        self.assertContains(self.client.get(origem), f'href="{destino}"')
        self.assertContains(self.client.get(destino), f'href="{origem}{self.ancora}"')

    def test_retorno_nao_aceita_dominios_ou_rotas_fora_da_lista(self):
        for origem in ("https://example.com/", reverse("pos_obra:painel")):
            with self.subTest(origem=origem):
                resposta = self.client.get(self.detalhe, {"retorno": origem})
                esperado = reverse("pos_obra:lista") + self.ancora
                self.assertContains(resposta, f'href="{esperado}"')
