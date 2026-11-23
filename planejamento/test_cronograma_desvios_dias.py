"""Regressões de datas, projeção e diferença temporal; sem banco de produção."""
from datetime import date
from django.test import SimpleTestCase
from planejamento.services.cronograma.prazos import calcular_indicadores_prazo
from planejamento.services.cronograma.resumo_geral import calcular_avancos_mensais


class DatasPrazoCronogramaTests(SimpleTestCase):
    def test_termino_real_importado_nao_bloqueia_projecao_de_obra_incompleta(self):
        resumo = {
            "previsto": .3737, "executado": .3991, "restante": .6009,
            "data_atualizacao": date(2026, 11, 18),
            "termino_real": date(2026, 10, 20),
            "termino_base": date(2027, 4, 27),
        }
        avancos = [{"avanco_real": 0.0}] + [{"avanco_real": valor} for valor in (.02, .021, .022, .0253)]
        prazos = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=.022075, avancos=avancos)
        self.assertTrue(prazos["projecao_confiavel"])
        self.assertTrue(prazos["termino_real_inconsistente"])
        self.assertIsNone(prazos["termino_real"])
        self.assertIsNone(prazos["dias_diferenca_real"])
        self.assertIsNotNone(prazos["previsao_termino"])
        self.assertGreater(prazos["previsao_termino"], date(2026, 11, 18))

    def test_fim_real_somente_em_obra_fisicamente_concluida(self):
        resumo = {
            "executado": 1.0, "previsto": 1.0,
            "data_atualizacao": date(2026, 11, 18),
            "termino_real": date(2026, 11, 12), "termino_base": date(2026, 11, 19),
        }
        prazos = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=.01, avancos=[])
        self.assertEqual(prazos["dias_diferenca_real"], -7)
        self.assertFalse(prazos["projecao_confiavel"])
        self.assertIsNone(prazos["previsao_termino"])

    def test_desvio_mensal_em_dias_atrasado_e_adiantado(self):
        serie = [
            {"semana":1,"data_referencia":date(2026,5,6),"previsto":0.0,"executado":0.0},
            {"semana":2,"data_referencia":date(2026,5,13),"previsto":0.10,"executado":0.05},
            {"semana":3,"data_referencia":date(2026,5,20),"previsto":0.20,"executado":0.25},
            {"semana":4,"data_referencia":date(2026,6,3),"previsto":0.30,"executado":0.20},
            {"semana":5,"data_referencia":date(2026,7,1),"previsto":0.40,"executado":0.45},
        ]
        mensais = calcular_avancos_mensais(serie)
        self.assertEqual([i["periodo"] for i in mensais], ["05/2026", "06/2026", "07/2026"])
        self.assertLess(mensais[0]["desvio_dias"], 0)  # realizado 25%, futuro planejado 30%
        self.assertGreater(mensais[1]["desvio_dias"], 0)  # realizado 20%, planejado 30%
        self.assertLess(mensais[2]["desvio_dias"], 0)  # acima do último ponto, projetado
        self.assertTrue(mensais[2]["desvio_dias_estimado"])

    def test_sem_dados_de_ritmo_nao_inventa_prazo(self):
        serie = [
            {"semana":1,"data_referencia":date(2026,5,6),"previsto":.2,"executado":.3},
            {"semana":2,"data_referencia":date(2026,5,13),"previsto":.2,"executado":.4},
        ]
        self.assertIsNone(calcular_avancos_mensais(serie)[0]["desvio_dias"])
