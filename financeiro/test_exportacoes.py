from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from pypdf import PdfReader

from financeiro.models import TituloPagar
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoModulo


class ExportacoesFinanceirasTest(TestCase):
    def test_contas_exporta_todos_os_status_e_respeita_filtros(self):
        self.client.force_login(get_user_model().objects.create_superuser('teste-export-fin'))
        hoje = timezone.localdate()
        TituloPagar.objects.create(numero='LEGADO-1', descricao='=1+1', valor_original='170.91', vencimento=hoje,
                                  origem=TituloPagar.Origem.CONTRATO, status=TituloPagar.Status.PREVISTA)
        TituloPagar.objects.create(numero='CANCELADO-1', descricao='Histórico', valor_original='20.37', vencimento=hoje,
                                  origem=TituloPagar.Origem.CONTRATO, status=TituloPagar.Status.CANCELADO)
        base = reverse('financeiro:exportar', args=['contas', 'xlsx'])
        resposta = self.client.get(base, {'origem': TituloPagar.Origem.CONTRATO, 'periodo': 'hoje'})
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('attachment;', resposta['Content-Disposition'])
        linhas = list(load_workbook(BytesIO(resposta.content), read_only=True).active.rows)
        self.assertEqual({linha[0].value for linha in linhas[1:]}, {'LEGADO-1', 'CANCELADO-1'})
        self.assertTrue(any(celula.value == '=1+1' and celula.data_type == 's' for linha in linhas for celula in linha))
        rota_pdf = reverse('financeiro:exportar', args=['contas', 'pdf'])
        pdf = self.client.get(rota_pdf, {'excluir_cancelados': '1'})
        texto = ' '.join(pagina.extract_text() for pagina in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn('LEGADO-1', texto)
        self.assertNotIn('CANCELADO-1', texto)

    def test_aprovacoes_exportadas_exigem_permissao_de_aprovar(self):
        usuario = get_user_model().objects.create_user('teste-export-leitura-fin')
        PermissaoModulo.objects.create(usuario=usuario, modulo=ModuloSistema.FINANCEIRO, nivel=NivelPermissao.LEITURA)
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('financeiro:exportar', args=['aprovacoes', 'xlsx'])).status_code, 403)
