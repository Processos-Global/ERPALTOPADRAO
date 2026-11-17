"""Testes da concretagem — fase 2: campo, moldagem/PDF, anexos no Drive e laudos.

    manage.py test obras.tests_concretagem_execucao --settings=obras.test_settings_concretagem
"""
import io
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from obras.models import (
    AnexoConcretagem, CaminhaoConcretagem, Concretagem, LaudoConcretagem, SobraConcreto, UtilizacaoConcreto,
)
from obras.services.concretagem import campo, drive, ficha, fluxo
from obras.tests_concretagem import BaseConcretagem
from usuarios.models import Notificacao

S = Concretagem.Status


def _png(nome="etiqueta.png", tamanho=(60, 30)):
    buf = io.BytesIO()
    Image.new("RGB", tamanho, (200, 30, 30)).save(buf, "PNG")
    return SimpleUploadedFile(nome, buf.getvalue(), content_type="image/png")


class BaseExecucao(BaseConcretagem):
    def setUp(self):
        self.conc = fluxo.aceitar(
            fluxo.solicitar(self._criar(volume_solicitado=Decimal("15")), self.eng), self.gerente,
        )
        mail.outbox.clear()
        self.client.force_login(self.eng)

    def url(self, nome, *args):
        return reverse(f"obras:concretagem_{nome}", args=[self.conc.pk, *args])

    def _caminhao(self, volume="8", **extra):
        dados = {
            "volume_entregue": volume, "placa": "ABC1D23", "numero_nota_fiscal": "123",
            "horario_chegada": "07:40", "inicio_descarga": "07:50", "termino_descarga": "08:20", "cps_moldados": 4,
        }
        dados.update(extra)
        self.client.post(self.url("caminhao_criar"), dados)
        return CaminhaoConcretagem.objects.filter(concretagem=self.conc).order_by("-ordem").first()

    def _anexar_nf(self, cam):
        return self.client.post(self.url("caminhao_nf", cam.pk), {"foto_nf": _png("nf.png")})

    def _serie_completa(self, cam):
        return self.client.post(self.url("serie_salvar", cam.pk), {
            "inicio_mistura": "07:10", "hora_moldagem": "08:00", "concreto_aplicado_m3": str(cam.volume_entregue),
            "local_aplicacao": "LAJE", "abatimento_medido": "100",
        })


