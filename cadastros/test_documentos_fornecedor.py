from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.urls import reverse

from cadastros.forms import FornecedorForm
from cadastros.models import Fornecedor


class DocumentoFornecedorTest(TestCase):
    def test_banco_tem_indice_unico_portavel_para_documento(self):
        with connection.cursor() as cursor:
            indices = connection.introspection.get_constraints(cursor, Fornecedor._meta.db_table)
        indice = indices['cad_for_doc_unico_uniq']
        self.assertTrue(indice['unique'])
        self.assertEqual(indice['columns'], ['documento_chave'])

    def test_escrita_direta_rejeita_documento_duplicado_inclusive_inativo(self):
        cpf = '000.000.000-00'
        Fornecedor.objects.create(nome='Sintético inativo', documento=cpf, ativo=False)
        outro = Fornecedor.objects.create(nome='Sintético sem documento')

        with self.assertRaises(IntegrityError), transaction.atomic():
            Fornecedor.objects.bulk_create([Fornecedor(nome='Sintético duplicado', documento=cpf)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Fornecedor.objects.filter(pk=outro.pk).update(documento=cpf)

        outro.refresh_from_db()
        self.assertEqual(outro.documento, '')

    def test_vazios_e_variantes_formatadas_sao_preservados(self):
        documentos = ['', ' ', '000.000.000-00', '00000000000', '00.000.000/0000-00', '00000000000000']
        for documento in documentos:
            Fornecedor.objects.create(nome='Sintético', documento=documento)
        self.assertEqual(
            list(Fornecedor.objects.order_by('pk').values_list('documento', flat=True)),
            ['', '', *documentos[2:]],
        )

    def test_validacao_rejeita_duplicata_e_aceita_editar_o_proprio_documento(self):
        documento = '00.000.000/0000-00'
        fornecedor = Fornecedor.objects.create(nome='Sintético existente', documento=documento)
        duplicado = Fornecedor(nome='Sintético duplicado', documento=documento)
        with self.assertRaises(ValidationError):
            duplicado.full_clean()

        novo = FornecedorForm(data={'nome': 'Sintético duplicado', 'documento': documento})
        edicao = FornecedorForm(data={'nome': fornecedor.nome, 'documento': documento}, instance=fornecedor)
        self.assertFalse(novo.is_valid())
        self.assertTrue(novo.non_field_errors())
        self.assertTrue(edicao.is_valid(), edicao.errors)

    def test_diagnostico_ignora_vazios_e_nao_exibe_documentos(self):
        Fornecedor.objects.bulk_create([
            Fornecedor(nome='Sintético sem documento'),
            Fornecedor(nome='Sintético sem documento'),
            Fornecedor(nome='Sintético com documento', documento='000.000.000-00'),
        ])
        saida = StringIO()

        call_command('diagnosticar_documentos_fornecedores', stdout=saida)

        self.assertIn('0 grupos', saida.getvalue())
        self.assertNotIn('000.000.000-00', saida.getvalue())
        self.assertEqual(Fornecedor.objects.count(), 3)


class ConflitoDocumentoFornecedorViewTest(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser('documento-fornecedor-teste'))

    def test_conflito_apos_validacao_e_mostrado_ao_criar_ou_editar(self):
        existente = Fornecedor.objects.create(nome='Sintético existente')
        is_valid = FornecedorForm.is_valid

        for url, documento in (
            (reverse('cadastros:fornecedor_novo'), '000.000.000-00'),
            (reverse('cadastros:fornecedor_editar', args=[existente.pk]), '00.000.000/0000-00'),
        ):
            with self.subTest(url=url):
                def validar_e_inserir_duplicado(form):
                    valido = is_valid(form)
                    if valido:
                        Fornecedor.objects.create(nome='Sintético gravado após validação', documento=documento)
                    return valido

                with patch.object(FornecedorForm, 'is_valid', validar_e_inserir_duplicado):
                    resposta = self.client.post(url, {'nome': 'Sintético da tela', 'documento': documento})

                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, 'Já existe um fornecedor com este CPF/CNPJ.')
                self.assertEqual(Fornecedor.objects.filter(documento=documento).count(), 1)
                existente.refresh_from_db()
                self.assertEqual(existente.documento, '')

    def test_falha_de_integridade_em_outro_campo_e_propagada(self):
        existente = Fornecedor.objects.create(nome='Sintético existente')
        is_valid = FornecedorForm.is_valid

        def validar_e_repetir_codigo(form):
            valido = is_valid(form)
            form.instance.codigo = existente.codigo
            return valido

        with patch.object(FornecedorForm, 'is_valid', validar_e_repetir_codigo):
            with self.assertRaises(IntegrityError):
                self.client.post(reverse('cadastros:fornecedor_novo'), {'nome': 'Sintético da tela'})
