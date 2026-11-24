from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from financeiro.models import Pagamento, TituloPagar
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class NavegacaoFinanceiraTests(TestCase):
    def test_seis_areas_principais_e_acao_separada(self):
        self.client.force_login(get_user_model().objects.create_superuser('financeiro-nav-admin'))
        resposta = self.client.get(reverse('financeiro:dashboard'))
        navegacao = resposta.content.decode().split('id="fin-subnav"', 1)[1].split('</nav>', 1)[0]
        for rota in ('dashboard', 'titulos', 'pagamentos', 'compromissos', 'previsoes', 'indicadores'):
            self.assertIn(reverse(f'financeiro:{rota}'), navegacao)
        self.assertNotIn(reverse('financeiro:titulo_novo'), navegacao)
        self.assertContains(resposta, 'Nova solicitação')
        self.assertContains(resposta, reverse('financeiro:plano_financeiro'))

    def test_leitura_nao_expoe_configuracao_e_acao_de_criacao(self):
        usuario = get_user_model().objects.create_user('financeiro-nav-leitura')
        PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.LEITURA)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse('financeiro:dashboard'))
        self.assertNotContains(resposta, reverse('financeiro:titulo_novo'))
        self.assertNotContains(resposta, reverse('financeiro:plano_financeiro'))

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
