from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from cadastros.models import Material, UnidadeMedida
from obras.models import MovimentoEstoque, Obra
from obras.services.estoque import obter_estoque


class EstoqueConsultasTest(TestCase):
    def test_materiais_nao_geram_consulta_por_movimento(self):
        obra = Obra.objects.create(nome="Obra teste estoque", codigo="OB-EST-01")
        unidade = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        for indice in range(5):
            material = Material.objects.create(nome=f"Material {indice}", unidade=unidade)
            MovimentoEstoque.objects.create(
                tipo=MovimentoEstoque.Tipo.SAIDA,
                obra_origem=obra,
                material=material,
                descricao_item=material.nome,
                unidade="UN",
                quantidade=Decimal("1"),
            )

        with CaptureQueriesContext(connection) as consultas:
            linhas = obter_estoque(obra=obra, somente_com_saldo=False)

        self.assertEqual(len(linhas), 5)
        self.assertEqual(len(consultas), 2)