class CampoTests(BaseExecucao):
    def test_caminhoes_ordem_e_foto_nf_fica_pendente_sem_drive(self):
        c1 = self._caminhao("8", foto_nf=_png("nf.png"))
        c2 = self._caminhao("7")
        self.assertEqual((c1.ordem, c2.ordem), (1, 2))
        nf = AnexoConcretagem.objects.get(caminhao=c1, etapa="NOTA_FISCAL")
        self.assertEqual(nf.status, "PENDENTE")
        self.assertTrue(nf.arquivo)
        self.assertEqual(campo.resumo_volume(self.conc)["volume_entregue"], Decimal("15"))

    def test_nao_lanca_caminhao_antes_de_confirmar(self):
        outra = fluxo.solicitar(self._criar(), self.eng)
        self.client.post(reverse("obras:concretagem_caminhao_criar", args=[outra.pk]), {"volume_entregue": "5"})
        self.assertFalse(CaminhaoConcretagem.objects.filter(concretagem=outra).exists())

    def test_leitor_nao_lanca_caminhao(self):
        self.client.force_login(self.leitor)
        resp = self.client.post(self.url("caminhao_criar"), {"volume_entregue": "5"})
        self.assertEqual(resp.status_code, 403)

    def test_uso_nao_passa_do_saldo_do_caminhao(self):
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8.5"})
        self.assertFalse(UtilizacaoConcreto.objects.exists())
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "7.5"})
        self.assertEqual(campo.resumo_volume(self.conc)["saldo"], Decimal("0.50"))

    def test_uso_rejeita_local_de_outra_obra(self):
        self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"local": self.local_outra.pk, "volume_utilizado": "1"})
        self.assertFalse(UtilizacaoConcreto.objects.exists())

    def test_sobra_outra_obra_exige_obra_e_calcula_situacao(self):
        self._caminhao("8")
        self.client.post(self.url("sobra_criar"), {"volume_sobra": "1", "destino": "OUTRA_OBRA"})
        self.assertFalse(SobraConcreto.objects.exists())
        self.client.post(self.url("sobra_criar"), {
            "volume_sobra": "1", "destino": "OUTRA_OBRA", "obra_destino": self.outra_obra.pk,
        })
        sobra = SobraConcreto.objects.get()
        self.assertEqual(sobra.situacao, "REAPROVEITADA")
        self.assertIn("Outra Obra", sobra.destino_texto)

    def test_sobra_outro_exige_descricao(self):
        self._caminhao("8")
        self.client.post(self.url("sobra_criar"), {"volume_sobra": "1", "destino": "OUTRO"})
        self.assertFalse(SobraConcreto.objects.exists())

    def test_nao_remove_caminhao_com_uso(self):
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "2"})
        self.client.post(self.url("caminhao_remover", cam.pk))
        cam.refresh_from_db()
        self.assertTrue(cam.ativo)

    def test_reagendar_bloqueado_com_caminhao(self):
        self._caminhao("8")
        with self.assertRaises(fluxo.FluxoError):
            fluxo.reagendar(self.conc, self.eng)

    def test_finalizar_exige_saldo_zero_e_ficha(self):
        cam = self._caminhao("8")
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        self.assertTrue(any("Ficha de moldagem" in m for m in campo.pendencias_finalizar(self.conc)))
        self._serie_completa(cam)
        self.assertIn(f"Anexe a nota fiscal do {cam.rotulo}.", campo.pendencias_finalizar(self.conc))
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)  # sem NF não avança
        self._anexar_nf(cam)
        self.assertEqual(campo.pendencias_finalizar(self.conc), [])
        self.client.post(self.url("finalizar"))  # avançar etapa: sem motivo/ocorrências
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.EXECUTADA)
        self.assertTrue(AnexoConcretagem.objects.filter(concretagem=self.conc, etapa="FICHA_MOLDAGEM", ativo=True).exists())
        # Depois de finalizada, os lançamentos de campo ficam bloqueados.
        self.client.post(self.url("uso_criar"), {"local": self.laje.pk, "volume_utilizado": "1"})
        self.assertEqual(UtilizacaoConcreto.objects.count(), 1)


class FichaPdfTests(BaseExecucao):
    def test_pdf_com_mais_de_cinco_caminhoes_e_etiquetas(self):
        for _ in range(6):
            cam = self._caminhao("2")
        self.client.post(self.url("serie_salvar", cam.pk), {
            "local_aplicacao": "PILAR", "etiquetas": [_png(), _png("b.png", (30, 60))],
        })
        self.assertEqual(AnexoConcretagem.objects.filter(caminhao=cam, etapa="ETIQUETA_CP").count(), 2)
        conteudo = ficha.gerar_pdf(self.conc)
        self.assertTrue(conteudo.startswith(b"%PDF"))
        from pypdf import PdfReader
        self.assertEqual(len(PdfReader(io.BytesIO(conteudo)).pages), 4)  # 2 fichas x 2 páginas
        resp = self.client.get(self.url("ficha_pdf"))
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_etiqueta_rejeita_arquivo_que_nao_e_imagem(self):
        cam = self._caminhao("2")
        falso = SimpleUploadedFile("x.png", b"nao sou imagem", content_type="image/png")
        self.client.post(self.url("serie_salvar", cam.pk), {"etiquetas": [falso]})
        self.assertFalse(AnexoConcretagem.objects.filter(etapa="ETIQUETA_CP").exists())


