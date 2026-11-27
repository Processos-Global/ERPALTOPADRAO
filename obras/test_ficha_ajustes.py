from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import CaracteristicaAmbiente, CategoriaGrandeFornecedor, TipoAmbiente
from obras.models import (
    AmbienteFichaTecnica, CategoriaFichaTecnica, FichaTecnicaObra,
    ItemFichaTecnica, Obra, PavimentoFichaTecnica,
)


class FichaAjustesTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(username="admin-ficha-lote")
        self.client.force_login(self.usuario)
        self.obra = Obra.objects.create(nome="Ficha lote", codigo="FIC-LOTE")
        self.ficha = FichaTecnicaObra.objects.create(obra=self.obra)
        self.pav = PavimentoFichaTecnica.objects.create(ficha=self.ficha, nome="Térreo")
        self.seca, _ = CaracteristicaAmbiente.objects.get_or_create(codigo="SECA", defaults={"nome": "Seca"})
        self.molhada, _ = CaracteristicaAmbiente.objects.get_or_create(codigo="AREA_MOLHADA", defaults={"nome": "Molhada"})
        self.tipo, _ = TipoAmbiente.objects.get_or_create(nome="Ambiente lote", defaults={"caracteristica_padrao": self.seca})
        self.a = self.ambiente(self.pav, "Sala", self.seca)
        self.b = self.ambiente(self.pav, "Banheiro", self.molhada)
        self.inativo = self.ambiente(self.pav, "Inativo", self.seca, False)
        outra = FichaTecnicaObra.objects.create(obra=Obra.objects.create(nome="Outra ficha", codigo="FIC-OUTRA"))
        self.outro = self.ambiente(PavimentoFichaTecnica.objects.create(ficha=outra, nome="Térreo"), "Outro", self.seca)
        self.cat = CategoriaGrandeFornecedor.objects.create(nome="Pisos lote")
        self.outra_cat = CategoriaGrandeFornecedor.objects.create(nome="Outra categoria lote")
        self.url = reverse("obras:ficha_tecnica_acao", args=[self.obra.pk])

    def ambiente(self, pav, nome, caracteristica, ativo=True):
        return AmbienteFichaTecnica.objects.create(pavimento=pav, tipo_ambiente=self.tipo,
            identificacao=nome, caracteristica=caracteristica, area_m2=Decimal("10"), ativo=ativo)

    def aplicar(self, cat):
        return self.client.post(self.url, {"acao": "aplicar_categoria_todos_ambientes", "categoria_lote": cat.pk, "etapa": "3"})

    def test_lote_preserva_itens_e_outras_categorias_sem_duplicar(self):
        ap = CategoriaFichaTecnica.objects.create(ficha=self.ficha, categoria=self.cat, ambiente=self.a)
        item = ItemFichaTecnica.objects.create(aplicacao_categoria=ap, descricao_item="Piso existente")
        outra = CategoriaFichaTecnica.objects.create(ficha=self.ficha, categoria=self.outra_cat, ambiente=self.a)
        inativa = CategoriaFichaTecnica.objects.create(ficha=self.ficha, categoria=self.cat, ambiente=self.b, ativo=False)
        self.assertEqual(self.aplicar(self.cat).status_code, 302)
        self.assertEqual(self.aplicar(self.cat).status_code, 302)
        self.assertEqual(set(CategoriaFichaTecnica.objects.filter(categoria=self.cat, ativo=True).values_list("ambiente_id", flat=True)), {self.a.pk, self.b.pk})
        self.assertEqual(CategoriaFichaTecnica.objects.filter(categoria=self.cat).count(), 2)
        inativa.refresh_from_db()
        self.assertTrue(inativa.ativo)
        self.assertTrue(ItemFichaTecnica.objects.filter(pk=item.pk, aplicacao_categoria=ap).exists())
        self.assertTrue(CategoriaFichaTecnica.objects.filter(pk=outra.pk).exists())

    def test_lote_respeita_area_molhada_e_escopo(self):
        self.cat.somente_area_molhada = True
        self.cat.save(update_fields=["somente_area_molhada"])
        self.assertEqual(self.aplicar(self.cat).status_code, 302)
        self.assertEqual(list(CategoriaFichaTecnica.objects.filter(categoria=self.cat).values_list("ambiente_id", flat=True)), [self.b.pk])
        self.outra_cat.tipo_preenchimento = CategoriaGrandeFornecedor.TipoPreenchimento.MULTIPLA_PROJETO
        self.outra_cat.save(update_fields=["tipo_preenchimento"])
        self.assertEqual(self.aplicar(self.outra_cat).status_code, 404)
        self.assertFalse(CategoriaFichaTecnica.objects.filter(categoria=self.outra_cat).exists())

    def test_sem_permissao_nao_aplica(self):
        self.client.force_login(get_user_model().objects.create_user(username="ficha-sem-edicao"))
        self.assertEqual(self.aplicar(self.cat).status_code, 403)
        self.assertFalse(CategoriaFichaTecnica.objects.filter(categoria=self.cat).exists())

    def test_quebras_de_linha_renderizadas_e_html_escapado(self):
        ap = CategoriaFichaTecnica.objects.create(ficha=self.ficha, categoria=self.cat, ambiente=self.a)
        ItemFichaTecnica.objects.create(aplicacao_categoria=ap, descricao_item="Piso", especificacao="- Primeira linha\n- <b>Segunda linha</b>\n\n- Terceira linha")
        url = reverse("obras:ficha_tecnica", args=[self.obra.pk])
        detalhe = self.client.get(url, {"etapa": "4", "ambiente": self.a.pk})
        consulta = self.client.get(reverse("obras:ficha_tecnica_consulta"), {"obra": self.obra.pk, "ambiente": self.a.pk})
        for resposta in (detalhe, consulta):
            self.assertContains(resposta, "- Primeira linha<br>- &lt;b&gt;Segunda linha&lt;/b&gt;<br><br>- Terceira linha", html=True)
        categorias = self.client.get(url, {"etapa": "3"})
        self.assertContains(categorias, "Aplicar categoria a todos os ambientes")
