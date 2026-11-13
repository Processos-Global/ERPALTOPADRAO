from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from cadastros.models import Cliente, EmpreendimentoPosObra, VinculoCliente, CategoriaOcorrencia, TipoProblema
from pos_obra.forms import ChamadoForm, AgendamentoForm
from pos_obra.models import Chamado, MaterialOS, RegistroChamado


class RegressaoOperacionalTests(TestCase):
    def test_assinatura_png_truncada_rejeitada(self):
        import base64
        from pos_obra.models import DocumentoOS,AceiteOS
        c=self.chamado();doc=DocumentoOS.objects.create(chamado=c,tipo='EXECUCAO',versao=1,arquivo='teste.pdf',sha256='0'*64)
        self.client.force_login(self.user)
        raw=base64.b64encode(b'\x89PNG\r\n\x1a\ninvalid').decode()
        r=self.client.post(reverse('pos_obra:registrar_aceite',args=[doc.pk]),{'signatario':'Cliente','representacao':'Proprietário','resultado':'ACEITO','ciencia':'on','assinatura':'data:image/png;base64,'+raw})
        self.assertEqual(r.status_code,403);self.assertFalse(AceiteOS.objects.filter(documento=doc).exists())
        from io import BytesIO
        from PIL import Image
        buf=BytesIO();Image.new('RGB',(600,200),'white').save(buf,format='PNG')
        raw=base64.b64encode(buf.getvalue()).decode()
        r=self.client.post(reverse('pos_obra:registrar_aceite',args=[doc.pk]),{'signatario':'Cliente','representacao':'Proprietário','resultado':'ACEITO','ciencia':'on','assinatura':'data:image/png;base64,'+raw})
        self.assertEqual(r.status_code,302)
        aceite=AceiteOS.objects.get(documento=doc);aceite.assinatura.delete(save=False)

    def test_comprovante_preserva_ressalva_longa(self):
        from pos_obra.models import DocumentoOS,AceiteOS
        from pos_obra.relatorios import gerar_relatorio
        from django.core.files.base import ContentFile
        from pypdf import PdfReader
        from io import BytesIO
        import hashlib
        c=self.chamado();original=gerar_relatorio(c,'os').content
        doc=DocumentoOS.objects.create(chamado=c,tipo='OS',versao=1,arquivo=ContentFile(original,name='original-qa.pdf'),sha256=hashlib.sha256(original).hexdigest())
        a=AceiteOS.objects.create(documento=doc,signatario='Nome '*35,representacao='Proprietário',resultado='RESSALVA',observacoes='Observação detalhada. '*170+'MARCADOR FINAL')
        self.client.force_login(self.user)
        r=self.client.get(reverse('pos_obra:comprovante_aceite',args=[a.pk]))
        self.assertEqual(r.status_code,200)
        pdf=PdfReader(BytesIO(r.content));texto=''.join(p.extract_text() for p in pdf.pages)
        self.assertIn('MARCADOR FINAL',texto);self.assertIn(a.signatario.strip(),texto.replace('\n',' '))
        doc.arquivo.delete(save=False)

    def test_publicacao_evidencia_invalida_aceite(self):
        from pos_obra.models import DocumentoOS,AceiteOS,AnexoChamado
        from pos_obra.views.atendimento import aceite_valido
        c=self.chamado()
        anexo=AnexoChamado.objects.create(chamado=c,etapa='EXECUCAO',arquivo='evidencia.png')
        doc=DocumentoOS.objects.create(chamado=c,tipo='EXECUCAO',versao=1,arquivo='teste.pdf',sha256='0'*64)
        AceiteOS.objects.create(documento=doc,signatario='Cliente',representacao='Proprietário',resultado='ACEITO')
        AnexoChamado.objects.filter(pk=anexo.pk).update(criado_em=timezone.now()-timedelta(minutes=2))
        DocumentoOS.objects.filter(pk=doc.pk).update(criado_em=timezone.now()-timedelta(minutes=1))
        self.client.force_login(self.user)
        self.client.post(reverse('pos_obra:publicar_anexo',args=[anexo.pk]),{'publico':'1'})
        self.assertFalse(aceite_valido(c))

    def test_evidencia_tecnica_invalida_aceite(self):
        from pos_obra.models import DocumentoOS,AceiteOS,AnexoChamado
        from pos_obra.views.atendimento import aceite_valido
        c=self.chamado()
        doc=DocumentoOS.objects.create(chamado=c,tipo='EXECUCAO',versao=1,arquivo='teste.pdf',sha256='0'*64)
        AceiteOS.objects.create(documento=doc,signatario='Cliente',representacao='Proprietário',resultado='ACEITO')
        DocumentoOS.objects.filter(pk=doc.pk).update(criado_em=timezone.now()-timedelta(minutes=1))
        AnexoChamado.objects.create(chamado=c,etapa='EXECUCAO',arquivo='evidencia.png')
        self.assertFalse(aceite_valido(c))

    def test_reagendamento_invalido_preserva_dados(self):
        from pos_obra.models import AgendamentoOS
        c=self.chamado()
        a=AgendamentoOS.objects.create(chamado=c,tipo='VISTORIA',inicio=timezone.now(),fim=timezone.now()+timedelta(hours=1),responsavel=self.user)
        self.client.force_login(self.user)
        r=self.client.post(reverse('pos_obra:alterar_agendamento',args=[a.pk]),{'acao':'REAGENDAR','tipo':'VISTORIA','inicio':'invalido','fim':'invalido','observacoes':'Manter observação de reagendamento','responsavel':self.user.pk})
        self.assertEqual(r.status_code,200);self.assertContains(r,'Manter observação de reagendamento')
        a.refresh_from_db();self.assertEqual(a.situacao,'PROPOSTO')

    def test_agendamento_bloqueado_apos_conclusao_da_etapa(self):
        from pos_obra.models import AgendamentoOS
        c=self.chamado(data_vistoria=timezone.localdate(),diagnostico='Vistoria concluída')
        self.client.force_login(self.user)
        inicio=timezone.localtime(timezone.now()+timedelta(days=2))
        dados={'tipo':'VISTORIA','inicio':inicio.strftime('%Y-%m-%dT%H:%M'),'fim':(inicio+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'responsavel':self.user.pk}
        resposta=self.client.post(reverse('pos_obra:agendar',args=[c.pk]),dados)
        self.assertEqual(resposta.status_code,403)
        self.assertFalse(AgendamentoOS.objects.filter(chamado=c).exists())
        dados['tipo']='EXECUCAO'
        resposta=self.client.post(reverse('pos_obra:agendar',args=[c.pk]),dados)
        self.assertEqual(resposta.status_code,302)
        c.data_execucao=timezone.localdate();c.execucao='Execução concluída';c.save()
        resposta=self.client.post(reverse('pos_obra:agendar',args=[c.pk]),dados)
        self.assertEqual(resposta.status_code,403)
        a=AgendamentoOS.objects.get(chamado=c)
        resposta=self.client.post(reverse('pos_obra:alterar_agendamento',args=[a.pk]),dict(dados,acao='REAGENDAR'))
        self.assertEqual(resposta.status_code,403)
        a.refresh_from_db();self.assertEqual(a.situacao,'PROPOSTO')

    @classmethod
    def setUpTestData(cls):
        cls.user=get_user_model().objects.create_superuser('gestor_reg',password='senha')
        cls.portal=get_user_model().objects.create_user('portal_reg',password='senha')
        cls.cliente=Cliente.objects.create(nome='Cliente',usuario=cls.portal,portal_habilitado=True)
        cls.imovel=EmpreendimentoPosObra.objects.create(historica=True,nome_historico='Casa',liberada=True)
        VinculoCliente.objects.create(cliente=cls.cliente,empreendimento=cls.imovel)
        cls.cat=CategoriaOcorrencia.objects.create(nome='Teste')
        cls.tipo=TipoProblema.objects.create(categoria=cls.cat,nome='Teste')

    def chamado(self,**kw):
        return Chamado.objects.create(cliente=self.cliente,empreendimento=self.imovel,tipo_problema=self.tipo,descricao='Teste',**kw)

    def dados(self,**kw):
        d=dict(cliente=self.cliente.pk,empreendimento=self.imovel.pk,tipo_problema=self.tipo.pk,descricao='Teste',ambiente_padrao='Sala')
        d.update(kw);return d

    def test_preferencia_passada(self):
        f=ChamadoForm(self.dados(preferencia_data=(timezone.localdate()-timedelta(days=1)).isoformat()))
        self.assertFalse(f.is_valid());self.assertIn('preferencia_data',f.errors)

    def test_horario_invertido(self):
        f=ChamadoForm(self.dados(preferencia_periodo='HORARIO',preferencia_inicio='15:00',preferencia_fim='14:00'))
        self.assertFalse(f.is_valid());self.assertIn('preferencia_fim',f.errors)

    def test_horario_incompleto(self):
        f=ChamadoForm(self.dados(preferencia_periodo='HORARIO'))
        self.assertFalse(f.is_valid())

    def test_portal_form_renderiza(self):
        self.client.force_login(self.portal)
        self.assertEqual(self.client.get(reverse('pos_obra:portal_novo')).status_code,200)

    def test_estimado_distinto_consumo(self):
        m=MaterialOS(chamado=self.chamado(),previsto=Decimal('3'),utilizado=Decimal('1'),custo_unitario=Decimal('10'))
        self.assertEqual(getattr(m,'total_estimado',None),Decimal('30'))
        self.assertEqual(m.total,Decimal('10'))

    def test_tecnica_reconhece_mensagens_reais(self):
        from pos_obra.views.atendimento import ultima_alteracao_tecnica
        c=self.chamado()
        for mensagem in ['Execucao: informações salvas','Vistoria: informações salvas','Quantidade necessária de Material: 1 → 2']:
            with self.subTest(mensagem=mensagem):
                h=RegistroChamado.objects.create(chamado=c,status_novo=c.status,mensagem=mensagem)
                self.assertEqual(ultima_alteracao_tecnica(c),h.criado_em)

    def test_agenda_rejeita_responsavel_cliente(self):
        data=timezone.localtime()+timedelta(days=1)
        f=AgendamentoForm({'tipo':'VISTORIA','inicio':data.strftime('%Y-%m-%dT%H:%M'),'fim':(data+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),'responsavel':self.portal.pk})
        self.assertFalse(f.is_valid());self.assertIn('responsavel',f.errors)

    def test_agenda_data_impossivel_nao_500(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('pos_obra:agenda'),{'data':'2026-02-31'}).status_code,200)

    def test_agendamento_invalido_preserva_dados(self):
        self.client.force_login(self.user);c=self.chamado()
        r=self.client.post(reverse('pos_obra:agendar',args=[c.pk]),{'tipo':'VISTORIA','observacoes':'Portaria lateral','inicio':'invalido','fim':'invalido','responsavel':self.user.pk})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Portaria lateral')
        self.assertEqual(c.agendamentos.count(),0)

    def test_pdf_texto_longo(self):
        from pos_obra.relatorios import gerar_relatorio
        from pypdf import PdfReader
        from io import BytesIO
        c=self.chamado(diagnostico=('Diagnóstico detalhado com dados reais do teste. '*300),execucao='Conclusão & teste <seguro>')
        response=gerar_relatorio(c,'os')
        pdf=PdfReader(BytesIO(response.content))
        self.assertGreater(len(pdf.pages),1)
        self.assertIn('Conclusão & teste <seguro>',''.join(p.extract_text() for p in pdf.pages))

    def test_bloqueio_recursos_outro_cliente(self):
        from pos_obra.models import DocumentoOS,AceiteOS,AnexoChamado,AgendamentoOS
        outro=get_user_model().objects.create_user('outro_cliente_reg')
        Cliente.objects.create(nome='Outro',usuario=outro,portal_habilitado=True)
        c=self.chamado(status='CONCLUIDO')
        doc=DocumentoOS.objects.create(chamado=c,tipo='OS',versao=1,arquivo='nao-abra.pdf',sha256='0'*64)
        aceite=AceiteOS.objects.create(documento=doc,signatario='Cliente',representacao='Proprietário',resultado='ACEITO')
        anexo=AnexoChamado.objects.create(chamado=c,etapa='ABERTURA',arquivo='nao-abra.pdf',publico=True)
        agenda=AgendamentoOS.objects.create(chamado=c,tipo='VISTORIA',inicio=timezone.now(),fim=timezone.now()+timedelta(hours=1),responsavel=self.user)
        self.client.force_login(outro)
        for nome,args in [('portal_detalhe',[c.pk]),('portal_pdf',[c.pk,'os']),('baixar_documento',[doc.pk]),('comprovante_aceite',[aceite.pk]),('anexo',[anexo.pk]),('pesquisa',[c.pk])]:
            with self.subTest(nome=nome):self.assertIn(self.client.get(reverse('pos_obra:'+nome,args=args)).status_code,[403,404])
        self.assertEqual(self.client.post(reverse('pos_obra:responder_agendamento',args=[agenda.pk]),{'resposta':'CONFIRMADO'}).status_code,403)

    def test_vinculo_removido_revoga_os(self):
        c=self.chamado();self.client.force_login(self.portal)
        VinculoCliente.objects.filter(cliente=self.cliente).update(ativo=False)
        self.assertEqual(self.client.get(reverse('pos_obra:portal_detalhe',args=[c.pk])).status_code,403)

    def test_aceite_os_valido_permite_finalizar(self):
        from pos_obra.models import DocumentoOS,AceiteOS
        c=self.chamado(responsavel=self.user,triagem='Triagem',diagnostico='Diagnóstico',data_vistoria=timezone.localdate(),execucao='Feito',data_execucao=timezone.localdate(),conclusao='Concluído')
        doc=DocumentoOS.objects.create(chamado=c,tipo='OS',versao=1,arquivo='teste.pdf',sha256='0'*64)
        AceiteOS.objects.create(documento=doc,signatario='Cliente',representacao='Proprietário',resultado='ACEITO')
        self.client.force_login(self.user)
        self.client.post(reverse('pos_obra:finalizar',args=[c.pk]),{'confirmacao_assinatura':'on'})
        c.refresh_from_db();self.assertEqual(c.status,'CONCLUIDO')

    def test_material_invalida_documento_assinado(self):
        from pos_obra.models import DocumentoOS,AceiteOS
        c=self.chamado(responsavel=self.user,triagem='Triagem',diagnostico='Diagnóstico',data_vistoria=timezone.localdate(),execucao='Feito',data_execucao=timezone.localdate(),conclusao='Concluído')
        doc=DocumentoOS.objects.create(chamado=c,tipo='EXECUCAO',versao=1,arquivo='teste.pdf',sha256='0'*64)
        AceiteOS.objects.create(documento=doc,signatario='Cliente',representacao='Proprietário',resultado='ACEITO')
        DocumentoOS.objects.filter(pk=doc.pk).update(criado_em=timezone.now()-timedelta(minutes=1))
        RegistroChamado.objects.create(chamado=c,mensagem='Quantidade necessária de Material: 1 → 2',status_novo=c.status)
        self.client.force_login(self.user)
        self.client.post(reverse('pos_obra:finalizar',args=[c.pk]),{'confirmacao_assinatura':'on'})
        c.refresh_from_db();self.assertNotEqual(c.status,'CONCLUIDO')