class DriveAnexoTests(BaseExecucao):
    def test_envio_ao_drive_apaga_temporario(self):
        cam = self._caminhao("8", foto_nf=_png("nf.png"))
        anexo = AnexoConcretagem.objects.get(caminhao=cam)
        storage = anexo._meta.get_field("arquivo").storage
        nome_local = anexo.arquivo.name
        self.assertTrue(storage.exists(nome_local))
        self.conc.drive_pasta_id = "pasta"
        self.conc.save(update_fields=["drive_pasta_id"])
        with self.settings(CONCRETAGEM_DRIVE_ENABLED=True, CONCRETAGEM_DRIVE_ROOT_FOLDER_ID="raiz"), \
                mock.patch("core.services.arquivos_drive.obter_pasta", return_value="sub"), \
                mock.patch.object(drive, "_upload", return_value=("id123", "https://drive.google.com/file/d/id123/view")):
            enviados, restantes = drive.reenviar_pendentes(self.conc)
        self.assertEqual((enviados, restantes), (1, 0))
        anexo.refresh_from_db()
        self.assertEqual(anexo.status, "NO_DRIVE")
        self.assertFalse(anexo.arquivo)
        self.assertFalse(storage.exists(nome_local))
        resp = self.client.get(self.url("anexo_abrir", anexo.pk))
        self.assertRedirects(resp, anexo.drive_url, fetch_redirect_response=False)

    def test_falha_no_drive_mantem_pendente(self):
        cam = self._caminhao("8", foto_nf=_png("nf.png"))
        anexo = AnexoConcretagem.objects.get(caminhao=cam)
        with self.settings(CONCRETAGEM_DRIVE_ENABLED=True, CONCRETAGEM_DRIVE_ROOT_FOLDER_ID="raiz"), \
                mock.patch.object(drive, "garantir_pasta", return_value=False):
            self.assertFalse(drive.enviar_anexo(anexo))
        anexo.refresh_from_db()
        self.assertEqual(anexo.status, "PENDENTE")
        self.assertTrue(anexo.arquivo)
        self.assertEqual(anexo.tentativas, 1)

    def test_leitor_abre_temporario_e_sem_fotos_da_obra(self):
        cam = self._caminhao("8", foto_nf=_png("nf.png"))
        anexo = AnexoConcretagem.objects.get(caminhao=cam, etapa="NOTA_FISCAL")
        self.assertEqual(self.client.get(self.url("anexo_abrir", anexo.pk)).status_code, 200)
        self.assertNotContains(self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])), "Fotos da obra")
        self.client.force_login(self.leitor)  # sem a permissão Concretagem
        self.assertEqual(self.client.get(self.url("anexo_abrir", anexo.pk)).status_code, 403)


