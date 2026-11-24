from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor, Material, UnidadeMedida
from financeiro.models import PlanoFinanceiro, TituloPagar
from obras.models import Obra
from usuarios.models import ModuloSistema, PermissaoFinanceiro, PermissaoModulo


class FormularioAvulsoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="teste_form_avulso")
        cls.permissao = PermissaoFinanceiro.objects.create(usuario=cls.usuario, lancar_titulos=True, editar_titulos=True)
        PermissaoModulo.objects.create(usuario=cls.usuario, modulo=ModuloSistema.FINANCEIRO)
        cls.obra = Obra.objects.create(nome="Obra sintética", codigo="OF-2026")
        classe = PlanoFinanceiro.objects.create(codigo="FAV", nome="Classe fictícia")
        cls.apropriacao = PlanoFinanceiro.objects.create(codigo="FAV.01", nome="Apropriação fictícia", pai=classe)
        cls.fornecedor = Fornecedor.objects.create(nome="Fornecedor sintético ativo", banco="Banco-Privado-A")
        cls.outro = Fornecedor.objects.create(nome="Fornecedor sintético inativo", banco="Banco-Privado-B", ativo=False)
        unidade = UnidadeMedida.objects.create(sigla="TFO", descricao="Unidade sintética")
        cls.material = Material.objects.create(nome="Insumo fictício escondido", unidade=unidade)

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_formulario_novo_nao_carrega_catalogo_e_dados_bancarios_inteiros(self):
        resposta = self.client.get(reverse("financeiro:titulo_novo"))
        self.assertNotContains(resposta, "Banco-Privado-")
        self.assertNotContains(resposta, self.outro.nome)
        self.assertNotContains(resposta, self.material.nome)
        self.assertContains(resposta, 'name="competencia"')
        self.assertContains(resposta, 'name="condicao_pagamento"')

    def test_consulta_privada_retorna_dados_de_um_unico_fornecedor_sem_cache(self):
        rota = reverse("financeiro:titulo_catalogo")
        dados = self.client.get(rota, {"tipo": "dados_bancarios", "id": self.fornecedor.pk})
        self.assertEqual(dados.status_code, 200)
        self.assertEqual(dados.json()["banco"], "Banco-Privado-A")
        self.assertNotContains(dados, "Banco-Privado-B")
        self.assertIn("no-store", dados.headers["Cache-Control"])
        self.assertEqual(self.client.get(rota, {"tipo": "dados_bancarios", "id": self.outro.pk}).status_code, 404)

    def test_consulta_publica_de_fornecedores_retorna_apenas_identificacao_inclusive_inativos(self):
        PermissaoFinanceiro.objects.filter(pk=self.permissao.pk).update(lancar_titulos=False, editar_titulos=False)
        rota = reverse("financeiro:titulo_catalogo")
        consulta = self.client.get(rota, {"tipo": "fornecedor_publico", "q": "inativo"})
        self.assertEqual(consulta.json(), {"resultados": [{"id": self.outro.pk, "texto": self.outro.nome}]})
        self.assertEqual(self.client.get(rota, {"tipo": "dados_bancarios", "id": self.fornecedor.pk}).status_code, 403)
        self.assertEqual(self.client.get(rota, {"tipo": "material", "q": "Insumo"}).status_code, 403)

    def test_busca_em_catalogo_extenso_e_limitada(self):
        Fornecedor.objects.bulk_create([Fornecedor(nome=f"Empresa fictícia {i:02d}") for i in range(30)])
        rota = reverse("financeiro:titulo_catalogo")
        resposta = self.client.get(rota, {"tipo": "fornecedor", "q": "Empresa fictícia"})
        self.assertEqual(len(resposta.json()["resultados"]), 25)
        self.assertEqual(self.client.get(rota, {"tipo": "obra", "q": self.obra.codigo}).json(), {
            "resultados": [{"id": self.obra.pk, "texto": str(self.obra)}],
        })
        self.assertEqual(self.client.get(rota, {"tipo": "material", "q": "Insumo"}).json(), {
            "resultados": [{"id": self.material.pk, "texto": str(self.material)}],
        })
        self.assertEqual(self.client.get(rota, {"tipo": "apropriacao", "q": "Classe fictícia"}).json(), {
            "resultados": [{"id": self.apropriacao.pk, "texto": str(self.apropriacao)}],
        })

    def test_edicao_aprovada_exibe_apenas_selecao_e_snapshot_bancario(self):
        titulo = TituloPagar.objects.create(
            numero="FIN-FORM-1", status=TituloPagar.Status.APROVADO, fornecedor=self.fornecedor,
            obra=self.obra, plano_financeiro=self.apropriacao, descricao="Conta sintética", valor_original=Decimal("100.00"),
            vencimento=date(2026, 11, 30), beneficiario_banco="Banco histórico", competencia=date(2026, 11, 1),
        )
        resposta = self.client.get(reverse("financeiro:titulo_editar", args=[titulo.pk]))
        self.assertContains(resposta, self.fornecedor.nome)
        self.assertContains(resposta, "Banco histórico")
        self.assertNotContains(resposta, "Banco-Privado-")
        self.assertNotContains(resposta, self.outro.nome)
