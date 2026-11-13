from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from cadastros.models import Cliente, EmpreendimentoPosObra, VinculoCliente
from usuarios.forms import UsuarioSistemaForm


class CadastroIntegradoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.obra = EmpreendimentoPosObra.objects.create(historica=True, nome_historico='Casa histórica', liberada=True)
        cls.admin = get_user_model().objects.create_superuser('gestor', password='Teste12345!')

    def dados(self, **kw):
        data = dict(username='portal', first_name='Ana', tipo_acesso='CLIENTE',
                    cliente_nome='Ana da Silva', cliente_documento='123.456.789-00',
                    cliente_email='contato@example.test', cliente_telefone='11999999999',
                    cliente_ativo='on', portal_habilitado='on', ativo='on',
                    senha='SenhaSegura123!', confirmar_senha='SenhaSegura123!',
                    empreendimentos_cliente=[self.obra.pk])
        data.update(kw)
        return data

    def criar(self):
        f=UsuarioSistemaForm(self.dados())
        self.assertTrue(f.is_valid(), f.errors)
        return f.save()

    def test_cria_cliente_sem_cadastro_previo(self):
        u=self.criar()
        self.assertEqual(u.cliente_saari.nome, 'Ana da Silva')
        self.assertTrue(u.check_password('SenhaSegura123!'))
        self.assertFalse(u.is_staff)
        self.assertEqual(u.cliente_saari.vinculos.get().empreendimento, self.obra)

    def test_interno_nao_cria_cliente(self):
        f=UsuarioSistemaForm(self.dados(tipo_acesso='INTERNO', cargo='ENGENHARIA'))
        self.assertTrue(f.is_valid(), f.errors)
        u=f.save()
        self.assertFalse(Cliente.objects.filter(usuario=u).exists())
        self.assertEqual(u.perfil_erp.cargo, 'ENGENHARIA')

    def test_edicao_preserva_cliente_e_inativos(self):
        u=self.criar();pk=u.cliente_saari.pk
        outra=EmpreendimentoPosObra.objects.create(historica=True,nome_historico='Outra',liberada=True)
        VinculoCliente.objects.create(cliente=u.cliente_saari,empreendimento=outra,ativo=False)
        f=UsuarioSistemaForm(instance=u)
        self.assertEqual(list(f['empreendimentos_cliente'].value()), [self.obra.pk])
        f=UsuarioSistemaForm(self.dados(senha='',confirmar_senha='',cliente_nome='Ana editada'),instance=u)
        self.assertTrue(f.is_valid(),f.errors);f.save()
        self.assertEqual(Cliente.objects.get(usuario=u).pk,pk)
        self.assertEqual(Cliente.objects.get(pk=pk).nome,'Ana editada')
        self.assertFalse(VinculoCliente.objects.get(cliente_id=pk,empreendimento=outra).ativo)

    def test_remocao_e_reativacao_explicitas(self):
        u=self.criar();cl=u.cliente_saari
        v=cl.vinculos.get();v.papel='AUTORIZADO';v.save()
        for obras,enabled in [([],False),([self.obra.pk],True)]:
            f=UsuarioSistemaForm(self.dados(senha='',confirmar_senha='',empreendimentos_cliente=obras,portal_habilitado='on' if enabled else ''),instance=u)
            self.assertTrue(f.is_valid(),f.errors);f.save()
            v.refresh_from_db();self.assertEqual(v.ativo,enabled);self.assertEqual(v.papel,'AUTORIZADO')

    def test_rollback_vinculo(self):
        f=UsuarioSistemaForm(self.dados());self.assertTrue(f.is_valid(),f.errors)
        with patch('cadastros.models.pos_obra.VinculoCliente.objects.update_or_create',side_effect=RuntimeError('falha simulada')):
            with self.assertRaises(RuntimeError):f.save()
        self.assertFalse(get_user_model().objects.filter(username='portal').exists())
        self.assertEqual(Cliente.objects.count(),0)

    def test_commit_false_nao_grava(self):
        f=UsuarioSistemaForm(self.dados());self.assertTrue(f.is_valid(),f.errors)
        u=f.save(commit=False)
        self.assertIsNone(u.pk);self.assertEqual(Cliente.objects.count(),0)

    def test_documento_formatado_duplicado(self):
        Cliente.objects.create(nome='Legado',documento='12345678900')
        f=UsuarioSistemaForm(self.dados())
        self.assertFalse(f.is_valid());self.assertIn('cliente_documento',f.errors)

    def test_associacao_legado_explicita(self):
        cl=Cliente.objects.create(nome='Legado',documento='12345678900')
        f=UsuarioSistemaForm(self.dados(cliente_vinculado=cl.pk))
        self.assertTrue(f.is_valid(),f.errors);u=f.save()
        self.assertEqual(Cliente.objects.count(),1)
        cl.refresh_from_db();self.assertEqual(cl.usuario,u)

    def test_nao_apropria_cliente_associado(self):
        u=self.criar()
        f=UsuarioSistemaForm(self.dados(username='outro',cliente_vinculado=u.cliente_saari.pk))
        self.assertFalse(f.is_valid())

    def test_associacao_legado_preserva_obra_nao_liberada(self):
        cl=Cliente.objects.create(nome='Legado',documento='12345678900')
        self.obra.liberada=False;self.obra.save()
        v=VinculoCliente.objects.create(cliente=cl,empreendimento=self.obra,papel='AUTORIZADO')
        f=UsuarioSistemaForm(self.dados(cliente_vinculado=cl.pk,empreendimentos_cliente=[]))
        self.assertTrue(f.is_valid(),f.errors);f.save()
        v.refresh_from_db();self.assertTrue(v.ativo);self.assertEqual(v.papel,'AUTORIZADO')

    def test_validacao_senha_nova_conta(self):
        f=UsuarioSistemaForm(self.dados(senha='123',confirmar_senha='123'))
        self.assertFalse(f.is_valid());self.assertIn('senha',f.errors)

    def test_http_preserva_dados_invalidos(self):
        self.client.force_login(self.admin)
        r=self.client.post(reverse('usuarios:novo_usuario'),self.dados(confirmar_senha='diferente'))
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Ana da Silva');self.assertNotContains(r,'value="SenhaSegura123!"')

    def test_cadastros_nao_cria_cliente_por_post(self):
        self.client.force_login(self.admin)
        r=self.client.post(reverse('cadastros:pos_obra_novo',args=['clientes']),{'nome':'Independente','ativo':'on'})
        self.assertIn(r.status_code,[403,405,410]);self.assertEqual(Cliente.objects.count(),0)