class LaudosTests(BaseExecucao):
    def setUp(self):
        super().setUp()
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        self._serie_completa(cam)
        self._anexar_nf(cam)
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.EXECUTADA)

    def test_avancar_na_executada_abre_janela_dos_cps(self):
        html = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])).content.decode()
        self.assertIn('data-cc-open="modal-cps">Avançar etapa', html)
        self.assertIn('id="modal-cps"', html)
        self.assertNotIn("CPs enviados ao laboratório</button>", html)  # formulário duplicado saiu da aba Laudos
        self.assertNotIn('data-cc-open="modal-cancelar"', html)  # executada não cancela

    def test_cps_enviados_exige_bombista_quando_tem_bomba(self):
        Concretagem.objects.filter(pk=self.conc.pk).update(com_bomba=True)
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.EXECUTADA)

    def test_fluxo_laudos_reprovacao_e_conclusao(self):
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.AGUARDANDO_LAUDOS)
        # primeiro lançamento exige o arquivo do laudo
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 7, "resistencia_mpa": "20"})
        self.assertFalse(LaudoConcretagem.objects.exists())
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 7, "resistencia_mpa": "20", "arquivo": _png("l7.png")})
        l7 = LaudoConcretagem.objects.get(idade_dias=7)
        self.assertTrue(l7.aprovado)  # 20/30 = 66,7% >= 60%
        self.assertEqual(l7.enviado_por_nome, "Carlos")
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url("laudo_salvar"), {"idade_dias": 28, "resistencia_mpa": "28", "arquivo": _png("l28.png")})
        l28 = LaudoConcretagem.objects.get(idade_dias=28)
        self.assertFalse(l28.aprovado)  # mínimo 95% de 30 = 28,5
        self.assertEqual(l28.limite_minimo_mpa, Decimal("28.5"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["eng@test.local"])
        self.assertTrue(Notificacao.objects.filter(usuario=self.gerente, evento="concretagem.laudo_reprovado.28").exists())
        # sem a permissão Concretagem não conclui
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(self.url("concluir")).status_code, 403)
        # precisa justificar por causa do laudo reprovado
        self.client.force_login(self.gerente)
        self.client.post(self.url("concluir"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.AGUARDANDO_LAUDOS)
        self.client.post(self.url("concluir"), {"justificativa": "Extração de testemunho aprovada"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONCLUIDA)
        self.assertEqual(self.conc.concluida_por, self.gerente)

    def test_atualizar_laudo_sem_novo_arquivo(self):
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 14, "resistencia_mpa": "18", "arquivo": _png()})
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 14, "resistencia_mpa": "23"})
        self.assertEqual(LaudoConcretagem.objects.get(idade_dias=14).resistencia_mpa, Decimal("23.0"))

    def test_concluir_exige_28_e_intermediario(self):
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 28, "resistencia_mpa": "31", "arquivo": _png()})
        self.client.force_login(self.gerente)
        self.client.post(self.url("concluir"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.AGUARDANDO_LAUDOS)

    def test_detalhe_renderiza_todas_as_abas(self):
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        self.client.post(self.url("laudo_salvar"), {"idade_dias": 7, "resistencia_mpa": "15", "arquivo": _png()})
        for usuario in (self.eng, self.gerente):
            self.client.force_login(usuario)
            resp = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))
            self.assertEqual(resp.status_code, 200)
            for aba in ("campo", "moldagem", "laudos", "anexos"):
                self.assertContains(resp, f'data-panel="{aba}"')


class DetalheConfirmadaTests(BaseExecucao):
    def test_aviso_de_confirmada_some_apos_primeiro_caminhao(self):
        detalhe = reverse("obras:concretagem_detalhe", args=[self.conc.pk])
        self.assertContains(self.client.get(detalhe), "Concretagem confirmada")
        self._caminhao("8")
        self.assertNotContains(self.client.get(detalhe), "Concretagem confirmada")

    def test_detalhe_confirmada_com_caminhoes_renderiza(self):
        cam = self._caminhao("8", foto_nf=_png())
        self.client.post(self.url("sobra_criar"), {"volume_sobra": "1", "destino": "DESCARTADO", "caminhao": cam.pk})
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Avançar etapa")
        self.assertNotContains(resp, "Finalizar execução")
        self.assertContains(resp, "foto NF")
        html = resp.content.decode()
        self.assertIn('cc-tag alerta">Sobra<', html)  # sobra na mesma lista, marcada
        self.assertIn('data-cc-open="modal-sobra">+ Sobra', html)

    def test_avancar_e_voltar_entre_etapas_3_e_5(self):
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        self._serie_completa(cam)
        self._anexar_nf(cam)
        self.client.post(self.url("finalizar"))
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Pedro"})
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.AGUARDANDO_LAUDOS)
        self.assertContains(self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])), "Voltar etapa")
        self.client.post(self.url("voltar_etapa"))
        self.conc.refresh_from_db()
        self.assertEqual((self.conc.status, self.conc.cps_enviados_por_nome), (S.EXECUTADA, ""))
        self.client.post(self.url("voltar_etapa"))
        self.conc.refresh_from_db()
        self.assertEqual((self.conc.status, self.conc.executada_em), (S.CONFIRMADA, None))
        # Campo reaberto: aceita lançamentos de novo; Confirmada não volta por aqui.
        self._caminhao("2")
        self.assertEqual(self.conc.caminhoes.filter(ativo=True).count(), 2)
        self.client.post(self.url("voltar_etapa"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(self.url("voltar_etapa")).status_code, 403)


class LocalObrigatorioTests(BaseExecucao):
    def test_uso_sem_local_rejeitado(self):
        self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"descricao": "laje", "volume_utilizado": "2"})
        self.assertFalse(UtilizacaoConcreto.objects.exists())

    def test_item_planejado_sem_local_rejeitado(self):
        self.client.post(reverse("obras:concretagem_nova"), {
            "obra": self.obra.pk, "concreteira": self.forn.pk, "engenheiro": self.eng.pk,
            "item_local": [""], "item_descricao": ["pilares"], "item_volume": ["3"],
        })
        self.assertEqual(Concretagem.objects.count(), 1)  # só a do setUp


