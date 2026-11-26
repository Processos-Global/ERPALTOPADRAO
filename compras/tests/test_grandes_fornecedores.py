from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from openpyxl import load_workbook

from cadastros.models import CategoriaGrandeFornecedor, Fornecedor, Material, UnidadeMedida
from compras.models import (
    GrandeFornecedorItem,
    GrandeFornecedorOferta,
    GrandeFornecedorParticipante,
    GrandeFornecedorProcesso,
    ProcessoCompra,
)
from obras.models import CategoriaFichaTecnica, FichaTecnicaObra, ItemFichaTecnica, Obra
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class GrandesFornecedoresContractTest(TestCase):
    def test_process_model_exposes_special_flow_flag(self):
        self.assertTrue(hasattr(ProcessoCompra, "fluxo_grande_fornecedor"))

    def test_price_history_difference_is_new_minus_old(self):
        from compras.models import HistoricoValorGrandeFornecedor

        historico = HistoricoValorGrandeFornecedor(
            valor_anterior=Decimal("100.00"),
            valor_novo=Decimal("90.00"),
        )
        self.assertEqual(historico.diferenca, Decimal("-10.00"))


class SincronizacaoMatrizTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(username="gf-admin")
        obra = Obra.objects.create(nome="Obra de teste", codigo="GF-TESTE")
        categoria = CategoriaGrandeFornecedor.objects.create(nome="Bancadas")
        ficha = FichaTecnicaObra.objects.create(obra=obra)
        aplicacao = CategoriaFichaTecnica.objects.create(ficha=ficha, categoria=categoria)
        cls.item_ficha = ItemFichaTecnica.objects.create(
            aplicacao_categoria=aplicacao, descricao_item="Bancada A", quantidade=1
        )
        cls.processo = ProcessoCompra.objects.create(
            numero="GF-TESTE",
            obra=obra,
            titulo="Bancadas",
            fluxo_grande_fornecedor=True,
            categoria_grande_fornecedor=categoria,
            etapa_atual=ProcessoCompra.Etapa.COMPATIBILIZACAO,
            status=ProcessoCompra.Status.EM_COMPATIBILIZACAO,
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.matriz = reverse("compras:grande_fornecedor_matriz", args=[self.processo.pk])
        self.sincronizar = reverse("compras:gf_importar_ficha_tecnica", args=[self.processo.pk])

    def test_get_exibe_pendencia_sem_gravar_fluxo_ou_item(self):
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.matriz)
        self.assertContains(resposta, "Sincronizar Ficha Técnica")
        self.assertEqual(resposta.context["qtd_itens_ficha_pendentes"], 1)
        self.assertFalse(GrandeFornecedorProcesso.objects.filter(processo=self.processo).exists())
        escritas = {"INSERT", "UPDATE", "DELETE", "REPLACE"}
        self.assertFalse(any(q["sql"].split()[0] in escritas for q in consultas))

    def test_post_importa_e_atualiza_sem_duplicar_item_ou_historico(self):
        self.assertEqual(self.client.post(self.sincronizar).status_code, 302)
        vinculo = GrandeFornecedorItem.objects.get(item_ficha_tecnica=self.item_ficha)
        self.assertEqual(vinculo.quantidade, 1)
        ItemFichaTecnica.objects.filter(pk=self.item_ficha.pk).update(quantidade=3)
        self.assertEqual(self.client.get(self.matriz).status_code, 200)
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.quantidade, 1)

        self.assertEqual(self.client.post(self.sincronizar).status_code, 302)
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.quantidade, 3)
        self.assertEqual(self.client.post(self.sincronizar).status_code, 302)
        self.assertEqual(GrandeFornecedorItem.objects.filter(item_ficha_tecnica=self.item_ficha).count(), 1)
        self.assertEqual(
            self.processo.historico.filter(tipo="GF_FICHA_TECNICA_SINCRONIZADA").count(), 2
        )

    def test_excel_do_relatorio_preserva_texto_e_quantidade(self):
        fluxo = GrandeFornecedorProcesso.objects.create(processo=self.processo)
        texto = "=1+1"
        GrandeFornecedorItem.objects.create(fluxo=fluxo, item=texto, quantidade=2)
        resposta = self.client.get(reverse("compras:relatorio_grandes_fornecedores"), {"formato": "xlsx"})

        self.assertEqual(resposta.status_code, 200)
        planilha = load_workbook(BytesIO(resposta.content), read_only=True)
        self.addCleanup(planilha.close)
        self.assertEqual(planilha.active["I2"].value, texto)
        self.assertEqual(planilha.active["I2"].data_type, "s")
        self.assertEqual(planilha.active["K2"].value, 2)
        self.assertEqual(planilha.active["K2"].data_type, "n")

    def test_post_respeita_permissao_de_edicao(self):
        leitor = get_user_model().objects.create_user(username="gf-leitor")
        PermissaoModulo.objects.create(
            usuario=leitor, modulo=ModuloSistema.COMPRAS, nivel=NivelPermissao.LEITURA
        )
        self.client.force_login(leitor)
        self.assertNotContains(self.client.get(self.matriz), "Sincronizar Ficha Técnica")
        self.assertEqual(self.client.post(self.sincronizar).status_code, 403)
        self.assertFalse(GrandeFornecedorProcesso.objects.filter(processo=self.processo).exists())

    def test_post_preserva_matriz_aprovada(self):
        ProcessoCompra.objects.filter(pk=self.processo.pk).update(status=ProcessoCompra.Status.APROVADO)
        self.assertNotContains(self.client.get(self.matriz), "Sincronizar Ficha Técnica")
        self.assertEqual(self.client.post(self.sincronizar).status_code, 302)
        self.assertFalse(GrandeFornecedorProcesso.objects.filter(processo=self.processo).exists())

    def test_sincronizacao_preserva_oferta_de_linha_manual_equivalente(self):
        fluxo = GrandeFornecedorProcesso.objects.create(processo=self.processo)
        item_manual = GrandeFornecedorItem.objects.create(fluxo=fluxo, item="Bancada A", quantidade=2)
        fornecedor = Fornecedor.objects.create(nome="Fornecedor técnico")
        participante = GrandeFornecedorParticipante.objects.create(fluxo=fluxo, fornecedor=fornecedor)
        oferta = GrandeFornecedorOferta.objects.create(item=item_manual, participante=participante, valor_atual=10)
        self.assertEqual(self.client.post(self.sincronizar).status_code, 302)
        resposta = self.client.get(self.matriz)
        self.assertEqual(resposta.context["qtd_itens_ficha_pendentes"], 1)
        self.assertEqual(list(fluxo.itens.all()), [item_manual])
        self.assertEqual(item_manual.ofertas.get(), oferta)

    def test_conclusao_da_compatibilizacao_pede_revisao_apos_incluir_item_da_ficha(self):
        url = reverse("compras:gf_concluir_compatibilizacao", args=[self.processo.pk])
        versao_anterior = self.client.get(self.matriz).context["versao_matriz"]
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"versao_matriz": versao_anterior}).status_code, 302)
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.etapa_atual, ProcessoCompra.Etapa.COMPATIBILIZACAO)
        self.assertTrue(GrandeFornecedorItem.objects.filter(item_ficha_tecnica=self.item_ficha).exists())
        resposta = self.client.get(self.matriz)
        self.assertContains(resposta, "Revise a matriz")

        self.assertEqual(self.client.post(url, {"versao_matriz": resposta.context["versao_matriz"]}).status_code, 302)
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.etapa_atual, ProcessoCompra.Etapa.NEGOCIACAO)

    def test_envio_para_aprovacao_pede_revisao_apos_atualizar_medida_da_ficha(self):
        self.client.post(self.sincronizar)
        item = GrandeFornecedorItem.objects.get(item_ficha_tecnica=self.item_ficha)
        fornecedor = Fornecedor.objects.create(nome="Fornecedor da proposta")
        participante = GrandeFornecedorParticipante.objects.create(fluxo=item.fluxo, fornecedor=fornecedor)
        GrandeFornecedorOferta.objects.create(item=item, participante=participante, valor_atual=10)
        item.participante_aprovado = participante
        item.save(update_fields=["participante_aprovado"])
        ItemFichaTecnica.objects.filter(pk=self.item_ficha.pk).update(quantidade=4, descricao_medidas="2 m")
        ProcessoCompra.objects.filter(pk=self.processo.pk).update(
            etapa_atual=ProcessoCompra.Etapa.NEGOCIACAO, status=ProcessoCompra.Status.EM_NEGOCIACAO
        )
        url = reverse("compras:gf_enviar_aprovacao", args=[self.processo.pk])
        versao_anterior = self.client.get(self.matriz).context["versao_matriz"]
        for _ in range(2):
            self.assertEqual(self.client.post(url, {"versao_matriz": versao_anterior}).status_code, 302)
        self.processo.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.processo.etapa_atual, ProcessoCompra.Etapa.NEGOCIACAO)
        self.assertEqual((item.quantidade, item.descricao_medidas), (4, "2 m"))
        self.assertEqual(item.participante_aprovado_id, participante.pk)
        resposta = self.client.get(self.matriz)
        self.assertContains(resposta, "Revise a matriz")

        self.assertEqual(self.client.post(url, {"versao_matriz": resposta.context["versao_matriz"]}).status_code, 302)
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.etapa_atual, ProcessoCompra.Etapa.APROVACAO)

    def test_parametros_numericos_fora_da_faixa_sao_ignorados(self):
        resposta = self.client.get(self.matriz, {"pavimento": "9" * 4301, "material": str(2**63)})
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.context["filtros_matriz"]["pavimento"])
        self.assertIsNone(resposta.context["filtros_matriz"]["material"])

    @override_settings(USE_THOUSAND_SEPARATOR=True)
    def test_filtro_da_matriz_usa_id_sem_separador_de_milhar(self):
        unidade = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        material = Material.objects.create(pk=1234, nome="Bancada", unidade=unidade)
        ItemFichaTecnica.objects.filter(pk=self.item_ficha.pk).update(material=material)
        self.client.post(self.sincronizar)

        resposta = self.client.get(self.matriz, {"material": "01234"})
        self.assertEqual(resposta.context["filtros_matriz"]["material"], 1234)
        self.assertEqual(len(resposta.context["matriz_linhas"]), 1)
        self.assertContains(resposta, 'value="1234" selected')
        self.assertContains(resposta, 'data-material="1234"')
