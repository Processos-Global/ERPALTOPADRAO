from datetime import date
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from tempfile import TemporaryDirectory
from django.urls import reverse
from cadastros.models import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
from pos_obra.models import Chamado, RegistroChamado, AnexoChamado, MaterialOS

class FluxoPosObraTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep uploads out of production media even when these tests run in the ERP.
        from pos_obra.models import AnexoChamado
        cls._tmp = TemporaryDirectory(prefix='saari-pos-obra-test-')
        cls.addClassCleanup(cls._tmp.cleanup)
        storage = AnexoChamado._meta.get_field('arquivo').storage
        original = storage._location
        def restore_storage():
            storage._location = original
            storage.__dict__.pop('location', None)
            storage.__dict__.pop('base_location', None)
        cls.addClassCleanup(restore_storage)
        storage._location = cls._tmp.name
        storage.__dict__.pop('location', None)
        storage.__dict__.pop('base_location', None)
        cls._settings = override_settings(SAARI_DRIVE_ENABLED=False)
        cls._settings.enable()
        cls.addClassCleanup(cls._settings.disable)
        super().setUpClass()

    @classmethod
    def setUpTestData(cls):
        U=get_user_model()
        cls.interno=U.objects.create_superuser(username='gestor',password='test')
        cls.usuario=U.objects.create_user(username='cliente',password='test')
        cls.outro_usuario=U.objects.create_user(username='outro',password='test')
        cls.cliente=Cliente.objects.create(nome='Cliente 1',usuario=cls.usuario,portal_habilitado=True)
        cls.outro=Cliente.objects.create(nome='Cliente 2',usuario=cls.outro_usuario,portal_habilitado=True)
        cls.imovel=EmpreendimentoPosObra.objects.create(nome_historico='Imóvel A',historica=True,liberada=True)
        VinculoCliente.objects.create(cliente=cls.cliente,empreendimento=cls.imovel)
        cls.categoria=CategoriaOcorrencia.objects.create(nome='Hidráulica')
        cls.tipo=TipoProblema.objects.create(categoria=cls.categoria,nome='Vazamento')
    def chamado(self,**kwargs):
        return Chamado.objects.create(cliente=self.cliente,empreendimento=self.imovel,tipo_problema=self.tipo,descricao='Problema no imóvel',**kwargs)
    def login_interno(self):self.client.force_login(self.interno)
    def login_cliente(self):self.client.force_login(self.usuario)
    def triagem(self,c,status):
        return self.client.post(reverse('pos_obra:detalhe',args=[c.pk]),{'etapa':'TRIAGEM','status':status,'prioridade':'NORMAL'})
    def test_status_anterior_e_historico_publico(self):
        self.login_interno();c=self.chamado()
        self.triagem(c,'TRIAGEM');c.refresh_from_db()
        self.assertEqual(c.status,'TRIAGEM')
        h=c.historico.get();self.assertEqual(h.status_anterior,'ABERTO');self.assertTrue(h.publico)
    def test_nao_reabre_concluido_por_triagem(self):
        self.login_interno();c=self.chamado(status='CONCLUIDO')
        self.triagem(c,'TRIAGEM');c.refresh_from_db();self.assertEqual(c.status,'CONCLUIDO')
    def test_nao_reabre_cancelado_por_triagem(self):
        self.login_interno();c=self.chamado(status='CANCELADO')
        self.triagem(c,'TRIAGEM');c.refresh_from_db();self.assertEqual(c.status,'CANCELADO')
    def test_cancelamento_e_registrado(self):
        self.login_interno();c=self.chamado()
        self.triagem(c,'CANCELADO');c.refresh_from_db();self.assertEqual(c.status,'CANCELADO')
    def test_conclusao_exige_fluxo_de_finalizacao(self):
        self.login_interno();c=self.chamado()
        self.triagem(c,'CONCLUIDO');c.refresh_from_db();self.assertEqual(c.status,'ABERTO')
    def test_cliente_nao_acessa_chamado_alheio(self):
        c=self.chamado();self.client.force_login(self.outro_usuario)
        self.assertIn(self.client.get(reverse('pos_obra:portal_detalhe',args=[c.pk])).status_code,[403,404])
    def test_cliente_nao_altera_os_interna(self):
        c=self.chamado();self.login_cliente()
        self.assertEqual(self.triagem(c,'CONCLUIDO').status_code,403)
    def test_download_publico_e_privado(self):
        c=self.chamado();a=AnexoChamado.objects.create(chamado=c,etapa='ABERTURA',publico=True,arquivo=SimpleUploadedFile('teste.pdf',b'%PDF-test'))
        self.login_cliente();response=self.client.get(reverse('pos_obra:anexo',args=[a.pk]))
        self.assertEqual(response.status_code,200);response.close()
        a.publico=False;a.save()
        self.assertEqual(self.client.get(reverse('pos_obra:anexo',args=[a.pk])).status_code,403)
    def test_links_pdf_somente_apos_conclusao(self):
        c=self.chamado(diagnostico='Diagnóstico');self.login_cliente()
        r=self.client.get(reverse('pos_obra:portal_detalhe',args=[c.pk]))
        self.assertNotContains(r,reverse('pos_obra:portal_pdf',args=[c.pk,'vistoria']))
    def test_paginacao_lista_e_busca_imovel(self):
        self.login_interno()
        for _ in range(26):self.chamado()
        r=self.client.get(reverse('pos_obra:lista'),{'q':'Imóvel A'})
        self.assertEqual(r.context['chamados'].paginator.count,26)
        self.assertContains(r,'Próxima')
    def test_portal_conta_todos_e_pagina(self):
        for _ in range(51):self.chamado()
        self.login_cliente();r=self.client.get(reverse('pos_obra:portal'))
        self.assertEqual(r.context['total_chamados'],51);self.assertContains(r,'Próxima')
    def test_data_edicao_iso(self):
        from pos_obra.forms import AtendimentoForm
        c=self.chamado(data_vistoria=date(2026,10,14))
        self.assertIn('2026-10-14',str(AtendimentoForm(instance=c)['data_vistoria']))
    def test_portal_upload_abertura(self):
        self.login_cliente()
        r=self.client.post(reverse('pos_obra:portal_novo'),{'empreendimento':self.imovel.pk,'tipo_problema':self.tipo.pk,'ambiente_padrao':'Sala','descricao':'Vazamento','arquivo':SimpleUploadedFile('abertura.pdf',b'%PDF-test')})
        self.assertEqual(r.status_code,302)
        self.assertTrue(AnexoChamado.objects.filter(chamado__cliente=self.cliente,etapa='ABERTURA',publico=True).exists())
    def test_tipo_desativado_nao_oferecido(self):
        from pos_obra.forms import ChamadoForm
        self.tipo.ativo=False;self.tipo.save()
        self.assertNotIn(self.tipo,ChamadoForm().fields['tipo_problema'].queryset)
    def test_finalizacao_incompleta_nao_altera_status(self):
        self.login_interno();c=self.chamado()
        self.client.post(reverse('pos_obra:finalizar',args=[c.pk]));c.refresh_from_db();self.assertEqual(c.status,'ABERTO')
    def test_finaliza_com_via_e_confirmacao(self):
        self.login_interno()
        c=self.chamado(data_vistoria=date(2026,10,10),diagnostico='Diagnóstico',data_execucao=date(2026,10,11),execucao='Serviço executado',conclusao='Problema corrigido')
        AnexoChamado.objects.create(chamado=c,etapa='FINALIZACAO',arquivo=SimpleUploadedFile('assinada.pdf',b'%PDF-test'))
        url=reverse('pos_obra:finalizar',args=[c.pk])
        self.client.post(url);c.refresh_from_db();self.assertEqual(c.status,'ABERTO')
        self.client.post(url,{'confirmacao_assinatura':'on'});c.refresh_from_db()
        self.assertEqual(c.status,'CONCLUIDO');self.assertIsNotNone(c.finalizado_em)
        self.assertTrue(c.historico.get().publico)
    def test_visibilidade_documento(self):
        self.login_interno();c=self.chamado()
        a=AnexoChamado.objects.create(chamado=c,etapa='VISTORIA',arquivo=SimpleUploadedFile('evidencia.pdf',b'%PDF-test'))
        self.client.post(reverse('pos_obra:publicar_anexo',args=[a.pk]),{'publico':'1'})
        a.refresh_from_db();self.assertTrue(a.publico)
        self.login_cliente();r=self.client.get(reverse('pos_obra:portal_detalhe',args=[c.pk]))
        self.assertContains(r,reverse('pos_obra:anexo',args=[a.pk]))
    def test_cliente_nao_publica_anexo(self):
        c=self.chamado();a=AnexoChamado.objects.create(chamado=c,etapa='VISTORIA',arquivo='teste.pdf')
        self.login_cliente()
        self.assertEqual(self.client.post(reverse('pos_obra:publicar_anexo',args=[a.pk]),{'publico':'1'}).status_code,403)
    def test_upload_rejeita_tipo_falso(self):
        self.login_interno();c=self.chamado()
        self.client.post(reverse('pos_obra:upload',args=[c.pk]),{'etapa':'VISTORIA','arquivo':SimpleUploadedFile('foto.png',b'conteudo nao e uma imagem')})
        self.assertEqual(c.anexos.count(),0)
    def test_upload_bloqueado_apos_conclusao(self):
        self.login_interno();c=self.chamado(status='CONCLUIDO')
        self.assertEqual(self.client.post(reverse('pos_obra:upload',args=[c.pk]),{'etapa':'VISTORIA','arquivo':SimpleUploadedFile('a.pdf',b'%PDF-test')}).status_code,403)
    def test_quantidades_material_preservam_preco(self):
        from decimal import Decimal
        self.login_interno();c=self.chamado()
        m=MaterialOS.objects.create(chamado=c,descricao='Material',previsto=1,utilizado=0,custo_unitario='12.3456')
        url=reverse('pos_obra:editar_material',args=[c.pk,m.pk])
        self.client.post(url,{'previsto':'2.500','utilizado':'1.200'})
        m.refresh_from_db();self.assertEqual(m.utilizado,Decimal('1.2'));self.assertEqual(m.custo_unitario,Decimal('12.3456'))
        self.client.post(url,{'previsto':'-1','utilizado':'-2'})
        m.refresh_from_db();self.assertEqual(m.utilizado,Decimal('1.2'))
    def test_materiais_encerrados_bloqueados(self):
        self.login_interno();c=self.chamado(status='CONCLUIDO')
        m=MaterialOS.objects.create(chamado=c,descricao='Material',previsto=1)
        self.assertEqual(self.client.post(reverse('pos_obra:editar_material',args=[c.pk,m.pk]),{'acao':'excluir'}).status_code,403)
    def test_cliente_nao_consulta_ambientes_alheios(self):
        self.login_cliente();e=EmpreendimentoPosObra.objects.create(nome_historico='Outro imóvel',historica=True,liberada=True)
        self.assertEqual(self.client.get(reverse('pos_obra:portal_ambientes'),{'empreendimento':e.pk}).status_code,404)
    def test_detalhe_encerrado_nao_exibe_acoes_edicao(self):
        self.login_interno();c=self.chamado(status='CONCLUIDO')
        r=self.client.get(reverse('pos_obra:detalhe',args=[c.pk]))
        self.assertNotContains(r,'Salvar triagem');self.assertNotContains(r,'Adicionar material</button>')
    def test_salvar_execucao_preserva_vistoria(self):
        self.login_interno();c=self.chamado(data_vistoria=date(2026,10,10),diagnostico='Diagnóstico')
        self.client.post(reverse('pos_obra:detalhe',args=[c.pk]),{'etapa':'EXECUCAO','data_execucao':'2026-10-11','execucao':'Concluído','materiais_observacao':'Sem sobras'})
        c.refresh_from_db();self.assertEqual(c.data_vistoria,date(2026,10,10));self.assertEqual(c.materiais_observacao,'Sem sobras')
    def test_pdf_concluido_e_bloqueio_alheio(self):
        c=self.chamado(status='CONCLUIDO');self.login_cliente()
        url=reverse('pos_obra:portal_pdf',args=[c.pk,'os'])
        r=self.client.get(url);self.assertEqual(r.status_code,200);self.assertTrue(r.content.startswith(b'%PDF-'))
        self.client.force_login(self.outro_usuario);self.assertEqual(self.client.get(url).status_code,403)
    def test_telas_internas_renderizam(self):
        self.login_interno();c=self.chamado()
        for name,args in [('painel',[]),('lista',[]),('kanban',[]),('novo',[]),('detalhe',[c.pk])]:
            with self.subTest(tela=name):self.assertEqual(self.client.get(reverse('pos_obra:'+name,args=args)).status_code,200)
    def test_menu_interno_tem_pos_obra(self):
        self.login_interno();r=self.client.get(reverse('core:index'))
        self.assertContains(r,reverse('pos_obra:painel'))
    def test_cadastros_data_entrega_iso(self):
        self.login_interno();self.imovel.data_entrega=date(2026,10,14);self.imovel.save()
        r=self.client.get(reverse('cadastros:pos_obra_editar',args=['empreendimentos',self.imovel.pk]))
        self.assertContains(r,'value="2026-10-14"')


class IntegracaoCadastrosPosObraTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from obras.models import Obra
        U = get_user_model()
        cls.gestor = U.objects.create_superuser(username='gestor_integracao', password='test')
        cls.usuario = U.objects.create_user(username='portal_integracao', password='test')
        cls.cliente = Cliente.objects.create(nome='Cliente integração', usuario=cls.usuario, portal_habilitado=True)
        cls.obra_a = Obra.objects.create(nome='Obra integração A', codigo='INT-A', status='CONCLUIDA')
        cls.obra_b = Obra.objects.create(nome='Obra integração B', codigo='INT-B', status='CONCLUIDA')
        cls.imovel = EmpreendimentoPosObra.objects.create(obra=cls.obra_a, liberada=True)
        VinculoCliente.objects.create(cliente=cls.cliente, empreendimento=cls.imovel)
        cls.categoria = CategoriaOcorrencia.objects.create(nome='Categoria integração')
        cls.tipo = TipoProblema.objects.create(categoria=cls.categoria, nome='Tipo integração')

    def test_edicao_nao_troca_obra_de_imovel_liberado(self):
        self.client.force_login(self.gestor)
        c = Chamado.objects.create(cliente=self.cliente, empreendimento=self.imovel,
            tipo_problema=self.tipo, descricao='Chamado existente')
        response = self.client.post(reverse('cadastros:pos_obra_editar', args=['empreendimentos', self.imovel.pk]),
            {'obra': self.obra_b.pk, 'historica': '', 'nome_historico': '', 'codigo_historico': '',
             'endereco_historico': '', 'data_entrega': ''})
        self.imovel.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.imovel.obra_id, self.obra_a.pk)
        self.assertEqual(c.empreendimento.obra_id, self.obra_a.pk)

    def test_validacao_modelo_protege_identidade_com_vinculo(self):
        from django.core.exceptions import ValidationError
        self.imovel.liberada = False
        self.imovel.save(update_fields=['liberada'])
        self.imovel.obra = self.obra_b
        with self.assertRaises(ValidationError):
            self.imovel.full_clean()

    def test_cadastro_nao_vincula_superusuario_a_cliente(self):
        self.client.force_login(self.gestor)
        response = self.client.post(reverse('cadastros:pos_obra_novo', args=['clientes']),
            {'nome': 'Cliente incorreto', 'usuario': self.gestor.pk, 'ativo': 'on', 'portal_habilitado': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Cliente.objects.filter(usuario=self.gestor).exists())
        from pos_obra.access import acesso_interno
        self.assertTrue(acesso_interno(self.gestor))

    def test_modelo_rejeita_conta_com_cargo_interno(self):
        from django.core.exceptions import ValidationError
        user = get_user_model().objects.create_user(username='engenheiro_integracao')
        user.perfil_erp.cargo = 'ENGENHARIA'
        user.perfil_erp.save()
        with self.assertRaises(ValidationError):
            Cliente(nome='Cliente incorreto', usuario=user).full_clean()

    def test_cadastro_aceita_conta_exclusiva_de_portal(self):
        self.client.force_login(self.gestor)
        user = get_user_model().objects.create_user(username='novo_portal_integracao')
        response = self.client.post(reverse('cadastros:pos_obra_novo', args=['clientes']),
            {'nome': 'Cliente válido', 'usuario': user.pk, 'ativo': 'on', 'portal_habilitado': 'on'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cliente.objects.filter(usuario=user).exists())

    def test_banco_rejeita_vinculo_duplicado(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            VinculoCliente.objects.create(cliente=self.cliente, empreendimento=self.imovel)

    def test_banco_rejeita_tipo_duplicado_na_categoria(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            TipoProblema.objects.create(categoria=self.categoria, nome='Tipo integração')

    def test_index_inclui_pos_obra_para_cargo_autorizado(self):
        from usuarios.models import ModuloSistema
        user = get_user_model().objects.create_user(username='operador_integracao')
        user.perfil_erp.cargo = 'POS_OBRA'
        user.perfil_erp.save()
        self.client.force_login(user)
        response = self.client.get(reverse('core:index'))
        self.assertContains(response, reverse('pos_obra:painel'))
        self.assertIn(ModuloSistema.POS_OBRA, [m['codigo'] for m in response.context['modulos']])
        self.assertEqual(response.context['total_modulos'], 1)
        sidebar = response.content.decode().partition('</aside>')[0]
        self.assertIn(reverse('pos_obra:painel'), sidebar)

    def test_index_nao_conta_pos_obra_sem_acesso_interno(self):
        from usuarios.models import ModuloSistema, PermissaoModulo
        user = get_user_model().objects.create_user(username='sem_cargo_integracao')
        PermissaoModulo.objects.create(usuario=user, modulo=ModuloSistema.POS_OBRA)
        self.client.force_login(user)
        response = self.client.get(reverse('core:index'))
        self.assertNotIn(ModuloSistema.POS_OBRA, [m['codigo'] for m in response.context['modulos']])
        self.assertNotContains(response, reverse('pos_obra:painel'))

    def test_admin_nao_altera_os_concluida(self):
        self.client.force_login(self.gestor)
        c = Chamado.objects.create(cliente=self.cliente, empreendimento=self.imovel,
            tipo_problema=self.tipo, descricao='Atendimento encerrado', status='CONCLUIDO')
        url = reverse('admin:pos_obra_chamado_change', args=[c.pk])
        response = self.client.get(url)
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.post(url, {'status': 'ABERTO'}).status_code, 403)
        c.refresh_from_db()
        self.assertEqual(c.status, 'CONCLUIDO')