class AvisosEConcretoAplicadoTests(BaseExecucao):
    def _detalhe(self):
        return self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))

    def test_concreto_aplicado_vem_do_caminhao(self):
        cam = self._caminhao("7.5")
        serie = cam.serie_moldagem
        self.assertIsNone(serie.concreto_aplicado_m3)
        self.assertEqual(serie.concreto_aplicado, Decimal("7.50"))
        self.assertNotIn("concreto aplicado", serie.pendencias())
        self.assertContains(self._detalhe(), 'name="concreto_aplicado_m3" value="7.50"')

    def test_aviso_nas_abas_e_borda_so_no_especifico(self):
        resp = self._detalhe()
        # sem caminhão: aviso só na aba Campo, sem borda vermelha no conteúdo
        self.assertContains(resp, 'data-tab="campo">Campo<span class="cc-aviso"')
        self.assertNotRegex(resp.content.decode(), r'class="[^"]*cc-falta')
        cam = self._caminhao("8")
        resp = self._detalhe()
        self.assertContains(resp, 'data-tab="campo">Campo<span class="cc-aviso"')
        self.assertContains(resp, 'data-tab="moldagem">Moldagem<span class="cc-aviso"')
        self.assertContains(resp, '<tr class="cc-falta">')  # caminhão com saldo sem destino
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        self._serie_completa(cam)
        self.assertContains(self._detalhe(), 'data-tab="campo">Campo<span class="cc-aviso"')  # ainda falta a NF
        self.client.post(self.url("caminhao_nf", cam.pk), {"foto_nf": _png("nf.png")})
        resp = self._detalhe()
        self.assertNotContains(resp, 'data-tab="campo">Campo<span class="cc-aviso"')
        self.assertNotContains(resp, 'data-tab="moldagem">Moldagem<span class="cc-aviso"')

    def test_aviso_bombista_na_solicitacao(self):
        Concretagem.objects.filter(pk=self.conc.pk).update(com_bomba=True)
        resp = self._detalhe()
        self.assertContains(resp, 'data-tab="solicitacao">Solicitação<span class="cc-aviso"')
        self.assertContains(resp, '<div class="cc-falta"><dt>Bombista</dt>')


