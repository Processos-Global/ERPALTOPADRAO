from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from compras.models import HistoricoCompraSuprimento, SuprimentoReferencia
from compras.services.historico_suprimentos import obter_ou_criar_referencia_suprimento
from obras.models import Obra
from planejamento.models import (
    CronogramaSuprimentosObra,
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)


class HistoricoSuprimentosTest(TestCase):
    # Cada caractere do prefixo ocupa quatro bytes em utf8mb4.
    prefixo = "\U00020000" * 499

    def test_chaves_longas_sao_unicas_pelo_texto_completo(self):
        primeira = obter_ou_criar_referencia_suprimento(self.prefixo + "a")
        segunda = obter_ou_criar_referencia_suprimento(self.prefixo + "B")
        repetida = obter_ou_criar_referencia_suprimento(self.prefixo + "A")

        primeira.refresh_from_db()
        segunda.refresh_from_db()
        self.assertEqual(primeira.chave, self.prefixo + "A")
        self.assertEqual(primeira.nome, self.prefixo + "A")
        self.assertEqual(segunda.chave, self.prefixo + "B")
        self.assertNotEqual(primeira.pk, segunda.pk)
        self.assertEqual(repetida.pk, primeira.pk)

        if connection.vendor == "mysql":
            with connection.cursor() as cursor:
                indices = connection.introspection.get_constraints(cursor, SuprimentoReferencia._meta.db_table)
                self.assertTrue(any(i["unique"] and i["columns"] == ["chave"] for i in indices.values()))
                cursor.execute("""
                    SELECT SUB_PART FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
                      AND COLUMN_NAME = 'chave' AND NON_UNIQUE = 0
                """, [SuprimentoReferencia._meta.db_table])
                self.assertEqual(cursor.fetchall(), ((None,),))

        with self.assertRaises(IntegrityError), transaction.atomic():
            SuprimentoReferencia.objects.create(nome="Duplicado", chave=primeira.chave)

    def test_historico_encontra_vinculo_multiplo_e_chave_legada_com_500_caracteres(self):
        nome_item = self.prefixo + "a"
        referencia = obter_ou_criar_referencia_suprimento(nome_item)
        outra_referencia = obter_ou_criar_referencia_suprimento(self.prefixo + "B")
        obra = Obra.objects.create(nome="Obra de teste", codigo="TESTE-HIST")
        importacao = ImportacaoCronogramaSuprimentos.objects.create(
            ativa=True,
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        cronograma = CronogramaSuprimentosObra.objects.create(
            importacao=importacao,
            obra=obra,
            nome_aba=obra.nome,
            codigo_aba=obra.codigo,
        )
        item = ItemCronogramaSuprimento.objects.create(cronograma_obra=cronograma, item=nome_item)
        legado = HistoricoCompraSuprimento.objects.create(
            suprimento=nome_item,
            suprimento_chave=referencia.chave,
            fornecedor_nome="Fornecedor legado",
            valor=Decimal("125.00"),
            origem=HistoricoCompraSuprimento.Origem.LEGADO,
        )
        agrupado = HistoricoCompraSuprimento.objects.create(
            suprimento="Compra agrupada",
            suprimento_chave="COMPRA AGRUPADA",
            fornecedor_nome="Fornecedor da compra agrupada",
            valor=Decimal("375.00"),
            origem=HistoricoCompraSuprimento.Origem.LEGADO,
        )
        agrupado.suprimentos_referencia.add(referencia, outra_referencia)
        HistoricoCompraSuprimento.objects.create(
            suprimento=self.prefixo + "B",
            suprimento_chave=outra_referencia.chave,
            fornecedor_nome="Fornecedor de outro suprimento",
            valor=Decimal("625.00"),
            origem=HistoricoCompraSuprimento.Origem.LEGADO,
        )
        usuario = get_user_model().objects.create_superuser(username="historico-suprimentos")
        self.client.force_login(usuario)

        url = reverse("planejamento:historico_item_cronograma_suprimentos", args=[item.pk])
        resposta = self.client.get(url)

        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["suprimento"], nome_item)
        self.assertEqual(dados["total"], 2)
        self.assertEqual(
            {registro["id"]: registro["suprimento_agrupado"] for registro in dados["registros"]},
            {legado.pk: False, agrupado.pk: True},
        )
        self.assertFalse(legado.suprimentos_referencia.exists())
