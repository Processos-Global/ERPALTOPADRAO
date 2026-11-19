from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from obras.models import DiarioAtividadeAdicional, DiarioAtividadePlanejada, DiarioObra, Obra
from planejamento.models import AtividadePlanejamento, ImportacaoCronograma, RegistroCronograma


class DiarioCronogramaTest(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="diario_admin", email="diario@example.test", password="senha-teste"
        )
        self.client.force_login(self.usuario)
        self.obra = Obra.objects.create(nome="Obra Diário", codigo="OB-DIA-01")
        self.outra = Obra.objects.create(nome="Outra Obra Diário", codigo="OB-DIA-02")
        self.importacao = ImportacaoCronograma.objects.create(
            ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA
        )
        self.atividades = []
        for indice, (obra, disciplina) in enumerate([
            (self.obra, "Estrutura"),
            (self.obra, "CHECKLIST PRÉ HABITE-SE"),
            (self.obra, "PÓS HABITE-SE"),
            (self.outra, "Estrutura"),
        ]):
            atividade = AtividadePlanejamento.objects.create(
                obra=obra, chave=f"diario-atividade-{indice}",
                disciplina=disciplina, nome_tarefa=f"Tarefa {indice}",
            )
            RegistroCronograma.objects.create(
                importacao=self.importacao, obra=obra, atividade_planejamento=atividade,
                projeto=f"Projeto {obra.pk}", semana=9, inicio_semana=date(2026, 10, 12),
                disciplina=disciplina, nome_tarefa=f"Tarefa {indice}",
            )
            self.atividades.append(atividade)

    def test_api_usa_semana_importada_e_isola_obra(self):
        resposta = self.client.get(reverse("obras:diario_atividades_api"), {
            "obra": self.obra.pk, "data": "2026-10-14",
        })
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["semana"], 9)
        self.assertEqual({a["id"] for a in dados["atividades"]}, {a.pk for a in self.atividades[:3]})
        self.assertEqual({a["origem"] for a in dados["atividades"]}, {
            "SEMANAL", "PRE_HABITESE", "POS_HABITESE",
        })

    def test_salva_multiplas_atividades_e_adicional_sem_alterar_cronograma(self):
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-14",
            "servicos_executados": "Registro textual preservado",
            "atividades": [self.atividades[0].pk, self.atividades[1].pk],
            "adicional_descricao": "Atividade emergencial",
            "adicional_justificativa": "Necessidade em campo",
        })
        self.assertEqual(resposta.status_code, 302)
        diario = DiarioObra.objects.get(obra=self.obra)
        self.assertEqual(diario.servicos_executados, "Registro textual preservado")
        self.assertEqual(DiarioAtividadePlanejada.objects.filter(diario=diario).count(), 2)
        self.assertEqual(DiarioAtividadeAdicional.objects.get(diario=diario).justificativa, "Necessidade em campo")
        self.assertEqual(RegistroCronograma.objects.get(atividade_planejamento=self.atividades[0]).percentual_executado, None)

    def test_rejeita_atividade_de_outra_obra(self):
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-14",
            "servicos_executados": "Tentativa inválida",
            "atividades": [self.atividades[3].pk],
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DiarioObra.objects.filter(obra=self.obra).exists())

    def test_diario_antigo_permanece_sem_vinculos(self):
        diario = DiarioObra.objects.create(
            obra=self.obra, data=date(2026, 10, 14), servicos_executados="Histórico antigo",
        )
        resposta = self.client.get(reverse("obras:diario_lista"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, diario.servicos_executados)

    def test_edicao_preserva_vinculo_de_importacao_anterior_ate_remocao_explicita(self):
        diario = DiarioObra.objects.create(
            obra=self.obra, data=date(2026, 10, 14), servicos_executados="Registro original",
        )
        vinculo = DiarioAtividadePlanejada.objects.create(
            diario=diario, atividade=self.atividades[0], origem="SEMANAL",
            semana=9, inicio_semana=date(2026, 10, 12),
        )
        self.importacao.ativa = False
        self.importacao.save(update_fields=["ativa"])
        importacao_nova = ImportacaoCronograma.objects.create(
            ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA,
        )
        atividade_nova = AtividadePlanejamento.objects.create(
            obra=self.obra, chave="diario-importacao-nova", disciplina="Estrutura",
            nome_tarefa="Tarefa atual",
        )
        RegistroCronograma.objects.create(
            importacao=importacao_nova, obra=self.obra, atividade_planejamento=atividade_nova,
            projeto="Projeto atual", semana=10, inicio_semana=date(2026, 10, 12),
            disciplina="Estrutura", nome_tarefa="Tarefa atual",
        )

        url = reverse("obras:diario_editar", args=[diario.pk])
        resposta = self.client.get(url)
        self.assertContains(resposta, "Atividades de cronogramas anteriores")
        self.assertContains(resposta, self.atividades[0].nome_tarefa)
        self.assertContains(resposta, f'value="{vinculo.pk}"')

        resposta = self.client.post(url, {
            "obra": self.obra.pk, "data": "2026-10-14",
            "servicos_executados": "Registro atualizado",
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(DiarioAtividadePlanejada.objects.filter(pk=vinculo.pk).exists())

        resposta = self.client.post(url, {
            "obra": self.obra.pk, "data": "2026-10-14",
            "servicos_executados": "Registro atualizado",
            "remover_atividade_historica": [vinculo.pk],
        })
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(DiarioAtividadePlanejada.objects.filter(pk=vinculo.pk).exists())
