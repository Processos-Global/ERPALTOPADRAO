from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastros.models import ChecklistProjetoGrupo
from obras.models import Obra
from projetos.models import AlteracaoProjeto


class AlteracoesProjetoTests(TestCase):
    def test_historico_pagina_no_banco_e_preserva_a_obra(self):
        usuario = get_user_model().objects.create_superuser(username="projetos-admin")
        self.client.force_login(usuario)
        obra = Obra.objects.create(nome="Projeto A", codigo="PROJ-A")
        grupo, _ = ChecklistProjetoGrupo.objects.get_or_create(
            nome="Arquitetura", tipo=ChecklistProjetoGrupo.TIPO_COMPATIBILIZACAO,
        )
        AlteracaoProjeto.objects.bulk_create([
            AlteracaoProjeto(obra=obra, disciplina=grupo, descricao=f"Registro {numero}", arquivo="projeto.pdf")
            for numero in range(16)
        ])
        url = reverse("projetos:alteracoes")
        with CaptureQueriesContext(connection) as consultas:
            primeira = self.client.get(url, {"obra": obra.pk})
        self.assertEqual(len(primeira.context["alteracoes"]), 15)
        self.assertContains(primeira, f"obra={obra.pk}&amp;page=2")
        self.assertTrue(any("LIMIT 15" in q["sql"] and "JOIN" in q["sql"] for q in consultas))
        segunda = self.client.get(url, {"obra": obra.pk, "page": 2})
        self.assertEqual([linha["obj"].descricao for linha in segunda.context["alteracoes"]], ["Registro 0"])
