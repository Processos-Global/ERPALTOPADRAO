from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from obras.models import Obra
from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra,
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)
from planejamento.services.cronograma_suprimentos.painel import (
    montar_painel_cronograma_suprimentos,
)


class PainelSuprimentosConsultasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        importacao = ImportacaoCronogramaSuprimentos.objects.create(
            ativa=True,
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        cls.itens = []
        for indice in range(3):
            obra = Obra.objects.create(nome=f"Obra {indice}", codigo=f"OB{indice}")
            cronograma = CronogramaSuprimentosObra.objects.create(
                importacao=importacao,
                obra=obra,
                nome_aba=obra.nome,
                codigo_aba=obra.codigo,
                ordem_aba=indice,
            )
            cls.itens.append(ItemCronogramaSuprimento.objects.create(
                cronograma_obra=cronograma,
                item=f"Suprimento {indice}",
                categoria="MATERIAL" if indice == 0 else "SERVICO",
            ))
            if indice == 0:
                ItemCronogramaSuprimento.objects.create(
                    cronograma_obra=cronograma,
                    item="Outro suprimento",
                    categoria="SERVICO",
                )

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_opcoes_de_todas_as_obras_usam_consulta_unica(self, anexar):
        with CaptureQueriesContext(connection) as consultas:
            contexto = montar_painel_cronograma_suprimentos()

        self.assertEqual(len(consultas), 4)
        self.assertEqual(contexto["suprimentos_filtro"], [
            "Outro suprimento", "Suprimento 0", "Suprimento 1", "Suprimento 2",
        ])
        anexar.assert_called_once()

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_filtro_local_limita_carga_comercial_sem_mudar_resumo(self, anexar):
        contexto = montar_painel_cronograma_suprimentos(
            suprimento="Suprimento 0", categoria="MATERIAL",
        )
        self.assertEqual(contexto["resumo"]["total"], 1)
        self.assertEqual(contexto["resumo"]["filtrados"], 1)
        self.assertEqual([item.id for item in anexar.call_args.args[0]], [self.itens[0].id])

        anexar.reset_mock()
        contexto = montar_painel_cronograma_suprimentos(categoria="MATERIAL")
        self.assertEqual(contexto["resumo"]["total"], 2)
        self.assertEqual(contexto["resumo"]["filtrados"], 1)
        self.assertEqual([item.id for item in anexar.call_args.args[0]], [self.itens[0].id])

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_suprimento_em_varias_obras_carrega_itens_em_uma_consulta(self, anexar):
        for item in self.itens:
            ItemCronogramaSuprimento.objects.create(
                cronograma_obra=item.cronograma_obra,
                item="Comum",
            )

        with CaptureQueriesContext(connection) as consultas:
            contexto = montar_painel_cronograma_suprimentos(suprimento="Comum")

        self.assertEqual(len(consultas), 4)
        self.assertEqual(contexto["resumo"]["total"], 3)
        self.assertEqual(
            [item.obra_exibicao for item in anexar.call_args.args[0]],
            ["Obra 0", "Obra 1", "Obra 2"],
        )

    @override_settings(USE_THOUSAND_SEPARATOR=True, THOUSAND_SEPARATOR=".")
    def test_filtro_get_envia_id_da_obra_sem_formatacao_e_renderiza_painel(self):
        obra = Obra.objects.create(pk=1234, nome="Obra do filtro", codigo="OB1234")
        cronograma = CronogramaSuprimentosObra.objects.create(
            importacao=self.itens[0].cronograma_obra.importacao,
            obra=obra, nome_aba=obra.nome, codigo_aba=obra.codigo, ordem_aba=4,
        )
        ItemCronogramaSuprimento.objects.create(
            cronograma_obra=cronograma, item="Filtro específico", categoria="MATERIAL",
        )
        usuario = get_user_model().objects.create_superuser(username="filtro-suprimentos", password="teste")
        self.client.force_login(usuario)
        url = reverse("planejamento:painel_cronograma_suprimentos")

        resposta = self.client.get(url, {"obra": obra.pk, "categoria": "MATERIAL"})

        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.headers.get("Content-Disposition"))
        self.assertEqual(resposta.context["cronograma_obra"].obra_id, obra.pk)
        self.assertEqual(resposta.context["resumo"]["filtrados"], 1)
        html = resposta.content.decode()
        self.assertIn('value="1234" selected', html)
        self.assertIn(f'{reverse("planejamento:kanban_cronograma_suprimentos")}?obra=1234', html)