class EtiquetasAjaxESlumpTests(BaseExecucao):
    XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}

    def test_envia_varias_etiquetas_por_ajax_com_miniatura_e_remove(self):
        cam = self._caminhao("8")
        url = self.url("etiqueta_enviar", cam.pk)
        ids = []
        for nome in ("a.png", "b.png", "c.png"):
            dados = self.client.post(url, {"foto": _png(nome)}, **self.XHR).json()
            self.assertTrue(dados["ok"])
            ids.append(dados["etiqueta"]["id"])
        self.assertEqual(AnexoConcretagem.objects.filter(caminhao=cam, etapa="ETIQUETA_CP", ativo=True).count(), 3)
        mini = self.client.get(self.url("anexo_miniatura", ids[0]))
        self.assertEqual(mini["Content-Type"], "image/jpeg")
        self.assertTrue(self.client.post(self.url("anexo_remover", ids[1]), **self.XHR).json()["ok"])
        self.assertEqual(AnexoConcretagem.objects.filter(caminhao=cam, etapa="ETIQUETA_CP", ativo=True).count(), 2)

    def test_etiqueta_fica_no_sistema_e_nao_vai_ao_drive(self):
        from unittest import mock

        from obras.services.concretagem import drive

        cam = self._caminhao("8")
        with mock.patch.object(drive, "drive_habilitado", return_value=True),                 mock.patch.object(drive, "agendar_envio") as agendar:
            dados = self.client.post(self.url("etiqueta_enviar", cam.pk), {"foto": _png()}, **self.XHR).json()
            anexo = AnexoConcretagem.objects.get(pk=dados["etiqueta"]["id"])
            agendar.assert_not_called()
            self.assertFalse(drive.enviar_anexo(anexo))
        self.assertEqual(dados["etiqueta"]["situacao"], "Na ficha")
        self.assertTrue(anexo.arquivo)  # arquivo continua no sistema para entrar na ficha
        self.assertNotIn(anexo, list(drive.pendentes(self.conc)))
        self.assertEqual(self.client.get(self.url("anexos_status")).json()["total"], 0)

    def test_etiqueta_invalida_retorna_erro_json(self):
        cam = self._caminhao("8")
        falso = SimpleUploadedFile("x.png", b"nada", content_type="image/png")
        resp = self.client.post(self.url("etiqueta_enviar", cam.pk), {"foto": falso}, **self.XHR)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_leitor_nao_envia_etiqueta(self):
        cam = self._caminhao("8")
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(self.url("etiqueta_enviar", cam.pk), {"foto": _png()}).status_code, 403)

    def test_slump_e_tolerancia_da_solicitacao_vao_para_as_series(self):
        Concretagem.objects.filter(pk=self.conc.pk).update(slump="10", slump_tolerancia="2")
        cam = self._caminhao("8")
        serie = cam.serie_moldagem
        self.assertEqual((serie.slump_flow_valor, serie.slump_flow_tolerancia_valor), ("10", "2"))
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))
        self.assertContains(resp, 'name="slump_flow" maxlength="20" value="10"')
        self.assertContains(resp, 'name="slump_flow_tolerancia" maxlength="20" value="2"')
        self.assertContains(resp, "10 ± 2")


class AbaDocumentosTests(BaseExecucao):
    def test_nota_fiscal_aparece_na_aba_de_documentos(self):
        com_nf = self._caminhao("8", foto_nf=_png("nf-123.png"), numero_nota_fiscal="NF-777")
        self._caminhao("5", numero_nota_fiscal="NF-888")
        resp = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))
        html = resp.content.decode()
        painel = html[html.index('data-panel="anexos"'):]
        self.assertIn("Notas fiscais dos caminhões", painel)
        self.assertIn("nf-123.png", painel)
        self.assertIn("NF-888", painel)
        self.assertIn("Falta NF", painel)
        anexo = AnexoConcretagem.objects.get(caminhao=com_nf, etapa="NOTA_FISCAL")
        self.assertIn(reverse("obras:concretagem_anexo_abrir", args=[self.conc.pk, anexo.pk]), painel)


