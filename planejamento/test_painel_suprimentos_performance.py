from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cadastros.models import Fornecedor
from compras.models import (
    AdjudicacaoCompra,
    CotacaoFornecedor,
    CotacaoFornecedorItem,
    NecessidadeCompra,
    NegociacaoItem,
    PedidoCompra,
    PedidoCompraItem,
    ProcessoCompra,
    RecebimentoPedido,
    RecebimentoPedidoItem,
    SolicitacaoCotacaoFornecedor,
)
from obras.models import Obra
from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra,
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)
from planejamento.services.cronograma_suprimentos.painel import (
    montar_painel_cronograma_suprimentos,
)
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class PainelSuprimentosConsultasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        importacao = ImportacaoCronogramaSuprimentos.objects.create(
            ativa=True,
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        cls.itens = []
        for indice in range(3):
            obra = Obra.objects.create(nome=f"Obra {indice}", codigo=f"OB{indice}")
            cronograma = CronogramaSuprimentosObra.objects.create(
                importacao=importacao,
                obra=obra,
                nome_aba=obra.nome,
                codigo_aba=obra.codigo,
                ordem_aba=indice,
            )
            cls.itens.append(ItemCronogramaSuprimento.objects.create(
                cronograma_obra=cronograma,
                item=f"Suprimento {indice}",
                categoria="MATERIAL" if indice == 0 else "SERVICO",
            ))
            if indice == 0:
                ItemCronogramaSuprimento.objects.create(
                    cronograma_obra=cronograma,
                    item="Outro suprimento",
                    categoria="SERVICO",
                )

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_opcoes_de_todas_as_obras_usam_consulta_unica(self, anexar):
        with CaptureQueriesContext(connection) as consultas:
            contexto = montar_painel_cronograma_suprimentos()

        self.assertEqual(len(consultas), 4)
        self.assertEqual(contexto["suprimentos_filtro"], [
            "Outro suprimento", "Suprimento 0", "Suprimento 1", "Suprimento 2",
        ])
        anexar.assert_called_once()

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_filtro_local_limita_carga_comercial_sem_mudar_resumo(self, anexar):
        contexto = montar_painel_cronograma_suprimentos(
            suprimento="Suprimento 0", categoria="MATERIAL",
        )
        self.assertEqual(contexto["resumo"]["total"], 1)
        self.assertEqual(contexto["resumo"]["filtrados"], 1)
        self.assertEqual([item.id for item in anexar.call_args.args[0]], [self.itens[0].id])

        anexar.reset_mock()
        contexto = montar_painel_cronograma_suprimentos(categoria="MATERIAL")
        self.assertEqual(contexto["resumo"]["total"], 2)
        self.assertEqual(contexto["resumo"]["filtrados"], 1)
        self.assertEqual(contexto["resumo_filtrado"]["total"], 1)
        self.assertEqual(contexto["resumo_filtrado"]["nao_iniciados"], 1)
        self.assertEqual([item.id for item in anexar.call_args.args[0]], [self.itens[0].id])

    @patch("planejamento.services.cronograma_suprimentos.painel._anexar_acompanhamento_compras")
    def test_suprimento_em_varias_obras_carrega_itens_em_uma_consulta(self, anexar):
        for item in self.itens:
            ItemCronogramaSuprimento.objects.create(
                cronograma_obra=item.cronograma_obra,
                item="Comum",
            )

        with CaptureQueriesContext(connection) as consultas:
            contexto = montar_painel_cronograma_suprimentos(suprimento="Comum")

        self.assertEqual(len(consultas), 4)
        self.assertEqual(contexto["resumo"]["total"], 3)
        self.assertEqual(
            [item.obra_exibicao for item in anexar.call_args.args[0]],
            ["Obra 0", "Obra 1", "Obra 2"],
        )

    @override_settings(USE_THOUSAND_SEPARATOR=True, THOUSAND_SEPARATOR=".")
    def test_filtro_get_envia_id_da_obra_sem_formatacao_e_renderiza_painel(self):
        obra = Obra.objects.create(pk=1234, nome="Obra do filtro", codigo="OB1234")
        cronograma = CronogramaSuprimentosObra.objects.create(
            importacao=self.itens[0].cronograma_obra.importacao,
            obra=obra, nome_aba=obra.nome, codigo_aba=obra.codigo, ordem_aba=4,
        )
        ItemCronogramaSuprimento.objects.create(
            cronograma_obra=cronograma, item="Filtro específico", categoria="MATERIAL",
        )
        usuario = get_user_model().objects.create_superuser(username="filtro-suprimentos", password="teste")
        self.client.force_login(usuario)
        url = reverse("planejamento:painel_cronograma_suprimentos")

        resposta = self.client.get(url, {"obra": obra.pk, "categoria": "MATERIAL"})

        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.headers.get("Content-Disposition"))
        self.assertEqual(resposta.context["cronograma_obra"].obra_id, obra.pk)
        self.assertEqual(resposta.context["resumo"]["filtrados"], 1)
        html = resposta.content.decode()
        self.assertIn('value="1234" selected', html)
        self.assertIn(f'{reverse("planejamento:kanban_cronograma_suprimentos")}?obra=1234', html)

    def test_detalhe_comercial_so_e_renderizado_para_o_item_solicitado(self):
        item = self.itens[0]
        processo = ProcessoCompra.objects.create(
            obra=item.cronograma_obra.obra, item_cronograma=item, numero="PROC-LAZY",
        )
        usuario = get_user_model().objects.create_superuser(username="suprimentos-detalhe")
        self.client.force_login(usuario)

        pagina = self.client.get(reverse("planejamento:painel_cronograma_suprimentos"))
        self.assertEqual(pagina.status_code, 200)
        self.assertNotContains(pagina, processo.numero)
        self.assertNotContains(pagina, 'class="ps-detail-shell"')

        url = reverse("planejamento:detalhe_item_cronograma_suprimentos", args=[item.pk])
        detalhe = self.client.get(url)
        self.assertContains(detalhe, processo.numero)

        ImportacaoCronogramaSuprimentos.objects.filter(pk=item.cronograma_obra.importacao_id).update(ativa=False)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_detalhe_comercial_exige_autenticacao_e_permissao(self):
        url = reverse("planejamento:detalhe_item_cronograma_suprimentos", args=[self.itens[0].pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        usuario = get_user_model().objects.create_user(username="sem-modulo")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_data_necessaria_e_parametro_explicito_com_historico(self):
        item = self.itens[0]
        item.data_real_contratacao = date(2026, 1, 5)
        item.save(update_fields=["data_real_contratacao"])
        usuario = get_user_model().objects.create_superuser(username="planejadora")
        self.client.force_login(usuario)
        detalhe_url = reverse("planejamento:detalhe_item_cronograma_suprimentos", args=[item.pk])
        salvar_url = reverse("planejamento:salvar_datas_item_cronograma_suprimentos", args=[item.pk])
        self.assertContains(self.client.get(detalhe_url), "Não definida")

        for valor in ("2026-07-16", "2026-07-16", "2026-09-21", "2026-02-30"):
            self.assertEqual(self.client.post(salvar_url, {"data_necessaria_obra": valor}).status_code, 302)

        item.refresh_from_db()
        self.assertEqual(item.data_real_contratacao, date(2026, 1, 5))
        self.assertFalse(item.datas_editadas_manualmente)
        detalhe = self.client.get(detalhe_url)
        self.assertContains(detalhe, "21/09/2026")
        self.assertContains(detalhe, "planejadora")
        self.assertEqual(list(item.historico_data_necessaria.values_list("data_anterior", "data_nova")), [
            (date(2026, 7, 16), date(2026, 9, 21)),
            (None, date(2026, 7, 16)),
        ])

    def test_parametro_respeita_permissao_e_rejeita_item_inativo(self):
        item = self.itens[0]
        usuario = get_user_model().objects.create_user(username="edicao-sem-acao-suprimentos")
        PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.SUPRIMENTOS, nivel=NivelPermissao.EDICAO)
        self.client.force_login(usuario)
        url = reverse("planejamento:salvar_datas_item_cronograma_suprimentos", args=[item.pk])
        self.assertEqual(self.client.post(url, {"data_necessaria_obra": "2026-07-16"}).status_code, 403)

        self.client.force_login(get_user_model().objects.create_superuser(username="edicao-item-inativo"))
        ImportacaoCronogramaSuprimentos.objects.filter(pk=item.cronograma_obra.importacao_id).update(ativa=False)
        self.assertEqual(self.client.post(url, {"data_necessaria_obra": "2026-07-16"}).status_code, 404)

    def test_detalhe_reconcilia_cotacao_negociacao_aprovacao_e_pedido(self):
        item = self.itens[0]
        obra = item.cronograma_obra.obra
        responsavel = get_user_model().objects.create_superuser(username="gestora-suprimentos")
        processo = ProcessoCompra.objects.create(
            obra=obra, item_cronograma=item, numero="PROC-VALORES", status=ProcessoCompra.Status.CONTRATADO,
        )
        necessidade = NecessidadeCompra.objects.create(
            processo=processo, descricao="Janela de vedação", unidade="UN", quantidade_necessaria=10, quantidade_incluida=10,
        )
        fornecedor = Fornecedor.objects.create(nome="Fornecedor da proposta")
        cotacao = CotacaoFornecedor.objects.create(
            processo=processo, fornecedor=fornecedor, frete=12, desconto_proposta=15, criado_por=responsavel,
        )
        cotado = CotacaoFornecedorItem.objects.create(
            cotacao=cotacao, necessidade=necessidade, quantidade=10, valor_unitario_cotado=12, desconto_cotado=8,
        )
        NegociacaoItem.objects.create(item_cotado=cotado, valor_unitario_negociado=11, frete_negociado=4, atualizado_por=responsavel)
        AdjudicacaoCompra.objects.create(
            processo=processo, cotacao=cotacao, item_cotado=cotado, necessidade=necessidade,
            quantidade=6, valor_unitario_final=11, selecionado_por=responsavel,
        )
        pedido = PedidoCompra.objects.create(
            numero="PED-PARCIAL", processo=processo, obra=obra, fornecedor=fornecedor,
            status=PedidoCompra.Status.ENTREGA_PARCIAL, subtotal=66, descontos=15, frete=4, valor_total=55,
        )
        linha_pedido = PedidoCompraItem.objects.create(
            pedido=pedido, necessidade=necessidade, descricao="Linha recebida", unidade="UN",
            quantidade=6, quantidade_recebida=2, valor_unitario=11, valor_total=66,
        )
        recebimento = RecebimentoPedido.objects.create(pedido=pedido, usuario=responsavel)
        RecebimentoPedidoItem.objects.create(recebimento=recebimento, item_pedido=linha_pedido, quantidade=2)
        self.client.force_login(responsavel)

        detalhe = self.client.get(reverse("planejamento:detalhe_item_cronograma_suprimentos", args=[item.pk]))
        self.assertEqual(detalhe.status_code, 200)
        linha = detalhe.context["item"].acompanhamento_fornecedores[0]
        self.assertEqual(linha["valor_cotado"], Decimal("109.00"))
        self.assertEqual(linha["valor_negociado"], Decimal("99.00"))
        self.assertEqual(linha["valor_aprovado"], Decimal("55.00"))
        self.assertEqual(linha["valor_pedido"], Decimal("55.00"))
        self.assertContains(detalhe, "Janela de vedação")
        self.assertContains(detalhe, "Linha recebida")
        self.assertContains(detalhe, "Recebido 2 UN")
        self.assertContains(detalhe, "Pendente 4 UN")
        self.assertContains(detalhe, "gestora-suprimentos")

    def test_detalhe_mostra_pedido_sem_cotacao_e_isola_obra_do_vinculo(self):
        item = self.itens[0]
        fornecedor = Fornecedor.objects.create(nome="Fornecedor histórico")
        for obra, numero in [
            (item.cronograma_obra.obra, "PED-HISTORICO"),
            (self.itens[1].cronograma_obra.obra, "PED-OUTRA-OBRA"),
        ]:
            processo = ProcessoCompra.objects.create(obra=obra, item_cronograma=item, numero=f"PROC-{obra.codigo}")
            PedidoCompra.objects.create(numero=numero, processo=processo, obra=obra, fornecedor=fornecedor, valor_total=30)
        self.client.force_login(get_user_model().objects.create_superuser(username="gestor-detalhe"))
        detalhe = self.client.get(reverse("planejamento:detalhe_item_cronograma_suprimentos", args=[item.pk]))
        self.assertContains(detalhe, "PED-HISTORICO")
        self.assertNotContains(detalhe, "PED-OUTRA-OBRA")

    def test_listagem_leve_mantem_previsao_e_busca_por_fornecedor(self):
        item = self.itens[0]
        obra = item.cronograma_obra.obra
        processo = ProcessoCompra.objects.create(obra=obra, item_cronograma=item, numero="PROC-BUSCA")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor Exclusivo")
        SolicitacaoCotacaoFornecedor.objects.create(processo=processo, fornecedor=fornecedor)
        for numero, situacao, previsao in (
            ("PED-1", PedidoCompra.Status.ENTREGUE, date(2026, 1, 1)),
            ("PED-2", PedidoCompra.Status.ENTREGA_PARCIAL, date(2026, 2, 1)),
            ("PED-3", PedidoCompra.Status.CANCELADO, date(2026, 1, 20)),
        ):
            PedidoCompra.objects.create(
                numero=numero, processo=processo, obra=obra, fornecedor=fornecedor,
                status=situacao, previsao_entrega_original=previsao,
            )
        with CaptureQueriesContext(connection) as consultas:
            contexto = montar_painel_cronograma_suprimentos(incluir_acompanhamento=False)
        self.assertEqual(len(consultas), 5)
        linha = contexto["categorias"][0]["itens"][0]
        self.assertEqual(linha.previsao_entrega_compra, date(2026, 2, 1))
        self.assertEqual(linha.previsao_entrega_qtd_pedidos, 2)
        self.assertFalse(hasattr(linha, "acompanhamento_fornecedores"))

        busca = montar_painel_cronograma_suprimentos(
            incluir_acompanhamento=False, busca="fornecedor exclusivo",
        )
        self.assertEqual(busca["resumo"]["filtrados"], 1)
        self.assertEqual(busca["categorias"][0]["itens"][0].pk, item.pk)
