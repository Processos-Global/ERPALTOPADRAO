from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import (
    AdjudicacaoCompra,
    CompatibilizacaoItem,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    GrandeFornecedorItem,
    GrandeFornecedorParticipante,
    GrandeFornecedorProcesso,
    HistoricoProcessoCompra,
    NecessidadeCompra,
    PedidoCompra,
    PedidoCompraAnexo,
    ProcessoCompra,
    TransicaoEtapaCompra,
)
from obras.models import Obra


class DesempenhoViewsComprasTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(username="compras-admin")
        cls.obra = Obra.objects.create(pk=2345, nome="Obra A", codigo="COMP-A")
        cls.outra_obra = Obra.objects.create(nome="Obra B", codigo="COMP-B")
        cls.fornecedor = Fornecedor.objects.create(nome="Fornecedor de teste")

    def setUp(self):
        self.client.force_login(self.usuario)

    @override_settings(USE_THOUSAND_SEPARATOR=True)
    def test_lista_pagina_apos_filtros_e_mantem_sla_do_conjunto_filtrado(self):
        processos = ProcessoCompra.objects.bulk_create([
            ProcessoCompra(pk=100 + i, obra=self.obra, numero=f"PC-PAG-{i:02}", titulo="Compra teste")
            for i in range(52)
        ])
        outro = ProcessoCompra.objects.create(
            obra=self.outra_obra, numero="PC-PAG-OUTRO", titulo="Compra teste"
        )
        inicio = timezone.now() - timedelta(days=10)
        TransicaoEtapaCompra.objects.bulk_create([
            TransicaoEtapaCompra(
                processo=processo,
                etapa=ProcessoCompra.Etapa.COTACAO,
                iniciada_em=inicio,
                contagem="CORRIDOS",
                prazo_dias=3,
                limite_em=timezone.localdate(inicio) + timedelta(days=3),
            )
            for processo in [*processos[:-1], outro]
        ])
        url = reverse("compras:lista_processos")
        filtros = {"obra": self.obra.pk, "q": "Compra teste", "sla": "ATRASADO"}
        primeira = self.client.get(url, filtros)
        segunda = self.client.get(url, {**filtros, "page": 2})
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertLess(len(primeira.context["processos"]), 51)
        self.assertTrue(segunda.context["processos"])
        exibidos = [processo.pk for processo in primeira.context["processos"]]
        exibidos += [processo.pk for processo in segunda.context["processos"]]
        self.assertEqual(exibidos, [processo.pk for processo in reversed(processos[:-1])])
        self.assertEqual(segunda.context["sla_resumo"]["processos_atrasados"], 51)
        self.assertEqual(segunda.context["sla_resumo"]["maior_atraso"], 7)
        self.assertContains(primeira, "sla=ATRASADO")
        self.assertContains(primeira, 'value="2345" selected')
        self.assertContains(primeira, "obra=2345")

    def test_pedidos_filtram_antes_da_paginacao(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-PEDIDOS", titulo="Pedidos"
        )
        pedidos = PedidoCompra.objects.bulk_create([
            PedidoCompra(
                pk=200 + i, obra=self.obra, processo=processo, fornecedor=self.fornecedor,
                numero=f"PED-PAG-{i:02}", status=PedidoCompra.Status.CONFIRMADO,
            )
            for i in range(36)
        ])
        PedidoCompra.objects.create(
            obra=self.obra, processo=processo, fornecedor=self.fornecedor,
            numero="PED-PAG-OUTRO", status=PedidoCompra.Status.CANCELADO,
        )
        url = reverse("compras:lista_pedidos")
        filtros = {"obra": self.obra.pk, "status": PedidoCompra.Status.CONFIRMADO, "q": "PED-PAG"}
        primeira = self.client.get(url, filtros)
        segunda = self.client.get(url, {**filtros, "page": 2})
        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertLess(len(primeira.context["pedidos"]), 36)
        self.assertTrue(segunda.context["pedidos"])
        exibidos = [pedido.pk for pedido in primeira.context["pedidos"]]
        exibidos += [pedido.pk for pedido in segunda.context["pedidos"]]
        self.assertEqual(exibidos, [pedido.pk for pedido in reversed(pedidos)])
        self.assertContains(primeira, "status=CONFIRMADO")

    def test_pedidos_carregam_os_autores_dos_anexos_na_mesma_consulta(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-ANEXOS", titulo="Pedido com anexos",
        )
        pedido = PedidoCompra.objects.create(
            obra=self.obra, processo=processo, fornecedor=self.fornecedor, numero="PED-ANEXOS",
        )
        url = reverse("compras:lista_pedidos")
        with CaptureQueriesContext(connection) as sem_anexos:
            self.assertEqual(self.client.get(url).status_code, 200)
        for indice in range(5):
            autor = get_user_model().objects.create_user(username=f"autor-anexo-{indice}")
            PedidoCompraAnexo.objects.create(
                pedido=pedido, arquivo=f"compras/pedidos/anexo-{indice}.pdf", enviado_por=autor,
            )
        with CaptureQueriesContext(connection) as com_anexos:
            resposta = self.client.get(url)

        for indice in range(5):
            self.assertContains(resposta, f"autor-anexo-{indice}")
        tabela = connection.ops.quote_name(get_user_model()._meta.db_table)
        self.assertEqual(
            sum(f"FROM {tabela}" in consulta["sql"] for consulta in com_anexos),
            sum(f"FROM {tabela}" in consulta["sql"] for consulta in sem_anexos),
        )

    def test_detalhe_preserva_saldos_sem_reconsultar_adjudicacoes_por_item(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-DETALHE", titulo="Detalhe"
        )
        necessidades = NecessidadeCompra.objects.bulk_create([
            NecessidadeCompra(
                pk=300 + i, processo=processo, descricao=f"Item {i}", unidade="UN",
                quantidade_necessaria=5, quantidade_incluida=5,
            )
            for i in range(6)
        ])
        cotacao = CotacaoFornecedor.objects.create(processo=processo, fornecedor=self.fornecedor)
        item = CotacaoFornecedorItem.objects.create(
            cotacao=cotacao, necessidade=necessidades[0], quantidade=5, valor_unitario_cotado=10
        )
        for cancelada, qtd in ((False, 2), (True, 3)):
            AdjudicacaoCompra.objects.create(
                processo=processo, necessidade=necessidades[0], cotacao=cotacao,
                item_cotado=item, quantidade=qtd, valor_unitario_final=8, cancelada=cancelada,
            )
        pedido = PedidoCompra.objects.create(
            processo=processo, obra=self.obra, fornecedor=self.fornecedor, numero="PED-DETALHE"
        )
        anexo = PedidoCompraAnexo.objects.create(
            pedido=pedido, arquivo="compras/pedidos/sintetico.pdf", enviado_por=self.usuario
        )
        evento = HistoricoProcessoCompra.objects.create(
            processo=processo, usuario=self.usuario, tipo="TESTE", descricao="Evento de teste"
        )
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(reverse("compras:detalhe_processo", args=[processo.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context["quantidade_adjudicada"], Decimal("2"))
        self.assertEqual(resposta.context["necessidades"][0].saldo, Decimal("3"))
        self.assertEqual(resposta.context["valor_total_selecionado"], Decimal("16"))
        self.assertEqual(
            [(doc["pk"], doc["nome"], doc["responsavel"]) for doc in resposta.context["documentos_processo"]],
            [(anexo.pk, "sintetico.pdf", self.usuario)],
        )
        self.assertIn(evento, resposta.context["historico"])
        tabela = connection.ops.quote_name(AdjudicacaoCompra._meta.db_table)
        consultas_adjudicacao = [consulta for consulta in consultas if f"FROM {tabela}" in consulta["sql"]]
        self.assertLessEqual(len(consultas_adjudicacao), 2)

    def test_aprovacao_reusa_ultima_analise_tecnica_e_respeita_revisao_da_oferta(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-APROVACAO", titulo="Aprovação",
            etapa_atual=ProcessoCompra.Etapa.APROVACAO,
            status=ProcessoCompra.Status.AGUARDANDO_APROVACAO,
        )
        cotacao = CotacaoFornecedor.objects.create(
            processo=processo, fornecedor=self.fornecedor, enviada_aprovacao_em=timezone.now()
        )
        itens = []
        for i in range(8):
            necessidade = NecessidadeCompra.objects.create(
                processo=processo, descricao=f"Item {i}", unidade="UN",
                quantidade_necessaria=1, quantidade_incluida=1,
            )
            item = CotacaoFornecedorItem.objects.create(
                cotacao=cotacao, necessidade=necessidade, quantidade=1, valor_unitario_cotado=10
            )
            itens.append(item)
            CompatibilizacaoItem.objects.create(item_cotado=item, resultado=CompatibilizacaoItem.Resultado.APROVADO)
        CompatibilizacaoItem.objects.create(item_cotado=itens[0], resultado=CompatibilizacaoItem.Resultado.REPROVADO)
        CotacaoFornecedorItem.objects.filter(pk=itens[1].pk).update(atualizado_em=timezone.now() + timedelta(seconds=1))
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(reverse("compras:detalhe_processo", args=[processo.pk]))
        self.assertEqual(resposta.status_code, 200)
        elegiveis = [
            oferta["item"].pk
            for linha in resposta.context["matriz_cotacao"]
            for oferta in linha["ofertas"]
            if oferta["elegivel_aprovacao"]
        ]
        self.assertEqual(elegiveis, [item.pk for item in itens[2:]])
        tabela = connection.ops.quote_name(CompatibilizacaoItem._meta.db_table)
        consultas_diretas = [
            consulta for consulta in consultas
            if f"FROM {tabela}" in consulta["sql"] and "(SELECT" not in consulta["sql"]
        ]
        self.assertEqual(len(consultas_diretas), 1)

    def test_contagens_dashboard_independentes_das_relacoes_multiplas(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-CONTAGENS", titulo="Contagens", fluxo_grande_fornecedor=True
        )
        fluxo = GrandeFornecedorProcesso.objects.create(processo=processo)
        outro = Fornecedor.objects.create(nome="Fornecedor dois")
        for fornecedor in (self.fornecedor, outro):
            GrandeFornecedorParticipante.objects.create(fluxo=fluxo, fornecedor=fornecedor)
            CotacaoFornecedor.objects.create(processo=processo, fornecedor=fornecedor)
        for i in range(3):
            GrandeFornecedorItem.objects.create(fluxo=fluxo, item=f"Item GF {i}", quantidade=1)
        for i in range(4):
            NecessidadeCompra.objects.create(
                processo=processo, descricao=f"Item padrão {i}", unidade="UN",
                quantidade_necessaria=1, quantidade_incluida=1,
            )
        resposta = self.client.get(reverse("compras:dashboard"), {"obra": self.obra.pk})
        card, = [p for coluna in resposta.context["colunas"] for p in coluna["processos"]]
        self.assertEqual(
            (card.qtd_itens, card.qtd_fornecedores, card.qtd_itens_grande_fornecedor, card.qtd_fornecedores_grande_fornecedor),
            (4, 2, 3, 2),
        )

    def test_dashboard_limita_cartoes_sem_perder_totais_ou_filtros(self):
        processos = ProcessoCompra.objects.bulk_create([
            ProcessoCompra(
                obra=self.obra, numero=f"PC-BOARD-{indice:03}",
                titulo="Painel da obra A", status=ProcessoCompra.Status.RASCUNHO,
            )
            for indice in range(75)
        ])
        ProcessoCompra.objects.create(
            obra=self.outra_obra, numero="PC-BOARD-OUTRA", titulo="Outra obra",
        )
        url = reverse("compras:dashboard")
        resposta = self.client.get(url, {"obra": self.obra.pk, "q": "Painel"})
        self.assertEqual(resposta.status_code, 200)
        coluna = next(c for c in resposta.context["colunas"] if c["chave"] == "RASCUNHO")
        self.assertEqual(coluna["quantidade_total"], 75)
        self.assertEqual(len(coluna["processos"]), 30)
        self.assertEqual(
            [p.pk for p in coluna["processos"]],
            [p.pk for p in reversed(processos[-30:])],
        )
        self.assertEqual(resposta.context["ativos"], 75)
        self.assertContains(resposta, "Exibindo 30 de 75 processos")
        self.assertContains(resposta, "Ver lista completa")
        self.assertContains(resposta, "obra=2345")
        self.assertNotContains(resposta, "PC-BOARD-OUTRA")

    def test_detalhe_mantem_formularios_das_propostas_conforme_a_fase_da_oferta(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="PC-FORMULARIOS", titulo="Formulários",
            etapa_atual=ProcessoCompra.Etapa.COMPATIBILIZACAO,
            status=ProcessoCompra.Status.EM_COMPATIBILIZACAO,
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Item", unidade="UN",
            quantidade_necessaria=1, quantidade_incluida=1,
        )
        rascunho = CotacaoFornecedor.objects.create(processo=processo, fornecedor=self.fornecedor)
        analise = CotacaoFornecedor.objects.create(
            processo=processo, fornecedor=Fornecedor.objects.create(nome="Fornecedor da análise"),
            enviada_compatibilizacao_em=timezone.now(),
        )
        negociacao = CotacaoFornecedor.objects.create(
            processo=processo, fornecedor=Fornecedor.objects.create(nome="Fornecedor da negociação"),
            enviada_compatibilizacao_em=timezone.now(), enviada_negociacao_em=timezone.now(),
        )
        CotacaoFornecedorItem.objects.create(
            cotacao=analise, necessidade=necessidade, quantidade=1, valor_unitario_cotado=10,
        )
        item_negociacao = CotacaoFornecedorItem.objects.create(
            cotacao=negociacao, necessidade=necessidade, quantidade=1, valor_unitario_cotado=8,
        )
        CompatibilizacaoItem.objects.create(
            item_cotado=item_negociacao, resultado=CompatibilizacaoItem.Resultado.APROVADO,
        )

        resposta = self.client.get(reverse("compras:detalhe_processo", args=[processo.pk]))
        self.assertEqual(resposta.status_code, 200)
        formularios = {bloco["cotacao"].pk: bloco["form"] for bloco in resposta.context["propostas_forms"]}
        self.assertIsNotNone(formularios[rascunho.pk])
        self.assertIsNone(formularios[analise.pk])
        self.assertIsNone(formularios[negociacao.pk])
        self.assertEqual(
            [bloco["cotacao"].pk for bloco in resposta.context["compatibilizacoes_forms"]], [analise.pk]
        )
        self.assertEqual(
            [linha["item"].pk for linha in resposta.context["form_decisao_lote"].linhas], [item_negociacao.pk]
        )

    def test_views_mantem_acesso_restrito_ao_modulo(self):
        processo = ProcessoCompra.objects.create(obra=self.obra, numero="PC-ACESSO", titulo="Acesso")
        self.client.force_login(get_user_model().objects.create_user(username="sem-modulo-compras"))
        for nome, args in (
            ("lista_processos", []),
            ("dashboard", []),
            ("detalhe_processo", [processo.pk]),
            ("lista_pedidos", []),
            ("grandes_fornecedores", []),
        ):
            with self.subTest(view=nome):
                self.assertEqual(self.client.get(reverse(f"compras:{nome}", args=args)).status_code, 403)

    def test_acompanhamento_gf_preserva_busca_status_e_totais(self):
        processo = ProcessoCompra.objects.create(
            obra=self.obra, numero="GF-ACOMPANHAMENTO", titulo="Bancadas", fluxo_grande_fornecedor=True,
        )
        fluxo = GrandeFornecedorProcesso.objects.create(processo=processo)
        entregue = GrandeFornecedorItem.objects.create(
            fluxo=fluxo, item="Bancada entregue", quantidade=1,
            status=GrandeFornecedorItem.Status.ENTREGUE,
        )
        GrandeFornecedorItem.objects.create(fluxo=fluxo, item="Bancada em análise", quantidade=1)
        url = reverse("compras:grandes_fornecedores")
        parametros = {"obra": self.obra.pk, "q": "Bancadas"}
        geral = self.client.get(url, parametros)
        entregue_apenas = self.client.get(url, {**parametros, "status": GrandeFornecedorItem.Status.ENTREGUE})
        self.assertEqual(geral.status_code, 200)
        self.assertEqual(entregue_apenas.status_code, 200)
        self.assertEqual(
            (geral.context["total_itens"], geral.context["total_recebidos"], geral.context["total_pendentes"]),
            (2, 1, 1),
        )
        self.assertEqual([linha["item"].pk for linha in entregue_apenas.context["rows"]], [entregue.pk])
        self.assertEqual(
            (entregue_apenas.context["total_itens"], entregue_apenas.context["total_pendentes"]), (1, 0)
        )