class NotaFiscalDepoisTests(BaseExecucao):
    def _detalhe(self):
        return self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])).content.decode()

    def test_aviso_ate_anexar_nf_e_anexa_depois(self):
        cam = self._caminhao("8")
        html = self._detalhe()
        self.assertIn("Falta NF", html)
        self.assertIn('data-tab="campo">Campo<span class="cc-aviso"', html)
        self.assertIn(f'data-cc-open="modal-nf-{cam.pk}"', html)
        self.client.post(self.url("caminhao_nf", cam.pk), {"foto_nf": _png("nota.png"), "numero_nota_fiscal": "NF-99"})
        cam.refresh_from_db()
        self.assertEqual(cam.numero_nota_fiscal, "NF-99")
        self.assertTrue(AnexoConcretagem.objects.filter(caminhao=cam, etapa="NOTA_FISCAL", ativo=True).exists())
        html = self._detalhe()
        self.assertNotIn("Falta NF", html)
        self.assertNotIn(f'data-cc-open="modal-nf-{cam.pk}"', html)  # botão some depois de anexar

    def test_nao_avanca_com_pendencia_de_nf_ou_bombista(self):
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        self._serie_completa(cam)
        Concretagem.objects.filter(pk=self.conc.pk).update(com_bomba=True)
        self.assertIn('title="Ainda falta:', self._detalhe())  # botão Avançar etapa desativado
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)
        self._anexar_nf(cam)
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.CONFIRMADA)  # ainda falta o bombista
        Concretagem.objects.filter(pk=self.conc.pk).update(nome_bombista="Zé")
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.EXECUTADA)

    def test_nf_exige_arquivo_valido(self):
        cam = self._caminhao("8")
        self.client.post(self.url("caminhao_nf", cam.pk), {})
        falso = SimpleUploadedFile("n.pdf", b"nao e pdf", content_type="application/pdf")
        self.client.post(self.url("caminhao_nf", cam.pk), {"foto_nf": falso})
        self.assertFalse(AnexoConcretagem.objects.filter(caminhao=cam, etapa="NOTA_FISCAL").exists())

    def test_leitor_nao_anexa_nf(self):
        cam = self._caminhao("8")
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.post(self.url("caminhao_nf", cam.pk), {"foto_nf": _png()}).status_code, 403)


class PastaDriveTests(BaseExecucao):
    def test_link_da_pasta_no_drive(self):
        url = reverse("obras:concretagem_pasta_drive", args=[self.conc.pk, "FICHA_MOLDAGEM"])
        resp = self.client.get(url)  # pasta ainda não criada: volta ao detalhe
        self.assertRedirects(resp, reverse("obras:concretagem_detalhe", args=[self.conc.pk]), fetch_redirect_response=False)
        Concretagem.objects.filter(pk=self.conc.pk).update(drive_pasta_id="abc", drive_pasta_url="https://drive.google.com/drive/folders/abc")
        resp = self.client.get(url)  # Drive desligado nos testes: cai na pasta da concretagem
        self.assertEqual(resp["Location"], "https://drive.google.com/drive/folders/abc")


class DriveSegundoPlanoTests(BaseExecucao):
    def test_status_lista_pendentes_e_modal_aparece(self):
        cam = self._caminhao("8", foto_nf=_png("nota-x.png"))
        dados = self.client.get(self.url("anexos_status")).json()
        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["pendentes"][0]["nome"], "nota-x.png")
        self.assertEqual(dados["pendentes"][0]["origem"], cam.rotulo)
        html = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])).content.decode()
        self.assertIn('id="modal-pendentes-drive"', html)
        self.assertIn("nota-x.png", html)

    def test_envio_nao_duplica_quando_ja_em_andamento(self):
        from django.utils import timezone
        cam = self._caminhao("8", foto_nf=_png())
        anexo = AnexoConcretagem.objects.get(caminhao=cam)
        AnexoConcretagem.objects.filter(pk=anexo.pk).update(enviando_em=timezone.now())
        with self.settings(CONCRETAGEM_DRIVE_ENABLED=True, CONCRETAGEM_DRIVE_ROOT_FOLDER_ID="raiz"), \
                mock.patch.object(drive, "_upload") as upload:
            self.assertFalse(drive.enviar_anexo(anexo))
            upload.assert_not_called()

    def test_agendamento_em_thread_so_depois_do_commit(self):
        cam = self._caminhao("8")
        with self.settings(CONCRETAGEM_DRIVE_ENABLED=True, CONCRETAGEM_DRIVE_ROOT_FOLDER_ID="raiz",
                           CONCRETAGEM_DRIVE_SEGUNDO_PLANO=True), \
                mock.patch("threading.Thread") as thread:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                drive.criar_anexo(self.conc, "NOTA_FISCAL", _png(), self.eng, caminhao=cam)
            thread.assert_not_called()  # nada roda antes do commit: a tela não espera o Drive
            self.assertEqual(len(callbacks), 1)
