"""Regressões do painel quando o CSV repete INICIO_SEMANA em todos os retratos.

Nenhum destes testes acessa o MySQL ou altera dados de produção.
"""

from datetime import date

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from planejamento.models import ImportacaoCronograma, RegistroCronograma
from planejamento.services.cronograma.consultas import usar_importacao_ativa
from planejamento.services.cronograma.resumo_geral import (
    calcular_avancos_semanais,
    obter_serie_resumo_geral,
)


class GraficosCronogramaDatasTests(TestCase):
    def test_serie_mantem_medicoes_corretas_com_inicio_semana_repetido(self):
        importacao = ImportacaoCronograma.objects.create(status="CONCLUIDA", ativa=True)
        for semana, medicao, previsto, realizado in (
            (22, date(2026, 9, 30), 0.3096, 0.2883),
            (23, date(2026, 10, 7), 0.3340, 0.2961),
            (29, date(2026, 11, 18), 0.3737, 0.3991),
        ):
            RegistroCronograma.objects.create(
                importacao=importacao,
                projeto="QI 05 CJ 05 CASA 09",
                semana=semana,
                disciplina="RESUMO GERAL",
                inicio_semana=date(2026, 4, 27),
                data_atualizacao=medicao,
                percentual_previsto=previsto,
                percentual_executado=realizado,
            )
        with usar_importacao_ativa(importacao):
            serie = obter_serie_resumo_geral(projeto="QI 05 CJ 05 CASA 09")
        self.assertEqual(
            [item["data_referencia"] for item in serie],
            [date(2026, 9, 30), date(2026, 10, 7), date(2026, 11, 18)],
        )
        self.assertEqual(
            [item["inicio_semana"] for item in serie], [date(2026, 4, 27)] * 3,
        )
        self.assertAlmostEqual(serie[-1]["previsto"], 0.3737)
        self.assertAlmostEqual(serie[-1]["executado"], 0.3991)
        avancos = calcular_avancos_semanais(serie)
        self.assertEqual(avancos[-1]["data_referencia"], date(2026, 11, 18))
        self.assertAlmostEqual(avancos[-1]["executado_acumulado"], 0.3991)


class TemplateCronogramaDatasTests(SimpleTestCase):
    def test_ambos_graficos_usam_data_da_medicao_e_nao_inicio_semana(self):
        request = RequestFactory().get("/planejamento/")
        request.user = AnonymousUser()
        contexto = {
            "possui_dados": True,
            "projeto_selecionado": "QI 05 CJ 05 CASA 09",
            "semana_selecionada": 29,
            "resumo": {"data_atualizacao": date(2026, 11, 18), "previsto": .3737, "executado": .3991},
            "ultima_medicao": date(2026, 11, 18),
            "periodo_semana": {"inicio_semana": date(2026, 4, 27), "fim_semana": date(2026, 5, 3)},
            "serie": [], "avancos": [], "avancos_mensais": [],
        }
        html = render_to_string("planejamento/painel_cronograma.html", contexto, request=request)
        self.assertIn("Referência da medição: 18/11/2026", html)
        self.assertNotIn("27/04 a 03/05", html)
        self.assertNotIn("Última medição: 18/11/2026", html)
        self.assertIn("const dataMedicao = item => item.data_referencia || item.data_atualizacao || null;", html)
        self.assertIn("labels: serie.map(rotuloSemana)", html)
        self.assertIn("labels: avancos.map(rotuloSemana)", html)
        self.assertIn('" · Medição: " + dataCompleta(medicao)', html)
        self.assertNotIn("dataCurta(item.inicio_semana)", html)

    def test_barras_de_progresso_mantem_ponto_decimal_em_portugues(self):
        """O HTML <progress> requer ponto, apesar do formato visual pt-BR."""
        from django.utils import translation

        request = RequestFactory().get("/planejamento/")
        request.user = AnonymousUser()
        contexto = {
            "possui_dados": True,
            "resumo": {"previsto": 0.724, "executado": 0.632},
        }
        with translation.override("pt-br"):
            html = render_to_string(
                "planejamento/painel_cronograma.html", contexto, request=request
            )
        self.assertIn('value="0.7240"', html)
        self.assertIn('value="0.6320"', html)
        self.assertIn("72,40%", html)
        self.assertIn("63,20%", html)
        self.assertNotIn('value="0,7240"', html)
        self.assertNotIn('value="0,6320"', html)
