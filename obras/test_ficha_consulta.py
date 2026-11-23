from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook
from pypdf import PdfReader

from cadastros.models import (
    CaracteristicaAmbiente, CategoriaGrandeFornecedor, Material,
    TipoAmbiente, TipoItemGrandeFornecedor, UnidadeMedida,
)
from compras.models import ProcessoCompra
from compras.services.grandes_fornecedores import sincronizar_itens_ficha_tecnica
from obras.models import (
    AmbienteFichaTecnica, CategoriaFichaTecnica, FichaTecnicaObra,
    ItemFichaTecnica, Obra, PavimentoFichaTecnica,
)


class FichaConsultaIntegracaoTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="ficha-admin", email="ficha@example.test", password="senha-teste"
        )
        self.client.force_login(self.usuario)
        self.obra = Obra.objects.create(nome="Obra Ficha", codigo="FIC-1")
        self.ficha = FichaTecnicaObra.objects.create(obra=self.obra)
        self.pavimento = PavimentoFichaTecnica.objects.create(ficha=self.ficha, nome="Térreo")
        caracteristica = CaracteristicaAmbiente.objects.create(codigo="SECA", nome="Área seca")
        tipo_ambiente = TipoAmbiente.objects.create(nome="Cozinha", caracteristica_padrao=caracteristica)
        self.ambiente = AmbienteFichaTecnica.objects.create(
            pavimento=self.pavimento, tipo_ambiente=tipo_ambiente,
            identificacao="Cozinha 1", caracteristica=caracteristica, area_m2=Decimal("12.00"),
        )
        self.categoria = CategoriaGrandeFornecedor.objects.create(nome="Mármores")
        self.aplicacao = CategoriaFichaTecnica.objects.create(
            ficha=self.ficha, categoria=self.categoria, ambiente=self.ambiente,
        )
        self.unidade = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        self.material = Material.objects.create(nome="Granito São Gabriel", unidade=self.unidade)
        self.tipo = TipoItemGrandeFornecedor.objects.create(
            categoria=self.categoria, nome="Bancada", unidade_padrao=self.unidade,
        )
        self.tipo.tipos_ambiente_sugeridos.add(tipo_ambiente)
        self.item = ItemFichaTecnica.objects.create(
            aplicacao_categoria=self.aplicacao, tipo_item=self.tipo,
            quantidade=Decimal("1.00"), unidade=self.unidade,
            descricao_medidas="2,40 × 0,60 m", especificacao="Acabamento polido",
            material=self.material,
        )

    def test_detalhamento_oferece_atalho_da_consulta_filtrado_pela_obra(self):
        url = reverse("obras:ficha_tecnica", args=[self.obra.pk])
        response = self.client.get(url, {"etapa": "4"})
        consulta = reverse("obras:ficha_tecnica_consulta")
        self.assertContains(
            response,
            f'<a class="ft-btn" href="{consulta}?obra={self.obra.pk}">Consulta e relatórios</a>',
            html=True,
        )

    def test_consulta_e_exportacoes_usam_filtro_material(self):
        filtros = f"?obra={self.obra.pk}&material={self.material.pk}"
        pagina = self.client.get(reverse("obras:ficha_tecnica_consulta") + filtros)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Cozinha 1")
        self.assertContains(pagina, "2,40 × 0,60 m")
        self.assertEqual(pagina.context["total"], 1)

        outro = Material.objects.create(nome="Mármore Branco", unidade=self.unidade)
        vazia = self.client.get(reverse("obras:ficha_tecnica_consulta") + f"?material={outro.pk}")
        self.assertEqual(vazia.context["total"], 0)

        excel = self.client.get(reverse("obras:ficha_tecnica_consulta_excel") + filtros)
        self.assertEqual(excel.status_code, 200)
        linhas = list(load_workbook(BytesIO(excel.content), read_only=True).active.values)
        self.assertTrue(any("2,40 × 0,60 m" in linha for linha in linhas))

        pdf = self.client.get(reverse("obras:ficha_tecnica_consulta_pdf") + filtros)
        self.assertEqual(pdf.status_code, 200)
        texto = " ".join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn("Bancada", texto)
        self.assertIn("Cozinha 1", texto)

    def test_sugestoes_exigem_confirmacao_e_nao_duplicam(self):
        novo_tipo = TipoItemGrandeFornecedor.objects.create(
            categoria=self.categoria, nome="Rodabanca", unidade_padrao=self.unidade,
        )
        novo_tipo.tipos_ambiente_sugeridos.add(self.ambiente.tipo_ambiente)
        self.assertEqual(self.aplicacao.itens.count(), 1)
        url = reverse("obras:ficha_tecnica_acao", args=[self.obra.pk])
        dados = {
            "acao": "adicionar_sugestoes", "aplicacao": str(self.aplicacao.pk),
            "sugestoes": [str(novo_tipo.pk)], f"quantidade_{novo_tipo.pk}": "2",
            f"medidas_{novo_tipo.pk}": "2 m", f"especificacao_{novo_tipo.pk}": "Polido",
        }
        for _ in range(2):
            resposta = self.client.post(url, dados)
            self.assertEqual(resposta.status_code, 302)
        self.assertEqual(self.aplicacao.itens.filter(tipo_item=novo_tipo, ativo=True).count(), 1)
        self.assertEqual(self.aplicacao.itens.get(tipo_item=novo_tipo).descricao_medidas, "2 m")

    def test_medidas_e_material_explicito_seguem_para_matriz_gf(self):
        processo = ProcessoCompra.objects.create(
            numero="PC-FIC-1", obra=self.obra, titulo="Mármores",
            fluxo_grande_fornecedor=True, categoria_grande_fornecedor=self.categoria,
            etapa_atual=ProcessoCompra.Etapa.COMPATIBILIZACAO,
            status=ProcessoCompra.Status.EM_COMPATIBILIZACAO,
        )
        primeiro = sincronizar_itens_ficha_tecnica(processo=processo)
        segundo = sincronizar_itens_ficha_tecnica(processo=processo)
        self.assertEqual(primeiro["criados"], 1)
        self.assertEqual(segundo["criados"], 0)
        item_gf = processo.grande_fornecedor.itens.get(item_ficha_tecnica=self.item)
        self.assertEqual(item_gf.descricao_medidas, "2,40 × 0,60 m")
        self.assertEqual(item_gf.material_id, self.material.pk)

        url = reverse("compras:grande_fornecedor_matriz", args=[processo.pk])
        filtrada = self.client.get(url, {"pavimento": self.pavimento.pk, "ambiente": self.ambiente.pk,
                                         "material": self.material.pk, "tipo": self.tipo.pk})
        self.assertEqual(filtrada.status_code, 200)
        self.assertEqual(len(filtrada.context["matriz_linhas"]), 1)
        sem_correspondencia = self.client.get(url, {"material": self.material.pk + 999})
        self.assertEqual(len(sem_correspondencia.context["matriz_linhas"]), 0)
