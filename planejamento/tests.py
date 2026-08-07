from datetime import date

from django.test import SimpleTestCase

from planejamento.services.cronograma.agenda_semanal import resumir_programacao
from planejamento.services.cronograma.atividades import _status_atividade


class StatusAtividadeTests(SimpleTestCase):
    def test_concluida_prevalece(self):
        status, *_ = _status_atividade(
            executado=1.0,
            previsto=1.0,
            inicio_base=date(2026, 8, 1),
            termino_base=date(2026, 8, 5),
            data_atualizacao=date(2026, 8, 7),
        )
        self.assertEqual(status, "CONCLUIDA")

    def test_para_iniciar_antes_do_termino(self):
        status, *_ = _status_atividade(
            executado=0.0,
            previsto=0.20,
            inicio_base=date(2026, 8, 5),
            termino_base=date(2026, 8, 15),
            data_atualizacao=date(2026, 8, 7),
        )
        self.assertEqual(status, "PARA_INICIAR")

    def test_termino_vencido_e_atrasada(self):
        status, *_ = _status_atividade(
            executado=0.0,
            previsto=1.0,
            inicio_base=date(2026, 8, 1),
            termino_base=date(2026, 8, 6),
            data_atualizacao=date(2026, 8, 7),
        )
        self.assertEqual(status, "ATRASADA")

    def test_para_concluir_quando_previsto_100_e_ainda_no_prazo(self):
        status, *_ = _status_atividade(
            executado=0.80,
            previsto=1.0,
            inicio_base=date(2026, 8, 1),
            termino_base=date(2026, 8, 10),
            data_atualizacao=date(2026, 8, 7),
        )
        self.assertEqual(status, "PARA_CONCLUIR")

    def test_atrasada_por_avanco(self):
        status, *_ = _status_atividade(
            executado=0.40,
            previsto=0.60,
            inicio_base=date(2026, 8, 1),
            termino_base=date(2026, 8, 20),
            data_atualizacao=date(2026, 8, 7),
        )
        self.assertEqual(status, "ATRASADA")


class ResumoProgramacaoTests(SimpleTestCase):
    def test_resumo_conta_todos_os_itens_recebidos(self):
        programacao = [
            {"categoria_resumo": "ATRASADA"} for _ in range(120)
        ] + [
            {"categoria_resumo": "CONCLUIDA"} for _ in range(30)
        ]
        resumo = resumir_programacao(programacao)
        self.assertEqual(resumo["total"], 150)
        self.assertEqual(resumo["atrasadas"], 120)
        self.assertEqual(resumo["concluidas"], 30)
