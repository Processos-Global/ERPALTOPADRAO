from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from obras.models import DiarioAtividadeAdicional, DiarioAtividadePlanejada, DiarioObra, Obra
from planejamento.models import AtividadePlanejamento, ImportacaoCronograma, RegistroCronograma
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


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
                inicio_base=date(2026, 10, 12),
                percentual_previsto_tarefa="0.2",
                disciplina=disciplina, nome_tarefa=f"Tarefa {indice}",
            )
            self.atividades.append(atividade)

    def _api(self, data, obra=None):
        return self.client.get(reverse("obras:diario_atividades_api"), {
            "obra": (obra or self.obra).pk, "data": data,
        })

    def test_lista_pagina_historico_preservando_filtros(self):
        inicio = date(2025, 1, 1)
        DiarioObra.objects.bulk_create([
            DiarioObra(obra=self.obra, data=inicio + timedelta(days=dia))
            for dia in range(301)
        ])
        DiarioObra.objects.create(obra=self.outra, data=inicio, servicos_executados="Diário de outra obra")
        url = reverse("obras:diario_lista")
        filtros = {"obra": self.obra.pk, "inicio": inicio.isoformat()}
        primeira = self.client.get(url, filtros)
        ultima = self.client.get(url, {**filtros, "page": 11})

        self.assertEqual(len(primeira.context["diarios"]), 30)
        self.assertContains(primeira, f"obra={self.obra.pk}&amp;inicio=2025-01-01&amp;page=2")
        self.assertEqual([diario.data for diario in ultima.context["diarios"]], [inicio])
        self.assertNotContains(ultima, "Diário de outra obra")

    def test_formulario_separa_checklists_sem_categoria_vazia(self):
        diario = DiarioObra.objects.create(obra=self.obra, data=date(2026, 10, 14))
        resposta = self.client.get(reverse("obras:diario_editar", args=[diario.pk]))
        self.assertContains(resposta, '<summary>Pré Habite-se</summary>', html=True)
        self.assertContains(resposta, '<summary>Pós Habite-se</summary>', html=True)
        self.assertContains(resposta, '<summary>Outras atividades</summary>', html=True)

        outro_diario = DiarioObra.objects.create(obra=self.outra, data=diario.data)
        resposta = self.client.get(reverse("obras:diario_editar", args=[outro_diario.pk]))
        self.assertNotContains(resposta, '<summary>Pré Habite-se</summary>', html=True)
        self.assertContains(resposta, '<summary>Outras atividades</summary>', html=True)

    def test_api_usa_semana_importada_e_isola_obra(self):
        resposta = self._api("2026-10-14")
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["semana"], 9)
        self.assertEqual({a["id"] for a in dados["atividades"]}, {a.pk for a in self.atividades[:3]})
        self.assertEqual({a["origem"] for a in dados["atividades"]}, {
            "SEMANAL", "PRE_HABITESE", "POS_HABITESE",
        })
        self.assertEqual(
            {a["id"] for a in self._api("2026-10-14", self.outra).json()["atividades"]},
            {self.atividades[3].pk},
        )

    def test_usa_avanco_do_periodo_e_exclui_reprogramacao_futura(self):
        for indice, atividade in enumerate(self.atividades[:3]):
            RegistroCronograma.objects.create(
                importacao=self.importacao, obra=self.obra, atividade_planejamento=atividade,
                projeto=f"Projeto {self.obra.pk}", semana=52, inicio_semana=date(2026, 10, 5),
                disciplina=atividade.disciplina, nome_tarefa=atividade.nome_tarefa,
                percentual_previsto_tarefa="0.1" if indice == 0 else "0.2",
                percentual_concluida="0.1",
                inicio_base=date(2026, 10, 5),
                inicio_real=date(2026, 10, 6),
            )
        RegistroCronograma.objects.filter(
            atividade_planejamento_id__in=[a.pk for a in self.atividades[:3]], semana=9,
        ).update(
            percentual_concluida="0.1", inicio_base=date(2026, 10, 5), inicio_real=date(2026, 10, 6),
        )
        RegistroCronograma.objects.filter(
            atividade_planejamento=self.atividades[1], semana=9,
        ).update(reprogramada=True, inicio_base=date(2026, 10, 26))
        RegistroCronograma.objects.filter(
            atividade_planejamento=self.atividades[2], semana=9,
        ).update(termino_base=date(2026, 10, 16))

        self.assertEqual(
            {a["id"] for a in self._api("2026-10-14").json()["atividades"]},
            {self.atividades[0].pk, self.atividades[2].pk},
        )
        self.assertEqual(len(self._api("2026-10-11").json()["atividades"]), 3)
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-14", "atividades": [self.atividades[1].pk],
        })
        self.assertContains(resposta, "As atividades selecionadas não pertencem à obra e semana")
        self.assertFalse(DiarioObra.objects.exists())

    def test_separa_numero_de_semana_repetido_em_anos_diferentes(self):
        antiga = AtividadePlanejamento.objects.create(
            obra=self.obra, chave="diario-atividade-ano-anterior", disciplina="Estrutura",
            nome_tarefa="Tarefa do ano anterior",
        )
        RegistroCronograma.objects.create(
            importacao=self.importacao, obra=self.obra, atividade_planejamento=antiga,
            projeto=f"Projeto {self.obra.pk}", semana=9, inicio_semana=date(2025, 10, 13),
            inicio_base=date(2025, 10, 14),
            disciplina=antiga.disciplina, nome_tarefa=antiga.nome_tarefa, percentual_previsto_tarefa="0.5",
        )
        anterior = self._api("2025-10-19").json()
        atual = self._api("2026-10-18").json()
        self.assertEqual(anterior["semana"], atual["semana"])
        self.assertEqual(anterior["inicio_semana"], "2025-10-13")
        self.assertEqual(atual["inicio_semana"], "2026-10-12")
        self.assertEqual({a["id"] for a in anterior["atividades"]}, {antiga.pk})
        self.assertEqual({a["id"] for a in atual["atividades"]}, {a.pk for a in self.atividades[:3]})
        self.assertIsNone(self._api("2026-10-19").json()["semana"])

    def test_retrato_legado_duplicado_usa_a_linha_mais_recente_da_atividade(self):
        atividade = self.atividades[0]
        RegistroCronograma.objects.create(
            importacao=self.importacao, obra=self.obra, atividade_planejamento=atividade,
            projeto=f"Projeto {self.obra.pk}", semana=9, inicio_semana=date(2026, 10, 12),
            inicio_base=date(2026, 10, 26), termino_base=date(2026, 10, 30),
            disciplina=atividade.disciplina, nome_tarefa=atividade.nome_tarefa, reprogramada=True,
        )
        ids = {a["id"] for a in self._api("2026-10-14").json()["atividades"]}
        self.assertEqual(ids, {a.pk for a in self.atividades[1:3]})

    def test_primeiro_retrato_exige_evidencia_de_programacao_na_semana(self):
        registros = RegistroCronograma.objects.filter(importacao=self.importacao, obra=self.obra)
        registros.filter(atividade_planejamento=self.atividades[0]).update(
            percentual_previsto_tarefa="1", percentual_concluida="1",
            inicio_real=date(2026, 9, 1), termino_real=date(2026, 10, 11),
            termino_base=date(2026, 10, 16),
        )
        registros.filter(atividade_planejamento=self.atividades[1]).update(
            inicio_base=None, inicio_real=date(2026, 9, 1), percentual_concluida="0.15",
        )
        registros.filter(atividade_planejamento=self.atividades[2]).update(
            inicio_base=date(2026, 10, 5), termino_base=date(2026, 10, 23),
            inicio_real=date(2026, 10, 6),
        )
        dados = self._api("2026-10-14").json()
        self.assertEqual(dados["semana"], 9)
        self.assertEqual({a["id"] for a in dados["atividades"]}, {self.atividades[2].pk})

    def test_avanco_acumulado_nao_atribui_semana_ausente_ao_retrato_seguinte(self):
        registros = RegistroCronograma.objects.filter(importacao=self.importacao, obra=self.obra)
        registros.update(inicio_base=None)
        for atividade in self.atividades[:2]:
            RegistroCronograma.objects.create(
                importacao=self.importacao, obra=self.obra, atividade_planejamento=atividade,
                projeto=f"Projeto {self.obra.pk}", semana=7, inicio_semana=date(2026, 9, 28),
                disciplina=atividade.disciplina, nome_tarefa=atividade.nome_tarefa,
                percentual_concluida="0.1",
            )
            registros.filter(atividade_planejamento=atividade, semana=9).update(
                percentual_concluida="0.8",
            )
        registros.filter(atividade_planejamento=self.atividades[0], semana=9).update(
            percentual_concluida="1", termino_real=date(2026, 10, 11),
            inicio_base=date(2026, 10, 12),
        )
        self.assertEqual(self._api("2026-10-14").json()["atividades"], [])

    def test_sem_programacao_e_sem_importacao_ativa(self):
        RegistroCronograma.objects.filter(importacao=self.importacao, obra=self.obra).update(
            percentual_previsto_tarefa=None,
            inicio_base=None,
            inicio_real=date(2026, 9, 1),
            data_atualizacao=date(2026, 10, 18),
        )
        dados = self._api("2026-10-14").json()
        self.assertEqual(dados["semana"], 9)
        self.assertEqual(dados["atividades"], [])
        self.importacao.ativa = False
        self.importacao.save(update_fields=["ativa"])
        self.assertIsNone(self._api("2026-10-14").json()["semana"])

    def test_salva_multiplas_atividades_sem_textos_manuais(self):
        url = reverse("obras:diario_novo")
        formulario = self.client.get(url)
        for campo in ("servicos_executados", "observacoes", "adicional_descricao", "adicional_justificativa"):
            self.assertNotContains(formulario, f'name="{campo}"')
        resposta = self.client.post(url, {
            "obra": self.obra.pk, "data": "2026-10-14",
            "atividades": [self.atividades[0].pk, self.atividades[1].pk],
            "clima": DiarioObra.Clima.NUBLADO, "efetivo": "3",
            "equipe_presente": "Equipe A", "ocorrencias": "Ocorrência registrada",
        })
        self.assertEqual(resposta.status_code, 302)
        diario = DiarioObra.objects.get(obra=self.obra)
        self.assertEqual(diario.servicos_executados, "")
        self.assertEqual(diario.observacoes, "")
        self.assertEqual(diario.efetivo, 3)
        self.assertEqual(diario.clima, DiarioObra.Clima.NUBLADO)
        self.assertEqual(diario.equipe_presente, "Equipe A")
        self.assertEqual(diario.ocorrencias, "Ocorrência registrada")
        self.assertEqual(DiarioAtividadePlanejada.objects.filter(diario=diario).count(), 2)
        self.assertFalse(DiarioAtividadeAdicional.objects.filter(diario=diario).exists())
        self.assertIsNone(RegistroCronograma.objects.get(atividade_planejamento=self.atividades[0]).percentual_executado)

    def test_edicao_preserva_informacoes_legadas_e_ignora_campos_removidos_no_post(self):
        diario = DiarioObra.objects.create(
            obra=self.obra, data=date(2026, 10, 14), servicos_executados="Serviço histórico",
            observacoes="Observação histórica",
        )
        adicional = DiarioAtividadeAdicional.objects.create(
            diario=diario, descricao="Atividade legada", justificativa="Necessidade em campo",
        )
        url = reverse("obras:diario_editar", args=[diario.pk])
        formulario = self.client.get(url)
        self.assertNotContains(formulario, 'name="remover_adicional"')
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-15",
        })
        self.assertEqual(resposta.status_code, 302)
        resposta = self.client.post(url, {
            "obra": self.obra.pk, "data": "2026-10-14", "ocorrencias": "Ocorrência atualizada",
            "servicos_executados": "Ignorar serviço", "observacoes": "Ignorar observação",
            "remover_adicional": [adicional.pk], "adicional_descricao": "Ignorar adicional",
        })
        self.assertEqual(resposta.status_code, 302)
        diario.refresh_from_db()
        self.assertEqual(diario.servicos_executados, "Serviço histórico")
        self.assertEqual(diario.observacoes, "Observação histórica")
        self.assertEqual(diario.ocorrencias, "Ocorrência atualizada")
        self.assertEqual(list(diario.atividades_adicionais.values_list("pk", flat=True)), [adicional.pk])
        lista = self.client.get(reverse("obras:diario_lista"))
        for texto in ("Serviço histórico", "Observação histórica", "Atividade legada", "Necessidade em campo"):
            self.assertContains(lista, texto)

    @override_settings(USE_THOUSAND_SEPARATOR=True, THOUSAND_SEPARATOR=".")
    def test_atributos_de_formulario_mantem_ids_e_efetivo_sem_formatacao_local(self):
        obra = Obra.objects.create(pk=1234, nome="Obra 1234", codigo="OB1234")
        atividade = AtividadePlanejamento.objects.create(
            pk=1234, obra=obra, chave="diario-1234", disciplina="Estrutura", nome_tarefa="Tarefa 1234",
        )
        antiga = AtividadePlanejamento.objects.create(
            pk=1235, obra=obra, chave="diario-1235", disciplina="Estrutura", nome_tarefa="Tarefa 1235",
        )
        RegistroCronograma.objects.create(
            importacao=self.importacao, obra=obra, projeto="Projeto 1234", semana=9,
            inicio_semana=date(2026, 10, 12), inicio_base=date(2026, 10, 14),
            atividade_planejamento=atividade, disciplina="Estrutura", nome_tarefa=atividade.nome_tarefa,
        )
        diario = DiarioObra.objects.create(obra=obra, data=date(2026, 10, 14), efetivo=2000)
        DiarioAtividadePlanejada.objects.create(
            pk=2345, diario=diario, atividade=antiga, semana=8, inicio_semana=date(2026, 10, 5),
            origem=DiarioAtividadePlanejada.Origem.SEMANAL,
        )
        resposta = self.client.get(reverse("obras:diario_editar", args=[diario.pk]))
        self.assertContains(resposta, 'value="1234" selected', msg_prefix="Valor da obra")
        self.assertContains(resposta, 'name="atividades" value="1234"')
        self.assertContains(resposta, 'name="efetivo" value="2000"')
        self.assertContains(resposta, 'name="remover_atividade_historica" value="2345"')
        self.assertContains(resposta, 'data-diario-vinculo-historico="1235"')
        lista = self.client.get(reverse("obras:diario_lista"), {"obra": obra.pk})
        self.assertContains(lista, 'value="1234" selected')

    def test_rejeita_atividade_de_outra_obra(self):
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-14",
            "atividades": [self.atividades[3].pk],
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DiarioObra.objects.filter(obra=self.obra).exists())

    def test_rejeita_id_de_atividade_invalido(self):
        for invalido in ("²", "9" * 4301):
            with self.subTest(tamanho=len(invalido)):
                resposta = self.client.post(reverse("obras:diario_novo"), {
                    "obra": self.obra.pk, "data": "2026-10-14",
                    "atividades": [str(self.atividades[0].pk), invalido],
                })
                self.assertContains(resposta, "As atividades selecionadas não pertencem à obra e semana")
        self.assertFalse(DiarioObra.objects.exists())

    def test_rejeita_id_de_obra_invalido(self):
        params = {"obra": "²", "data": "2026-10-14"}
        resposta = self.client.get(reverse("obras:diario_atividades_api"), params)
        self.assertEqual(resposta.json()["atividades"], [])
        resposta = self.client.post(reverse("obras:diario_novo"), params)
        self.assertContains(resposta, "Selecione a obra do diário")
        self.assertFalse(DiarioObra.objects.exists())

    def test_post_nao_reescreve_semana_de_vinculo_historico_com_atividade_disponivel(self):
        diario = DiarioObra.objects.create(obra=self.obra, data=date(2026, 10, 14))
        vinculo = DiarioAtividadePlanejada.objects.create(
            diario=diario, atividade=self.atividades[0], origem="SEMANAL",
            semana=8, inicio_semana=date(2026, 10, 12),
        )
        resposta = self.client.post(reverse("obras:diario_editar", args=[diario.pk]), {
            "obra": self.obra.pk, "data": "2026-10-14", "atividades": [self.atividades[0].pk],
        })
        self.assertContains(resposta, "As atividades selecionadas não pertencem à obra e semana")
        vinculo.refresh_from_db()
        self.assertEqual(vinculo.semana, 8)

    def test_leitura_e_criacao_exigem_as_permissoes_existentes(self):
        usuario = get_user_model().objects.create_user(username="diario_leitor")
        self.client.force_login(usuario)
        self.assertEqual(self._api("2026-10-14").status_code, 403)
        permissao = PermissaoModulo.objects.create(
            usuario=usuario, modulo=ModuloSistema.OBRAS, nivel=NivelPermissao.LEITURA,
        )
        self.assertEqual(self._api("2026-10-14").status_code, 200)
        permissao.nivel = NivelPermissao.EDICAO
        permissao.save(update_fields=["nivel"])
        resposta = self.client.post(reverse("obras:diario_novo"), {
            "obra": self.obra.pk, "data": "2026-10-14",
        })
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(DiarioObra.objects.exists())

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
