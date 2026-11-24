from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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
        resumo["executado"] = 1.0
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


class ProjecaoCronogramaTests(SimpleTestCase):
    def test_projecao_conta_os_quatro_ultimos_avancos_reais(self):
        resumo = {
            "restante": 0.20, "data_atualizacao": date(2026, 10, 12),
            "termino_base": date(2026, 11, 17),
        }
        avancos = [{"avanco_real": valor} for valor in (0.5, 0.1, 0, 0, 0.1)]
        prazos = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=0.05, avancos=avancos)
        self.assertEqual(prazos["previsao_termino"], date(2026, 11, 9))
        self.assertEqual(prazos["dias_diferenca_projetada"], -8)

    def test_projecao_fora_do_intervalo_de_datas_retorna_sem_previsao(self):
        resumo = {"restante": 0.9, "data_atualizacao": date(2026, 10, 12)}
        avancos = [{"avanco_real": valor} for valor in (0.1, 0.000001, 0.000001)]
        prazos = calcular_indicadores_prazo(resumo=resumo, media_avanco_real=0.000001, avancos=avancos)
        self.assertIsNone(prazos["previsao_termino"])
        self.assertFalse(prazos["projecao_confiavel"])

    def test_painel_exibe_progresso_e_distingue_desvios_do_prazo(self):
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get('/planejamento/')
        request.user = AnonymousUser()

        contexto = {
            "possui_dados": True,
            "resumo": {"previsto": 0.724, "executado": 0.632, "desvio": -0.092},
            "prazos": {
                "previsao_termino": date(2027, 3, 15),
                "dias_diferenca_real": 0, "dias_diferenca_projetada": -8,
                "dias_atraso_aberto": 12,
            },
        }
        html = render_to_string("planejamento/painel_cronograma.html", contexto, request=request)
        self.assertIn('aria-label="Previsto"', html)
        self.assertIn('aria-label="Realizado"', html)
        self.assertIn('value="0.7240"', html)
        self.assertIn('value="0.6320"', html)
        self.assertIn("15/03/2027", html)
        self.assertIn("8 dias adiantado", html)
        self.assertIn("No prazo", html)
        self.assertIn("12 dias em aberto", html)
        contexto["prazos"] = {"dias_diferenca_real": 12}
        html = render_to_string("planejamento/painel_cronograma.html", contexto, request=request)
        self.assertIn("12 dias atrasado", html)
        self.assertIn("Dados insuficientes", html)


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


class AbasCronogramaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create(username="cronograma", is_superuser=True)
        importacao = ImportacaoCronograma.objects.create(status="CONCLUIDA", ativa=True)
        RegistroCronograma.objects.create(
            importacao=importacao, projeto="Obra A", semana=1, disciplina="RESUMO GERAL",
            data_atualizacao=date(2026, 1, 11), inicio_semana=date(2026, 1, 5),
            percentual_executado=.1, percentual_previsto=.2,
        )
        RegistroCronograma.objects.create(
            importacao=importacao, projeto="Obra A", semana=1, disciplina="MARCOS",
            nome_tarefa="Marco exclusivo de teste", inicio_base=date(2026, 1, 1),
            termino_base=date(2026, 1, 20),
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse("planejamento:painel_cronograma")

    def test_visao_geral_carrega_apenas_a_curva(self):
        resposta = self.client.get(self.url, {"aba": "invalida"})
        self.assertContains(resposta, 'id="graficoCurvaS"')
        self.assertNotContains(resposta, 'id="graficoAvancoSemanal"')
        self.assertNotContains(resposta, "Marco exclusivo de teste")
        self.assertEqual(resposta.context["contadores_atividades"], {})
        self.assertEqual(resposta.context["marcos"], [])

    def test_curva_s_respeita_semana_de_referencia(self):
        RegistroCronograma.objects.create(
            importacao=ImportacaoCronograma.objects.get(ativa=True), projeto="Obra A",
            semana=2, disciplina="RESUMO GERAL", data_atualizacao=date(2026, 1, 18),
            inicio_semana=date(2026, 1, 12), percentual_executado=.9, percentual_previsto=.7,
        )
        resposta = self.client.get(self.url, {"aba": "visao-geral", "semana": 1})
        self.assertEqual([ponto["semana"] for ponto in resposta.context["serie"]], [1])

    def test_aba_marcos_preserva_filtros_e_carrega_seu_conteudo(self):
        resposta = self.client.get(self.url, {"aba": "marcos", "projeto": "Obra A", "semana": 1})
        self.assertContains(resposta, "Marco exclusivo de teste")
        self.assertContains(resposta, 'name="aba" value="marcos"')
        self.assertContains(resposta, 'projeto=Obra+A&amp;semana=1')
        self.assertNotContains(resposta, 'id="graficoCurvaS"')
        self.assertEqual(resposta.context["serie"], [])

    def test_avanco_semanal_usa_intervalo_importado_quando_distinto(self):
        resposta = self.client.get(self.url, {"aba": "semanal"})
        self.assertContains(resposta, 'id="graficoAvancoSemanal"')
        self.assertNotContains(resposta, 'id="graficoAvancoMensal"')
        self.assertEqual(resposta.context["avancos"][0]["rotulo_intervalo"], "05/01 – 11/01")

    def test_avanco_semanal_identifica_o_primeiro_retrato_como_base(self):
        RegistroCronograma.objects.create(
            importacao=ImportacaoCronograma.objects.get(ativa=True), projeto="Obra A",
            semana=3, disciplina="RESUMO GERAL", data_atualizacao=date(2026, 1, 25),
            inicio_semana=date(2026, 1, 19), percentual_executado=.35, percentual_previsto=.45,
        )
        resposta = self.client.get(self.url, {"aba": "semanal"})
        base, posterior = resposta.context["avancos"]
        self.assertTrue(base["base_acumulada"])
        self.assertFalse(posterior["base_acumulada"])
        self.assertTrue(posterior["intervalo_entre_medicoes"])
        self.assertAlmostEqual(posterior["avanco_real"], .25)

    def test_inicio_repetido_nao_gera_intervalo_semanal_falso(self):
        RegistroCronograma.objects.create(
            importacao=ImportacaoCronograma.objects.get(ativa=True), projeto="Obra A",
            semana=2, disciplina="RESUMO GERAL", data_atualizacao=date(2026, 1, 18),
            inicio_semana=date(2026, 1, 5), percentual_executado=.2, percentual_previsto=.3,
        )
        resposta = self.client.get(self.url, {"aba": "semanal"})
        self.assertEqual([ponto["rotulo_intervalo"] for ponto in resposta.context["avancos"]], ["", ""])

    def test_marcos_distinguem_adiantado_no_prazo_e_futuro(self):
        importacao = ImportacaoCronograma.objects.get(ativa=True)
        for nome, inicio, termino, termino_real, realizado in (
            ("Antecipado", date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 8), 1),
            ("Em curso", date(2026, 1, 1), date(2026, 1, 20), None, .5),
            ("A iniciar", date(2026, 1, 15), date(2026, 1, 20), None, 0),
        ):
            RegistroCronograma.objects.create(
                importacao=importacao, projeto="Obra A", semana=1, disciplina="MARCOS",
                nome_tarefa=nome, inicio_base=inicio, termino_base=termino,
                termino_real=termino_real, percentual_concluida=realizado,
                data_atualizacao=date(2026, 1, 11),
            )

        resposta = self.client.get(self.url, {"aba": "marcos"})
        marcos = {marco["nome"]: marco for marco in resposta.context["marcos"]}
        self.assertEqual(marcos["Antecipado"]["situacao_rotulo"], "Concluído adiantado")
        self.assertEqual(marcos["Antecipado"]["situacao"], "CONCLUIDO")
        self.assertEqual(marcos["Antecipado"]["variacao_dias"], -2)
        self.assertContains(resposta, "08/01/2026")
        self.assertEqual(marcos["Em curso"]["situacao_rotulo"], "No prazo")
        self.assertEqual(marcos["A iniciar"]["situacao_rotulo"], "Futuro")
