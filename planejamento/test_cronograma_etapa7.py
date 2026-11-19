from datetime import date

from django.test import SimpleTestCase, TestCase

from planejamento.models import ImportacaoCronograma, RegistroCronograma
from planejamento.services.cronograma.consultas import usar_importacao_ativa
from planejamento.services.cronograma.prazos import calcular_indicadores_prazo
from planejamento.services.cronograma.resumo_geral import (
    calcular_avancos_mensais,
    calcular_avancos_semanais,
    calcular_media_avancos,
    obter_serie_resumo_geral,
)


class CalculosCronogramaEtapa7Tests(SimpleTestCase):
    def test_media_semanal_nao_trata_primeiro_acumulado_como_avanco(self):
        avancos = [
            {"avanco_real": .40, "avanco_previsto": .40},
            {"avanco_real": .05, "avanco_previsto": .10},
            {"avanco_real": .15, "avanco_previsto": .10},
        ]
        media = calcular_media_avancos(avancos)
        self.assertAlmostEqual(media["media_real"], .10)
        self.assertEqual(media["quantidade_semanas"], 2)

    def test_mensal_usa_ultimo_snapshot_e_incrementos_por_diferenca(self):
        serie = [
            {"semana": 1, "data_referencia": date(2026, 1, 7), "executado": .1, "previsto": .15},
            {"semana": 2, "data_referencia": date(2026, 1, 14), "executado": .2, "previsto": .3},
            {"semana": 3, "data_referencia": date(2026, 2, 4), "executado": .35, "previsto": .45},
        ]
        mensal = calcular_avancos_mensais(serie)
        self.assertEqual([item["periodo"] for item in mensal], ["01/2026", "02/2026"])
        self.assertAlmostEqual(mensal[0]["executado_acumulado"], .2)
        self.assertAlmostEqual(mensal[1]["avanco_real"], .15)
        self.assertAlmostEqual(mensal[1]["avanco_previsto"], .15)

    def test_prazo_separa_encerramento_real_de_atraso_em_aberto(self):
        resumo = {
            "executado": .5, "previsto": .6, "restante": .5,
            "termino_base": date(2026, 1, 10),
            "data_atualizacao": date(2026, 1, 15),
        }
        insuficiente = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=.1, avancos=[])
        self.assertIsNone(insuficiente["previsao_termino"])
        self.assertEqual(insuficiente["dias_atraso_aberto"], 5)
        self.assertIsNone(insuficiente["dias_diferenca_real"])
        resumo["termino_real"] = date(2026, 1, 12)
        encerrado = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=.1, avancos=[])
        self.assertEqual(encerrado["dias_diferenca_real"], 2)
        self.assertIsNone(encerrado["dias_atraso_aberto"])

    def test_projecao_exige_amostras_e_avanco_positivo(self):
        resumo = {
            "executado": .5, "previsto": .6, "restante": .5,
            "termino_base": date(2026, 3, 1), "data_atualizacao": date(2026, 2, 1),
        }
        avancos = [{"avanco_real": .1}, {"avanco_real": .1}, {"avanco_real": .1}]
        calculo = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=.1, avancos=avancos)
        self.assertTrue(calculo["projecao_confiavel"])
        self.assertEqual(calculo["previsao_termino"], date(2026, 3, 8))
        self.assertEqual(calculo["dias_diferenca_projetada"], 7)


class SerieCronogramaEtapa7Tests(TestCase):
    def test_serie_consulta_apenas_importacao_ativa_e_periodos_do_csv(self):
        antiga = ImportacaoCronograma.objects.create(status="CONCLUIDA", ativa=False)
        atual = ImportacaoCronograma.objects.create(status="CONCLUIDA", ativa=True)
        RegistroCronograma.objects.create(
            importacao=antiga, projeto="Obra A", semana=1, disciplina="RESUMO GERAL",
            data_atualizacao=date(2026, 1, 1), percentual_executado=.9,
        )
        for semana, inicio, data, real, previsto in [
            (1, date(2026, 1, 5), date(2026, 1, 11), .1, .2),
            (2, date(2026, 1, 12), date(2026, 1, 18), .2, .3),
        ]:
            RegistroCronograma.objects.create(
                importacao=atual, projeto="Obra A", semana=semana,
                disciplina="RESUMO GERAL", inicio_semana=inicio,
                data_atualizacao=data, percentual_executado=real,
                percentual_previsto=previsto,
            )
        with usar_importacao_ativa(atual):
            serie = obter_serie_resumo_geral(projeto="Obra A")
        self.assertEqual(len(serie), 2)
        self.assertEqual(serie[0]["inicio_semana"], date(2026, 1, 5))
        self.assertEqual(serie[0]["fim_semana"], date(2026, 1, 11))
        self.assertAlmostEqual(calcular_avancos_semanais(serie)[1]["avanco_real"], .1)
