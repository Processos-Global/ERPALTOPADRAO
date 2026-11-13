"""Synthetic regressions; independent SQLite settings required."""
import sys
from datetime import date
from decimal import Decimal
from django.conf import settings

# Discovery imports this module before the runner creates any test database.
# Fail closed if somebody forgets the explicit independent settings argument.
if settings.SETTINGS_MODULE != 'relatorios.test_settings':
    raise RuntimeError('Use --settings=relatorios.test_settings; application database is forbidden.')
if set(settings.DATABASES) != {'default'}:
    raise RuntimeError('Only the isolated default database is allowed.')
_database = settings.DATABASES['default']
if (_database['ENGINE'] != 'django.db.backends.sqlite3'
        or _database['NAME'] != ':memory:'
        or _database.get('TEST', {}).get('NAME') != ':memory:'):
    raise RuntimeError('Tests require SQLite :memory: for NAME and TEST.NAME.')
if 'config.settings' in sys.modules:
    raise RuntimeError('Application settings were unexpectedly imported.')

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase, RequestFactory
from django.urls import reverse
from financeiro.models import TituloPagar, Pagamento
from usuarios.models import PermissaoModulo, PermissaoAcao
from relatorios.views import painel
from relatorios.services import estrategicos

class RelatoriosRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        assert settings.SETTINGS_MODULE == 'relatorios.test_settings'
        assert 'config.settings' not in sys.modules
        cls.admin = User.objects.create(username='qa-admin', is_superuser=True)
        cls.reader = User.objects.create(username='qa-reader')
        PermissaoModulo.objects.create(usuario=cls.reader, modulo='RELATORIOS', ativo=True)
        PermissaoAcao.objects.create(usuario=cls.reader, modulo='RELATORIOS', acao='visualizar', permitido=True)

    def test_empty_seven_pages_render(self):
        self.client.force_login(self.admin)
        for name in ['indicadores', 'projetos', 'obras', 'suprimentos', 'planejamento', 'financeiro', 'pos_obra']:
            with self.subTest(page=name):
                response = self.client.get(reverse('relatorios:' + name))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'relatorios/painel.html')

    def test_visualizar_does_not_allow_exportar(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('relatorios:financeiro'), {'exportar': 'csv'}).status_code, 403)

    def test_module_without_action_denied(self):
        PermissaoAcao.objects.all().delete()
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(reverse('relatorios:financeiro')).status_code, 403)

    def test_explicit_export_action(self):
        PermissaoAcao.objects.create(usuario=self.reader, modulo='RELATORIOS', acao='exportar', permitido=True)
        self.client.force_login(self.reader)
        response = self.client.get(reverse('relatorios:financeiro'), {'exportar': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_inactive_denied(self):
        self.reader.is_active = False
        request = RequestFactory().get('/relatorios/financeiro/')
        request.user = self.reader
        with self.assertRaises(PermissionDenied):
            painel.financeiro(request)

    def test_invalid_ids_never_expand_to_all(self):
        self.client.force_login(self.admin)
        for raw in ['²', '999999999999999999999999999999999999', 'not-an-id', '-1']:
            with self.subTest(raw=raw):
                response = self.client.get(reverse('relatorios:obras'), {'obra': raw})
                self.assertEqual(response.status_code, 400)

    def test_invalid_dates_not_silently_ignored(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('relatorios:projetos'), {'inicio': '2026-02-30'}).status_code, 400)

    def test_extreme_date_no_overflow(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('relatorios:projetos'), {'fim': '9999-12-31'}).status_code, 200)

    def test_reversed_dates(self):
        filters = painel._filters(RequestFactory().get('/', {'inicio': '2026-11-11', 'fim': '2026-01-01'}))
        self.assertEqual((filters['inicio'], filters['fim']), (date(2026, 1, 1), date(2026, 11, 11)))

    def assert_open_balance(self, expected):
        cards, _ = estrategicos.financeiro({'inicio': None, 'fim': None, 'obra_id': None}, painel._card, painel._panel)
        balances = [c['value'] for c in cards if 'saldo' in c['label'].casefold() and 'aberto' in c['label'].casefold()]
        self.assertTrue(balances, 'Dashboard must expose saldo em aberto')
        self.assertEqual(balances[0], 'R$ ' + painel._money(expected))

    def make_title(self):
        return TituloPagar.objects.create(numero='QA-001', descricao='Synthetic fixture', valor_original=Decimal('1000'), juros=Decimal('50'), desconto=Decimal('100'), vencimento=date(2026, 1, 1))

    def test_net_balance_950(self):
        self.make_title()
        self.assert_open_balance(Decimal('950'))

    def test_integral_payment_zero_balance(self):
        title = self.make_title()
        Pagamento.objects.create(titulo=title, data_pagamento=date(2026, 1, 1), valor=Decimal('950'), status=Pagamento.Status.EFETIVADO)
        self.assert_open_balance(Decimal('0'))

    def test_reversed_payment_restores_950(self):
        title = self.make_title()
        Pagamento.objects.create(titulo=title, data_pagamento=date(2026, 1, 1), valor=Decimal('950'), status=Pagamento.Status.ESTORNADO)
        self.assert_open_balance(Decimal('950'))

    def test_panel_explicit_numeric_contract(self):
        panel = painel._panel('Comparação', [{'label': 'A', 'value': '-1,2 p.p.', 'raw': -1.2, 'width': 100}])
        self.assertIn('chart', panel)
        for key in ['type', 'orientation', 'unit', 'precision', 'min', 'max', 'sort', 'negative', 'allowed_types']:
            self.assertIn(key, panel['chart'])
        self.assertEqual(panel['rows'][0]['raw'], -1.2)

    def post_fixture(self, status='ABERTO'):
        from pos_obra.models import Chamado, Cliente, EmpreendimentoPosObra, TipoProblema, CategoriaOcorrencia
        estate, _ = EmpreendimentoPosObra.objects.get_or_create(nome_historico='QA history', historica=True)
        client, _ = Cliente.objects.get_or_create(nome='QA client')
        category, _ = CategoriaOcorrencia.objects.get_or_create(nome='QA category')
        problem, _ = TipoProblema.objects.get_or_create(categoria=category, nome='QA problem')
        return Chamado.objects.create(empreendimento=estate, cliente=client, tipo_problema=problem, descricao='QA', status=status)

    def post_cards(self):
        from pos_obra.models import Chamado, PesquisaSatisfacao
        from relatorios.services import analises
        qs = Chamado.objects.all()
        cards, _ = analises.post_details(qs, qs.exclude(status__in=['CONCLUIDO', 'CANCELADO']), PesquisaSatisfacao.objects.all(), {'inicio': None, 'fim': None}, painel._card, painel._panel, painel._group)
        return cards

    def test_aging_strict_elapsed_days(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from pos_obra.models import Chamado
        now = timezone.make_aware(datetime(2026, 11, 11, 12))
        for days in [30, 30.5, 31, 60, 61, 90, 91]:
            row = self.post_fixture()
            Chamado.objects.filter(pk=row.pk).update(criado_em=now-timedelta(days=days))
        with patch('django.utils.timezone.now', return_value=now):
            values = [c['value'] for c in self.post_cards() if '30 / 60 / 90' in c['label']]
        self.assertEqual(values, ['6 / 3 / 1'])

    def test_paid_title_with_effective_payment_has_no_inconsistency(self):
        title = self.make_title()
        TituloPagar.objects.filter(pk=title.pk).update(status=TituloPagar.Status.PAGO)
        Pagamento.objects.create(titulo=title, data_pagamento=date(2026, 1, 1), valor=Decimal('950'), status=Pagamento.Status.EFETIVADO)
        cards, _ = estrategicos.financeiro({'inicio':None,'fim':None,'obra_id':None}, painel._card, painel._panel)
        values = {c['label']:c['value'] for c in cards}
        self.assertEqual(values['Saldo em aberto'], 'R$ 0,00')
        self.assertEqual(values['Inconsistências de pagamento'], '0')

    def test_survey_coverage_excludes_reopened(self):
        from pos_obra.models import PesquisaSatisfacao
        for status in ['CONCLUIDO', 'CONCLUIDO', 'REABERTO']:
            row = self.post_fixture(status)
            PesquisaSatisfacao.objects.create(chamado=row, atendimento=5, prazo=5, qualidade=5, resolvido='SIM')
        values = [c['value'] for c in self.post_cards() if 'pesquisas por os' in c['label'].casefold() or 'cobertura' in c['label'].casefold()]
        self.assertEqual(len(values), 1)
        self.assertIn(values[0], ['100.0%', '100,0%', '100%'])

    def test_estate_without_orders_keeps_filter(self):
        from pos_obra.models import EmpreendimentoPosObra
        estate = EmpreendimentoPosObra.objects.create(nome_historico='No orders', historica=True)
        filters = painel._filters(RequestFactory().get('/', {'empreendimento': estate.pk}), empreendimento=True)
        self.assertEqual(filters['empreendimento_id'], estate.pk)

    def test_physical_comparison_before_rounding(self):
        from planejamento.models import ImportacaoCronograma, RegistroCronograma
        imp = ImportacaoCronograma.objects.create(ativa=True, status='CONCLUIDA')
        RegistroCronograma.objects.create(importacao=imp, projeto='QA', disciplina='RESUMO GERAL', percentual_executado=Decimal('0.4996'), percentual_previsto=Decimal('0.5004'))
        cards, *rest = estrategicos.planejamento({'inicio': None, 'fim': None, 'obra_id': None}, painel._card, painel._panel)
        values = [c['value'] for c in cards if 'atrás' in c['label']]
        self.assertEqual(values, ['1'])

    def test_negative_obligation_clamped_to_zero(self):
        title = self.make_title()
        TituloPagar.objects.filter(pk=title.pk).update(desconto=Decimal('2000'))
        self.assert_open_balance(Decimal('0'))

    def test_csv_formula_escaped(self):
        request = RequestFactory().get('/', {'exportar': 'csv'})
        request.user = self.admin
        response = painel._render(request, 'QA', 'financeiro', [painel._card('=1+1', '@danger')], [], {'inicio': None, 'fim': None})
        content = response.content.decode('utf-8-sig')
        self.assertIn("'=1+1", content)
        self.assertIn("'@danger", content)

    def test_snapshot_asof_ignores_start_and_inactive_import(self):
        from planejamento.models import ImportacaoCronograma, RegistroCronograma
        imp = ImportacaoCronograma.objects.create(ativa=True, status='CONCLUIDA')
        inactive = ImportacaoCronograma.objects.create(ativa=False, status='CONCLUIDA')
        for source, day, executed in [(imp, 1, '0.2'), (imp, 10, '0.6'), (inactive, 2, '0.9')]:
            RegistroCronograma.objects.create(importacao=source, projeto='QA', disciplina='RESUMO GERAL', data_atualizacao=date(2026, 1, day), semana=day, percentual_executado=Decimal(executed), percentual_previsto=Decimal('0.5'))
        cards, *rest = estrategicos.planejamento({'inicio': date(2026, 1, 4), 'fim': date(2026, 1, 5), 'obra_id': None}, painel._card, painel._panel)
        values = {c['label']: c['value'] for c in cards}
        self.assertEqual(values['Cronogramas acompanhados'], '1')
        self.assertEqual(values['Cronogramas atrás do previsto'], '1')

    def test_local_month_and_missing_month_are_preserved(self):
        from datetime import datetime
        from django.utils import timezone
        from pos_obra.models import Chamado
        for dt in [datetime(2026, 1, 31, 23, 30), datetime(2026, 3, 1, 12)]:
            row = self.post_fixture()
            Chamado.objects.filter(pk=row.pk).update(criado_em=timezone.make_aware(dt))
        rows = painel._series(Chamado.objects.all(), 'criado_em')
        self.assertEqual([r['label'] for r in rows], ['01/2026', '02/2026', '03/2026'])
        self.assertEqual([r['raw'] for r in rows], [1, 0, 1])

    def test_chart_semantics_on_all_pages(self):
        self.client.force_login(self.admin)
        for page in ['indicadores', 'projetos', 'obras', 'suprimentos', 'planejamento', 'financeiro', 'pos_obra']:
            response = self.client.get(reverse('relatorios:' + page))
            for panel in response.context['panels']:
                with self.subTest(page=page, panel=panel['title']):
                    spec = panel['chart']
                    if 'por mês' in panel['title']:
                        self.assertEqual(spec['sort'], 'chronological')
                        self.assertEqual(spec['orientation'], 'vertical')
                    elif spec['sort'] != 'chronological':
                        self.assertNotIn('line', spec['allowed_types'])
                    if panel['title'] in ['Compras por obra', 'Compras por fornecedor']:
                        self.assertEqual(spec['unit'], 'currency')
                    if panel['title'] == 'Notas médias da pesquisa':
                        self.assertEqual(spec['type'], 'scatter')
                    for row in panel['rows']:
                        self.assertTrue(row['raw'] is None or isinstance(row['raw'], (int, float)))
        titles = [p['title'] for p in response.context['panels']]
        self.assertEqual(sum(t.startswith('Resolução ') for t in titles), 1)

    def test_fvs_denominator_and_work_isolation(self):
        from obras.models import Obra, FVS, FVSItem
        from cadastros.models import ModeloFVS
        work = Obra.objects.create(nome='QA A', codigo='QA-A')
        other = Obra.objects.create(nome='QA B', codigo='QA-B')
        model = ModeloFVS.objects.create(nome='QA Model')
        for target, results in [(work, ['C']*8+['NC']*2+['NA']*3+['']), (other, ['NC']*10)]:
            fvs = FVS.objects.create(obra=target, modelo_origem=model, modelo_nome='QA', criado_por=self.admin)
            FVSItem.objects.bulk_create([FVSItem(fvs=fvs, item_verificacao='QA', resultado=r) for r in results])
        self.client.force_login(self.admin)
        response = self.client.get(reverse('relatorios:obras'), {'obra':work.pk})
        cards = {c['label']:c for c in response.context['cards']}
        self.assertEqual(cards['Conformidade verificada']['value'], '80.0%')
        self.assertEqual(cards['Itens não conformes']['value'], '2')
        self.assertEqual(cards['Itens avaliados']['value'], '10')

    def test_overdue_balance_uses_net_and_excludes_no_due(self):
        self.make_title()
        TituloPagar.objects.create(numero='QA-UNDATED', descricao='QA', valor_original=Decimal('500'))
        cards, _ = estrategicos.financeiro({'inicio':None,'fim':None,'obra_id':None}, painel._card, painel._panel)
        values = {c['label']:c['value'] for c in cards}
        self.assertEqual(values['Saldo vencido'], 'R$ 950,00')
        self.assertEqual(values['Saldo em aberto'], 'R$ 1.450,00')
        self.assertEqual(values['Títulos sem vencimento'], '1')

    def test_financial_months_include_zero_activity(self):
        for month in (1, 3):
            title = TituloPagar.objects.create(numero=f'QA-M-{month}', descricao='QA', valor_original=Decimal('100'))
            Pagamento.objects.create(titulo=title, data_pagamento=date(2026, month, 1), valor=Decimal('100'), status=Pagamento.Status.EFETIVADO)
        _, panels = estrategicos.financeiro({'inicio':None,'fim':None,'obra_id':None}, painel._card, painel._panel)
        rows = next(p['rows'] for p in panels if p['title'] == 'Pagamentos efetivados por mês')
        self.assertEqual([r['label'] for r in rows], ['01/2026', '02/2026', '03/2026'])
        self.assertEqual([r['raw'] for r in rows], [100, 0, 100])

    def test_component_does_not_add_invisible_grid_items(self):
        from django.template.loader import render_to_string
        html = render_to_string('relatorios/_panel.html', {'panel':painel._panel('QA', []), 'panel_id':'qa'})
        self.assertNotIn('\ufeff', html)
