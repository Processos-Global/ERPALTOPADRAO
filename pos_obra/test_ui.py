from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from cadastros.models import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
from pos_obra.models import Chamado, AgendamentoOS, MaterialOS


class InterfaceOperacionalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin=get_user_model().objects.create_superuser('ui_admin',password='Teste12345!')
        cls.portal=get_user_model().objects.create_user('ui_cliente',password='Teste12345!')
        cls.cliente=Cliente.objects.create(nome='Cliente UI',usuario=cls.portal,portal_habilitado=True)
        cls.obra=EmpreendimentoPosObra.objects.create(historica=True,liberada=True,nome_historico='Residencial UI')
        VinculoCliente.objects.create(cliente=cls.cliente,empreendimento=cls.obra)
        cat=CategoriaOcorrencia.objects.create(nome='Categoria UI')
        cls.tipo=TipoProblema.objects.create(categoria=cat,nome='Ocorrência UI')
        cls.os=Chamado.objects.create(cliente=cls.cliente,empreendimento=cls.obra,tipo_problema=cls.tipo,descricao='Descrição UI',ambiente_padrao='Sala')

    def test_estados_operacionais_e_cabecalho(self):
        self.client.force_login(self.admin)
        r=self.client.get(reverse('pos_obra:detalhe',args=[self.os.pk]))
        self.assertContains(r,'data-stage-state="atual"')
        self.assertContains(r,'data-stage-state="bloqueada"')
        self.assertContains(r,'Próximo compromisso')
        self.assertContains(r,'Responsável técnico')
        self.assertContains(r,'id="os-abertura"')

    def test_somente_leitura_nao_oferece_gravacao(self):
        self.client.force_login(self.admin)
        with patch('pos_obra.views.atendimento.possui_permissao_acao',return_value=False):
            r=self.client.get(reverse('pos_obra:detalhe',args=[self.os.pk]))
        self.assertContains(r,'Somente leitura')
        self.assertNotContains(r,'name="etapa"')
        self.assertNotContains(r,'name="acao"')

    def test_upload_invalido_reabre_painel(self):
        self.client.force_login(self.admin)
        r=self.client.post(reverse('pos_obra:upload',args=[self.os.pk]),{'etapa':'ABERTURA','publico':'on'})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'data-active-panel="abertura"')
        self.assertContains(r,'Este campo é obrigatório')

    def test_avaliacao_tem_titulo_proprio(self):
        self.os.status='CONCLUIDO';self.os.save()
        self.client.force_login(self.portal)
        r=self.client.get(reverse('pos_obra:pesquisa',args=[self.os.pk]))
        self.assertContains(r,'Avalie o atendimento')
        self.assertNotContains(r,'<h2>Abrir solicitação</h2>')

    def test_portal_encerrado_nao_oferece_resposta_agenda(self):
        self.os.status='CONCLUIDO';self.os.save()
        a=AgendamentoOS.objects.create(chamado=self.os,tipo='VISTORIA',responsavel=self.admin,inicio=timezone.now()+timedelta(days=1),fim=timezone.now()+timedelta(days=1,hours=1))
        self.client.force_login(self.portal)
        r=self.client.get(reverse('pos_obra:portal_detalhe',args=[self.os.pk]))
        self.assertNotContains(r,reverse('pos_obra:responder_agendamento',args=[a.pk]))

    def test_todas_paginas_renderizam(self):
        self.client.force_login(self.admin)
        for nome,args in [('painel',[]),('lista',[]),('kanban',[]),('agenda',[]),('novo',[]),('detalhe',[self.os.pk]),('cadastros',['categorias']),('cadastros',['problemas']),('cadastrar',['categorias']),('cadastrar',['problemas'])]:
            with self.subTest(nome=nome,args=args):self.assertEqual(self.client.get(reverse('pos_obra:'+nome,args=args)).status_code,200)
        self.client.force_login(self.portal)
        for nome,args in [('portal',[]),('portal_novo',[]),('portal_detalhe',[self.os.pk])]:
            with self.subTest(nome=nome):self.assertEqual(self.client.get(reverse('pos_obra:'+nome,args=args)).status_code,200)

    def test_quantidade_invalida_preserva_valor_e_banco(self):
        self.os.responsavel=self.admin;self.os.triagem='Avaliado'
        self.os.data_vistoria=timezone.localdate();self.os.diagnostico='Diagnóstico';self.os.save()
        material=MaterialOS.objects.create(chamado=self.os,descricao='Material de teste',previsto=2)
        self.client.force_login(self.admin)
        r=self.client.post(reverse('pos_obra:editar_material',args=[self.os.pk,material.pk]),{'previsto':'-2'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['aba_ativa'],'materiais')
        self.assertEqual(r.context['material_quantidade_form']['previsto'].value(),'-2')
        self.assertContains(r,'value="-2"')
        material.refresh_from_db();self.assertEqual(material.previsto,2)

    def test_tratativa_invalida_preserva_texto(self):
        self.client.force_login(self.admin)
        r=self.client.post(reverse('pos_obra:registrar_tratativa',args=[self.os.pk]),{'observacao':'abc'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['aba_ativa'],'satisfacao')
        self.assertContains(r,'>abc</textarea>')
        self.assertEqual(self.os.tratativas_satisfacao.count(),0)

    def test_triagem_invalida_nao_avanca_e_preserva_campos(self):
        self.client.force_login(self.admin)
        r=self.client.post(reverse('pos_obra:detalhe',args=[self.os.pk]),{'etapa':'TRIAGEM','prioridade':'INVALIDA','responsavel':self.admin.pk,'triagem':'Parecer ainda não salvo'})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Parecer ainda não salvo</textarea>')
        self.assertContains(r,'Salvar triagem')
        self.assertContains(r,'data-stage-state="bloqueada"')
        self.os.refresh_from_db();self.assertEqual(self.os.triagem,'')

    def test_dashboard_exclui_agenda_encerrada(self):
        self.os.status='CONCLUIDO';self.os.save()
        AgendamentoOS.objects.create(chamado=self.os,tipo='VISTORIA',responsavel=self.admin,inicio=timezone.now(),fim=timezone.now()+timedelta(hours=1))
        self.client.force_login(self.admin)
        r=self.client.get(reverse('pos_obra:painel'))
        self.assertEqual(len(r.context['compromissos']),0)

    def test_encerramento_respeita_permissao_especifica(self):
        self.client.force_login(self.admin)
        def permissao(user,modulo,acao):return acao!='concluir_ocorrencia'
        with patch('pos_obra.views.atendimento.possui_permissao_acao',side_effect=permissao):
            r=self.client.get(reverse('pos_obra:detalhe',args=[self.os.pk]))
        self.assertNotContains(r,'Encerrar ordem de serviço')
