from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cadastros.models import Fornecedor, MaoObra, Material, UnidadeMedida


class PaginacaoCatalogosTest(TestCase):
    def test_catalogos_paginam_filtros_e_excluem_inativos(self):
        self.client.force_login(get_user_model().objects.create_superuser('catalogos-teste'))
        unidade = UnidadeMedida.objects.create(sigla='UN')
        cenarios = (
            ('materiais_lista', 'materiais', Material, 'nome', {'unidade': unidade}, {'unidade': unidade.pk}),
            ('fornecedores_lista', 'fornecedores', Fornecedor, 'nome', {}, {}),
            ('mao_obra_lista', 'itens', MaoObra, 'descricao', {'unidade': unidade}, {}),
        )
        for rota, contexto, modelo, campo, campos, filtros in cenarios:
            with self.subTest(rota=rota):
                modelo.objects.bulk_create([
                    modelo(**{campo: f'Sintético {i:02d}'}, **campos) for i in range(31)
                ])
                modelo.objects.create(**{campo: 'Sintético inativo'}, **campos, ativo=False)
                url = reverse(f'cadastros:{rota}')
                filtros = {**filtros, 'q': 'Sintético', 'status': 'ativos'}
                primeira = self.client.get(url, filtros)
                self.assertEqual(len(primeira.context[contexto]), 30)
                self.assertNotContains(primeira, 'Sintético 30')
                self.assertContains(primeira, 'page=2')
                segunda = self.client.get(url, {**filtros, 'page': '2'})
                self.assertContains(segunda, 'Sintético 30')
                self.assertNotContains(segunda, 'Sintético inativo')
                self.assertTrue(segunda.context[contexto].has_previous())
