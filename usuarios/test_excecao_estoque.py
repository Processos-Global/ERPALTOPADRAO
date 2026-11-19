from django.contrib.auth.models import User
from django.test import TestCase

from compras.services.permissoes import possui_acao_compras
from usuarios.models import AcaoCompra, ModuloSistema, NivelPermissao, PermissaoCompras, PermissaoModulo


class ExcecaoEstoquePermissaoTests(TestCase):
    def test_excecao_exige_acao_granular_ou_administracao(self):
        usuario = User.objects.create_user("comprador_excecao", password="Teste12345!")
        modulo = PermissaoModulo.objects.create(
            usuario=usuario, modulo=ModuloSistema.COMPRAS, nivel=NivelPermissao.APROVACAO,
        )
        self.assertFalse(possui_acao_compras(usuario, AcaoCompra.EXCECAO_ESTOQUE))

        permissao = PermissaoCompras.objects.create(usuario=usuario, visualizar=True)
        usuario = User.objects.get(pk=usuario.pk)
        self.assertFalse(possui_acao_compras(usuario, AcaoCompra.EXCECAO_ESTOQUE))

        permissao.excecao_estoque = True
        permissao.save(update_fields=["excecao_estoque"])
        usuario = User.objects.get(pk=usuario.pk)
        self.assertTrue(possui_acao_compras(usuario, AcaoCompra.EXCECAO_ESTOQUE))

        modulo.ativo = False
        modulo.save(update_fields=["ativo"])
        usuario = User.objects.get(pk=usuario.pk)
        self.assertFalse(possui_acao_compras(usuario, AcaoCompra.EXCECAO_ESTOQUE))
