from datetime import timedelta
from decimal import Decimal
from re import findall

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor
from compras.models import PedidoCompra, ProcessoCompra, RecebimentoPedido
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar
from obras.models import Obra
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoFinanceiro, PermissaoModulo


class NavegacaoFinanceiraTests(TestCase):
    def test_sete_areas_principais_e_acao_separada(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-nav-admin'))
        resposta = self.client.get(reverse('financeiro:dashboard'))
        navegacao = resposta.content.decode().split('id="fin-subnav"', 1)[1].split('</nav>', 1)[0]
        rotas = ('dashboard', 'titulos', 'aprovacoes', 'pagamentos', 'previsoes', 'indicadores', 'plano_financeiro')
        self.assertEqual(findall(r'href="([^"]+)"', navegacao), [reverse(f'financeiro:{rota}') for rota in rotas])
        self.assertContains(resposta, 'Nova solicitação')
        self.assertNotContains(resposta, reverse('financeiro:liberacoes'))

    def test_aprovador_granular_recebe_apenas_a_area_permitida(self):
        usuario = get_user_model().objects.create_user('financeiro-nav-aprovacao')
        PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.APROVACAO)
        PermissaoFinanceiro.objects.create(usuario=usuario, visualizar=False, aprovar_pagamentos=True)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse('financeiro:aprovacoes'))
        navegacao = resposta.content.decode().split('id="fin-subnav"', 1)[1].split('</nav>', 1)[0]
        self.assertEqual(findall(r'href="([^"]+)"', navegacao), [reverse('financeiro:aprovacoes')])

    def test_leitura_nao_expoe_configuracao_e_acao_de_criacao(self):
        usuario = get_user_model().objects.create_user('financeiro-nav-leitura')
        PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.LEITURA)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse('financeiro:dashboard'))
        self.assertNotContains(resposta, reverse('financeiro:titulo_novo'))
        self.assertNotContains(resposta, reverse('financeiro:plano_financeiro'))
        self.assertNotContains(resposta, reverse('financeiro:aprovacoes'))

    def test_solicitacao_de_compra_exibe_origem_divergencia_e_preparacao(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-nav-solicitacao'))
        titulo = TituloPagar.objects.create(
            numero='FIN-ORIGEM', descricao='Materiais recebidos para a fachada',
            origem=TituloPagar.Origem.COMPRA, conferencia=TituloPagar.Conferencia.DIVERGENCIA,
            status=TituloPagar.Status.PREVISTA, valor_original='42.16',
        )
        resposta = self.client.get(reverse('financeiro:titulos'))
        self.assertContains(resposta, '<td>Compras</td>', html=True)
        self.assertContains(resposta, 'Materiais recebidos para a fachada')
        self.assertContains(resposta, '<span class="fin-badge fin-badge--danger">Divergência</span>', html=True)
        self.assertContains(resposta, reverse('financeiro:titulo_editar', args=[titulo.pk]))

    def test_historico_reavalia_somente_pendencia_automatica_e_preserva_acao_legada(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-nav-historico'))
        obra = Obra.objects.create(nome='Obra sintética do histórico', codigo='FIN-HIST')
        fornecedor = Fornecedor.objects.create(nome='Fornecedor sintético do histórico')
        processo = ProcessoCompra.objects.create(numero='PROC-FIN-HIST', obra=obra, titulo='Processo sintético')
        pedido = PedidoCompra.objects.create(numero='PC-FIN-HIST', obra=obra, fornecedor=fornecedor, processo=processo)
        recebimento = RecebimentoPedido.objects.create(pedido=pedido, numero_nota_fiscal='321')
        registro = LiberacaoFinanceiraPedido.objects.create(
            referencia='UI-HIST-RECEBIMENTO', pedido=pedido, recebimento=recebimento,
            valor_esperado=0, tipo=LiberacaoFinanceiraPedido.Tipo.RECEBIMENTO,
            status=LiberacaoFinanceiraPedido.Status.DIVERGENTE,
        )
        legado = LiberacaoFinanceiraPedido.objects.create(
            referencia='UI-HIST-ANTECIPACAO', pedido=pedido,
            tipo=LiberacaoFinanceiraPedido.Tipo.ANTECIPACAO,
        )
        resposta = self.client.get(reverse('financeiro:liberacoes'))
        self.assertContains(resposta, 'Histórico financeiro de compras')
        self.assertContains(resposta, reverse('financeiro:liberacao_reprocessar', args=[registro.pk]))
        self.assertNotContains(resposta, reverse('financeiro:liberacao_autorizar', args=[registro.pk]))
        self.assertContains(resposta, reverse('financeiro:liberacao_autorizar', args=[legado.pk]))
        self.assertNotContains(resposta, reverse('financeiro:liberacao_reprocessar', args=[legado.pk]))

    def test_visao_geral_separa_dia_atraso_pagamento_e_agenda(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-dashboard'))
        hoje = timezone.localdate()
        for codigo, data, status, valor in (
            ('FIN-HOJE', hoje, TituloPagar.Status.PREVISTA, '20.00'),
            ('FIN-ATRASO', hoje - timedelta(days=1), TituloPagar.Status.APROVADO, '70.00'),
            ('FIN-APROVADO', hoje, TituloPagar.Status.APROVADO, '30.00'),
            ('FIN-FUTURO', hoje + timedelta(days=3), TituloPagar.Status.APROVADO, '90.00'),
            ('FIN-PAGO', hoje, TituloPagar.Status.PAGO, '25.00'),
            ('FIN-CANCELADO', hoje, TituloPagar.Status.CANCELADO, '80.00'),
        ):
            titulo = TituloPagar.objects.create(numero=codigo, descricao=codigo, vencimento=data, status=status, valor_original=valor)
            if status == TituloPagar.Status.PAGO:
                Pagamento.objects.create(titulo=titulo, data_pagamento=hoje, valor=valor)
        resposta = self.client.get(reverse('financeiro:dashboard'))
        self.assertEqual(resposta.context['total_hoje'], Decimal('50.00'))
        self.assertEqual(resposta.context['total_disponivel'], Decimal('100.00'))
        self.assertEqual(resposta.context['total_vencido'], Decimal('70.00'))
        self.assertEqual(resposta.context['pagos_mes'], Decimal('25.00'))
        self.assertEqual({t.numero for t in resposta.context['agenda']}, {'FIN-HOJE', 'FIN-APROVADO'})

    def test_central_filtra_origem_legada_e_mes_e_compartilha_agenda(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-contas'))
        hoje = timezone.localdate()
        TituloPagar.objects.create(numero='FIN-LEGADO', descricao='Legado', vencimento=hoje,
                                  valor_original='42.16', origem=TituloPagar.Origem.CONTRATO)
        TituloPagar.objects.create(numero='FIN-OUTRO', descricao='Avulsa', vencimento=hoje, valor_original='10.20')
        filtros = {'origem': TituloPagar.Origem.CONTRATO, 'periodo': 'mes', 'mes': hoje.strftime('%Y-%m')}
        for rota in ('titulos', 'agenda'):
            with self.subTest(rota=rota):
                resposta = self.client.get(reverse(f'financeiro:{rota}'), filtros)
                self.assertTemplateUsed(resposta, 'financeiro/titulos_lista.html')
                self.assertEqual([t.numero for t in resposta.context['page_obj']], ['FIN-LEGADO'])
                self.assertEqual(resposta.context['indicadores']['em_aberto'], Decimal('42.16'))

    def test_visao_geral_preserva_filtros_da_agenda_ao_detalhar_pagamentos(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-dashboard-filtros'))
        hoje = timezone.localdate()
        obra = Obra.objects.create(nome='Obra selecionada', codigo='DASH-1')
        outra = Obra.objects.create(nome='Outra obra', codigo='DASH-2')
        fornecedor = Fornecedor.objects.create(nome='Fornecedor selecionado')
        for i, destino in enumerate((obra, outra), 1):
            TituloPagar.objects.create(numero=f'DASH-ABERTO-{i}', descricao='Em aberto', valor_original='50.20',
                                      vencimento=hoje, obra=destino, fornecedor=fornecedor, status=TituloPagar.Status.APROVADO)
            pago = TituloPagar.objects.create(numero=f'DASH-PAGO-{i}', descricao='Pago', valor_original='70.10',
                                            vencimento=hoje - timedelta(days=40), obra=destino, fornecedor=fornecedor,
                                            status=TituloPagar.Status.PAGO)
            Pagamento.objects.create(titulo=pago, valor='70.10', data_pagamento=hoje)
        filtros = {'obra': obra.pk, 'fornecedor': fornecedor.pk, 'periodo': 'intervalo',
                   'inicio': hoje.isoformat(), 'fim': hoje.isoformat()}
        resposta = self.client.get(reverse('financeiro:dashboard'), filtros)
        self.assertEqual(resposta.context['total_hoje'], Decimal('50.20'))
        self.assertEqual(resposta.context['pagos_mes'], Decimal('70.10'))
        self.assertEqual([titulo.numero for titulo in resposta.context['agenda']], ['DASH-ABERTO-1'])
        filtro_pago = {**filtros, 'aba': 'efetivados'}
        pagamentos = self.client.get(reverse('financeiro:pagamentos'), filtro_pago)
        self.assertEqual(pagamentos.context['total_pago'], Decimal('70.10'))
        self.assertEqual([p.titulo.numero for p in pagamentos.context['page_obj']], ['DASH-PAGO-1'])

    def test_programar_preserva_vencimento_e_so_confirmar_liquida(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-programacao'))
        hoje = timezone.localdate()
        titulo = TituloPagar.objects.create(numero='FIN-PROG', descricao='Para programar', vencimento=hoje,
                                           valor_original='81.23', status=TituloPagar.Status.APROVADO)
        url = reverse('financeiro:pagamento_programar', args=[titulo.pk])
        for dias in (2, 3):
            agendada = hoje + timedelta(days=dias)
            resposta = self.client.post(url, {'data_programada': agendada.isoformat(), 'motivo': 'Agenda operacional'})
            self.assertEqual(resposta.status_code, 302)
        titulo.refresh_from_db()
        self.assertEqual(titulo.vencimento, hoje)
        self.assertEqual(titulo.status, TituloPagar.Status.APROVADO)
        self.assertFalse(Pagamento.objects.filter(titulo=titulo).exists())
        self.assertEqual(titulo.historico.filter(evento='PAGAMENTO_PROGRAMADO').count(), 2)
        programados = reverse('financeiro:pagamentos', query={'aba': 'programados'})
        self.assertContains(self.client.get(programados), titulo.numero)
        self.assertEqual(self.client.post(reverse('financeiro:pagamento_confirmar_direto', args=[titulo.pk])).status_code, 200)
        self.assertNotContains(self.client.get(programados), titulo.numero)
        self.assertEqual(Pagamento.objects.get(titulo=titulo).valor, Decimal('81.23'))
