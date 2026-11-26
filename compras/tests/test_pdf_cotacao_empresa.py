from io import BytesIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader

from cadastros.models import DadosEmpresa, Fornecedor
from compras.models import NecessidadeCompra, ProcessoCompra
from compras.services.pdf_solicitacao_cotacao import gerar_pdf_solicitacao_cotacao
from obras.models import Obra


class PdfCotacaoEmpresaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser("pdf-cotacao-empresa")
        obra = Obra.objects.create(nome="Obra sintetica", codigo="OB-PDF-COT")
        cls.processo = ProcessoCompra.objects.create(numero="PC-PDF-QA", titulo="Solicitacao teste", obra=obra)
        cls.item = NecessidadeCompra.objects.create(
            processo=cls.processo, descricao="Material sintetico & especial", unidade="UN",
            quantidade_necessaria=100, quantidade_incluida=60,
        )

    def pdf(self):
        return PdfReader(BytesIO(gerar_pdf_solicitacao_cotacao(self.processo)))

    @staticmethod
    def texto(pdf):
        return "\n".join(pagina.extract_text() for pagina in pdf.pages)

    def test_usa_empresa_institucional_e_logo_via_storage_sem_caminho_local(self):
        logo = BytesIO()
        Image.new("RGB", (120, 60), "brown").save(logo, format="PNG")
        nome = "empresa/logo/qa.png"
        storage = Mock(spec=Storage)
        storage.open.return_value = ContentFile(logo.getvalue())
        storage.path.side_effect = NotImplementedError
        with patch.object(DadosEmpresa._meta.get_field("logo"), "storage", storage):
            DadosEmpresa.objects.create(
                razao_social="Engenharia QA Ltda", nome_fantasia="Engenharia QA", cnpj="00.000.000/0001-00",
                logradouro="Rua Sintetica", numero="100", complemento="Sala A", bairro="Centro",
                cidade="Cidade QA", uf="SP", cep="01234-000", telefone="(11) 1234-5678",
                email="qa@example.test", inscricao_estadual="IE-QA", inscricao_municipal="IM-QA", logo=nome,
            )
            DadosEmpresa.objects.create(razao_social="Outro cadastro")
            pdf = self.pdf()
        storage.open.assert_called_once_with(nome, "rb")
        storage.path.assert_not_called()
        texto = self.texto(pdf)
        for trecho in (
            "Engenharia QA Ltda", "Engenharia QA", "00.000.000/0001-00", "Rua Sintetica", "Sala A", "Centro",
            "Cidade QA", "SP", "01234-000", "(11) 1234-5678", "qa@example.test", "IE-QA", "IM-QA",
            "PC-PDF-QA", "Material sintetico & especial", "60",
        ):
            self.assertIn(trecho, texto)
        self.assertNotIn("Outro cadastro", texto)
        self.assertEqual([imagem.image.size for imagem in pdf.pages[0].images], [(120, 60)])

    @override_settings(STATICFILES_DIRS=[])
    def test_cadastro_parcial_sem_logo_e_arquivo_indisponivel_gera_documento(self):
        empresa = DadosEmpresa.objects.create(razao_social="Empresa minima", nome_fantasia="")
        for nome in ("", "empresa/logo/inexistente.png"):
            with self.subTest(logo=nome):
                empresa.logo = nome
                empresa.save(update_fields=["logo"])
                pdf = self.pdf()
                self.assertIn("Empresa minima", self.texto(pdf))
                self.assertNotIn("None", self.texto(pdf))

    def test_especificacao_longa_e_multiplas_paginas_preservam_itens(self):
        self.item.especificacao = ("Detalhamento da especificacao tecnica do material. " * 150) + " FIM-ESPECIFICACAO"
        self.item.save(update_fields=["especificacao"])
        NecessidadeCompra.objects.bulk_create([
            NecessidadeCompra(processo=self.processo, descricao=f"Z-ITEM-{indice:02d}", unidade="UN",
                              quantidade_necessaria=1, quantidade_incluida=1)
            for indice in range(32)
        ])
        fornecedor = Fornecedor.objects.create(nome="Fornecedor QA do documento", documento="00.000.000/0001-00")
        pdf = PdfReader(BytesIO(gerar_pdf_solicitacao_cotacao(self.processo, fornecedor=fornecedor)))
        texto = self.texto(pdf)
        self.assertGreater(len(pdf.pages), 1)
        self.assertIn("FIM-ESPECIFICACAO", texto)
        self.assertIn("Z-ITEM-31", texto)
        self.assertIn("Fornecedor QA do documento", texto)

    def test_rota_preserva_permissao_e_entrega_pdf_com_conteudo(self):
        url = reverse("compras:pdf_solicitacao_cotacao", args=[self.processo.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(get_user_model().objects.create_user("sem-acesso-cotacao"))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.usuario)
        resposta = self.client.get(url)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn("PC-PDF-QA", resposta["Content-Disposition"])
        self.assertIn("Material sintetico & especial", self.texto(PdfReader(BytesIO(resposta.content))))
        self.assertRedirects(
            self.client.get(url, {"fornecedor": "²"}),
            reverse("compras:detalhe_processo", args=[self.processo.pk]), fetch_redirect_response=False,
        )
