from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from obras.models import MovimentoEstoque, Obra
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class RelatorioTransferenciasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.origem = Obra.objects.create(codigo="OB-RELT-1", nome="=1+1")
        destino = Obra.objects.create(codigo="OB-RELT-2", nome="Destino sintético")
        cls.movimento = MovimentoEstoque.objects.create(
            tipo=MovimentoEstoque.Tipo.TRANSFERENCIA, obra_origem=cls.origem, obra_destino=destino,
            descricao_item="=2+2", unidade="UN", quantidade=2, custo_unitario_transferencia=10,
            observacao="=3+3",
        )
        cls.leitor = get_user_model().objects.create_user("transferencias-leitor")
        cls.editor = get_user_model().objects.create_user("transferencias-editor")
        for usuario, nivel in ((cls.leitor, NivelPermissao.LEITURA), (cls.editor, NivelPermissao.EDICAO)):
            PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.OBRAS, nivel=nivel)

    def setUp(self):
        self.url = reverse("obras:relatorio_transferencias", args=[self.origem.pk])
        self.campo = f"depreciacao_{self.movimento.pk}"

    def test_reserva_escrita_de_depreciacao_a_edicao_e_preserva_download_registrado(self):
        self.client.force_login(self.leitor)
        pagina = self.client.get(self.url)
        self.assertNotContains(pagina, f'name="{self.campo}"')
        self.assertEqual(self.client.post(self.url, {self.campo: "10"}).status_code, 403)
        self.movimento.refresh_from_db()
        self.assertIsNone(self.movimento.depreciacao_percentual)

        self.client.force_login(self.editor)
        self.assertContains(self.client.get(self.url), "data-download")
        self.assertEqual(self.client.post(self.url, {self.campo: "10"}).status_code, 200)
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(self.url).status_code, 200)
        self.movimento.refresh_from_db()
        self.assertEqual(self.movimento.depreciacao_percentual, Decimal("10"))

    def test_excel_preserva_textos_e_o_valor_ressarcido(self):
        self.client.force_login(self.editor)
        resposta = self.client.post(self.url, {self.campo: "10"})

        self.assertEqual(resposta.status_code, 200)
        planilha = load_workbook(BytesIO(resposta.content), read_only=True)
        self.addCleanup(planilha.close)
        for endereco, valor in (("B2", "=1+1"), ("E4", "=2+2"), ("M4", "=3+3")):
            celula = planilha.active[endereco]
            self.assertEqual(celula.value, valor)
            self.assertEqual(celula.data_type, "s")
        self.assertEqual(planilha.active["K4"].value, 18)
        self.assertEqual(planilha.active["K5"].value, 18)
