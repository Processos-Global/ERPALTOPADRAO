from datetime import date
from io import BytesIO

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from pypdf import PdfReader

from obras.models import Obra, VistoriaItem
from obras.services.resumo_vistorias import montar_resumo_vistorias
from obras.views.vistorias import vistorias_resumo_pdf
from planejamento.models import AtividadePlanejamento, ImportacaoCronograma, RegistroCronograma


class ResumoVistoriasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser("vistoria-admin", "admin@example.test", "senha")
        cls.sem_permissao = User.objects.create_user("vistoria-sem", password="senha")
        cls.importacao = ImportacaoCronograma.objects.create(
            ativa=True, status=ImportacaoCronograma.Status.CONCLUIDA,
            nome_arquivo="cronograma-teste.csv",
        )
        cls.obra_a = Obra.objects.create(nome="Obra Alfa", codigo="ALFA")
        cls.obra_b = Obra.objects.create(nome="Obra Beta", codigo="BETA")
        cls.atividades = []
        for indice, (obra, disciplina) in enumerate((
            (cls.obra_a, "CHECKLIST PRE HABITE-SE"),
            (cls.obra_a, "POS HABITE-SE"),
            (cls.obra_b, "CHECKLIST PRE HABITE-SE"),
        )):
            atividade = AtividadePlanejamento.objects.create(
                obra=obra, chave=f"vistoria-teste-{indice}",
                disciplina=disciplina, nome_tarefa=f"Atividade {indice}",
            )
            cls.atividades.append(atividade)
            RegistroCronograma.objects.create(
                importacao=cls.importacao, obra=obra,
                atividade_planejamento=atividade,
                projeto=obra.nome, semana=1,
                data_atualizacao=date(2026, 10, 1),
                disciplina=disciplina, nome_tarefa=f"Atividade {indice}",
            )
        RegistroCronograma.objects.create(
            importacao=cls.importacao, obra=cls.obra_a,
            atividade_planejamento=cls.atividades[0],
            projeto=cls.obra_a.nome, semana=2,
            data_atualizacao=date(2026, 10, 8),
            disciplina="CHECKLIST PRE HABITE-SE", nome_tarefa="Atividade 0",
        )
        VistoriaItem.objects.create(atividade=cls.atividades[0], status="FEITO")
        VistoriaItem.objects.create(atividade=cls.atividades[1], status="NAO_FEITO")

    def test_deduplica_semana_e_separa_sem_avaliacao(self):
        dados = montar_resumo_vistorias({})
        self.assertEqual(dados["resumo"]["total"], 3)
        self.assertEqual(dados["resumo"]["realizadas"], 1)
        self.assertEqual(dados["resumo"]["nao_realizadas"], 2)
        self.assertEqual(dados["resumo"]["sem_avaliacao"], 1)
        self.assertEqual([linha["total"] for linha in dados["linhas"]], [2, 1])
        self.assertEqual({p["situacao"] for p in dados["pendencias"]},
                         {"Não feito", "Sem avaliação"})

    def test_filtros_de_obra_periodo_checklist_e_situacao(self):
        dados = montar_resumo_vistorias({
            "obra": str(self.obra_a.pk), "inicio": "2026-10-07", "fim": "2026-10-09",
            "tipo": "PRE", "situacao": "FEITO",
        })
        self.assertEqual(dados["resumo"]["total"], 1)
        self.assertEqual(dados["resumo"]["realizadas"], 1)
        self.assertEqual(dados["linhas"][0]["obra_nome"], "Obra Alfa")
        self.assertEqual(dados["pendencias"], [])
        sem_avaliacao = montar_resumo_vistorias({"situacao": "SEM_AVALIACAO"})
        self.assertEqual(sem_avaliacao["resumo"]["total"], 1)
        self.assertEqual(sem_avaliacao["linhas"][0]["obra_nome"], "Obra Beta")

    def test_pdf_repete_filtros_e_totais_da_tela(self):
        request = RequestFactory().get("/obras/vistorias/resumo/pdf/", {
            "obra": str(self.obra_a.pk), "tipo": "POS",
        })
        request.user = self.usuario
        resposta = vistorias_resumo_pdf(request)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertTrue(resposta.content.startswith(b"%PDF"))
        texto = " ".join(pagina.extract_text() for pagina in PdfReader(BytesIO(resposta.content)).pages)
        self.assertIn("Resumo Gerencial de Vistorias", texto)
        self.assertIn("Obra Alfa", texto)
        self.assertIn("Atividade 1", texto)
        self.assertNotIn("Obra Beta", texto)

    def test_pdf_exige_permissao_de_leitura(self):
        request = RequestFactory().get("/obras/vistorias/resumo/pdf/")
        request.user = self.sem_permissao
        with self.assertRaises(PermissionDenied):
            vistorias_resumo_pdf(request)
        request.user = AnonymousUser()
        resposta = vistorias_resumo_pdf(request)
        self.assertEqual(resposta.status_code, 302)
