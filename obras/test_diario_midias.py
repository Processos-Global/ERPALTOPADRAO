from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from obras.models import (
    Concretagem, DiarioAtividadeAdicional, DiarioAtividadePlanejada, DiarioObra, FotoDiarioObra, Obra,
)
from obras.services.diario_midias import PREFIXO_FOTO_PRIVADA
from planejamento.models import AtividadePlanejamento
from usuarios.models import ModuloSistema, NivelPermissao, PermissaoAcao, PermissaoModulo


@override_settings(CACHES={"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "testes-diario-midias",
}})
class DiarioMidiasTest(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(username="diario-midias-admin")
        self.leitor = get_user_model().objects.create_user(username="diario-midias-leitor")
        PermissaoModulo.objects.create(
            usuario=self.leitor, modulo=ModuloSistema.OBRAS, nivel=NivelPermissao.LEITURA,
        )
        self.client.force_login(self.admin)
        self.obra = Obra.objects.create(nome="Obra sintética", codigo="OB-DIA-MIDIA")
        self.diario = DiarioObra.objects.create(
            obra=self.obra, data=date(2026, 10, 14), registrado_por=self.admin,
            servicos_executados="Detalhe histórico", efetivo=7,
        )
        self.storage = InMemoryStorage()
        campo = FotoDiarioObra._meta.get_field("arquivo")
        troca_storage = patch.object(campo, "storage", self.storage)
        troca_storage.start()
        self.addCleanup(troca_storage.stop)

    def _foto(self, nome="evidencia.jpg", dados=None, diario=None):
        if dados is None:
            exif = Image.Exif()
            exif[274] = 6
            with BytesIO() as arquivo, Image.new("RGB", (2400, 1200), "brown") as imagem:
                imagem.save(arquivo, "JPEG", exif=exif)
                dados = arquivo.getvalue()
        caminho = self.storage.save(f"obras/diarios/2026/10/{nome}", ContentFile(dados))
        return FotoDiarioObra.objects.create(diario=diario or self.diario, arquivo=caminho), dados

    def _url_foto(self, foto, variante="miniatura", diario=None):
        return reverse("obras:diario_foto", args=[(diario or self.diario).pk, foto.pk, variante])

    def test_miniatura_e_visualizacao_jpeg_com_orientacao_e_cache(self):
        foto, original = self._foto()
        with patch.object(self.storage, "open", wraps=self.storage.open) as abrir:
            for variante, altura in (("miniatura", 480), ("visualizar", 1600)):
                with self.subTest(variante=variante):
                    resposta = self.client.get(self._url_foto(foto, variante))
                    self.assertEqual(resposta.status_code, 200)
                    self.assertEqual(resposta["Content-Type"], "image/jpeg")
                    self.assertIn("private", resposta["Cache-Control"])
                    self.assertEqual(resposta["X-Content-Type-Options"], "nosniff")
                    self.assertLess(len(resposta.content), len(original))
                    with Image.open(BytesIO(resposta.content)) as imagem:
                        self.assertEqual(imagem.size, (altura // 2, altura))
                        self.assertNotIn(274, imagem.getexif())
                    repetida = self.client.get(self._url_foto(foto, variante))
                    self.assertEqual(repetida.content, resposta.content)
            self.assertEqual(abrir.call_count, 2)

    def test_original_e_baixado_como_anexo_e_preserva_bytes(self):
        foto, original = self._foto(nome="conferência.jpg")
        self.client.force_login(self.leitor)
        resposta = self.client.get(self._url_foto(foto, "original"))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/octet-stream")
        self.assertIn("attachment;", resposta["Content-Disposition"])
        self.assertIn("confer%C3%AAncia.jpg", resposta["Content-Disposition"])
        self.assertIn("no-store", resposta["Cache-Control"])
        self.assertEqual(b"".join(resposta.streaming_content), original)

    def test_novo_upload_e_privado_e_original_legado_permanece_acessivel(self):
        legada, original = self._foto(nome="legada.jpg")
        privado = InMemoryStorage()
        url = reverse("obras:diario_editar", args=[self.diario.pk])
        with patch("obras.services.diario_midias.private_media_storage", privado, create=True):
            resposta = self.client.post(url, {
                "obra": self.obra.pk, "data": self.diario.data.isoformat(),
                "fotos": [SimpleUploadedFile("nova.jpg", original, content_type="image/jpeg")],
            })
            self.assertEqual(resposta.status_code, 302)
            nova = self.diario.fotos.exclude(pk=legada.pk).get()
            self.assertTrue(nova.arquivo.name.startswith(PREFIXO_FOTO_PRIVADA))
            self.assertTrue(privado.exists(nova.arquivo.name))
            self.assertFalse(self.storage.exists(nova.arquivo.name))
            self.assertTrue(self.storage.exists(legada.arquivo.name))
            for foto in (legada, nova):
                with self.subTest(foto=foto.pk):
                    self.assertEqual(self.client.get(self._url_foto(foto)).status_code, 200)
                    resposta = self.client.get(self._url_foto(foto, "original"))
                    self.assertEqual(b"".join(resposta.streaming_content), original)

    def test_falha_no_storage_privado_descarta_uploads_parciais(self):
        _, original = self._foto(nome="legada.jpg")
        privado = InMemoryStorage()
        salvar_original = privado.save
        nomes_iniciais = []

        def falhar_ao_salvar_segunda(nome, arquivo, **opcoes):
            if nome.endswith("segunda.jpg"):
                raise OSError("Storage indisponível")
            novo_nome = salvar_original(nome, arquivo, **opcoes)
            nomes_iniciais.append(novo_nome)
            return novo_nome

        with (
            patch("obras.services.diario_midias.private_media_storage", privado, create=True),
            patch.object(privado, "save", side_effect=falhar_ao_salvar_segunda),
        ):
            resposta = self.client.post(reverse("obras:diario_editar", args=[self.diario.pk]), {
                "obra": self.obra.pk, "data": self.diario.data.isoformat(), "efetivo": 10,
                "fotos": [
                    SimpleUploadedFile(nome, original, content_type="image/jpeg")
                    for nome in ("primeira.jpg", "segunda.jpg")
                ],
            })
        self.assertContains(resposta, "Não foi possível salvar as fotos")
        self.assertEqual(len(nomes_iniciais), 1)
        self.assertFalse(privado.exists(nomes_iniciais[0]))
        self.diario.refresh_from_db()
        self.assertEqual(self.diario.efetivo, 7)
        self.assertEqual(self.diario.fotos.count(), 1)

    def test_foto_privada_ausente_nao_utiliza_arquivo_publico_homonimo(self):
        _, original = self._foto()
        caminho = f"{PREFIXO_FOTO_PRIVADA}teste.jpg"
        self.storage.save(caminho, ContentFile(original))
        foto = FotoDiarioObra.objects.create(diario=self.diario, arquivo=caminho)
        privado = InMemoryStorage()
        with patch("obras.services.diario_midias.private_media_storage", privado):
            for variante in ("miniatura", "visualizar", "original"):
                with self.subTest(variante=variante):
                    self.assertEqual(self.client.get(self._url_foto(foto, variante)).status_code, 404)

    def test_falha_na_primeira_foto_nao_cria_diario_e_preserva_formulario(self):
        _, original = self._foto()
        privado = InMemoryStorage()
        salvar_original = privado.save
        caminhos = []

        def salvar_e_falhar(nome, arquivo, **opcoes):
            caminhos.append(salvar_original(nome, arquivo, **opcoes))
            raise OSError("Falha depois da gravação física")

        nova_data = self.diario.data + timedelta(days=1)
        url = reverse("obras:diario_novo")
        with (
            patch("obras.services.diario_midias.private_media_storage", privado),
            patch.object(privado, "save", side_effect=salvar_e_falhar),
        ):
            resposta = self.client.post(url, {
                "obra": self.obra.pk, "data": nova_data.isoformat(), "efetivo": "10",
                "clima": DiarioObra.Clima.NUBLADO, "equipe_presente": "Equipe sintética",
                "ocorrencias": "Ocorrência sintética",
                "fotos": [SimpleUploadedFile("nova.jpg", original, content_type="image/jpeg")],
            })
        self.assertContains(resposta, "Não foi possível salvar as fotos")
        self.assertContains(resposta, "Equipe sintética")
        self.assertContains(resposta, "Ocorrência sintética")
        self.assertEqual(resposta.context["dados_formulario"]["efetivo"], "10")
        self.assertEqual(resposta.context["dados_formulario"]["clima"], DiarioObra.Clima.NUBLADO)
        self.assertEqual(len(caminhos), 1)
        self.assertFalse(privado.exists(caminhos[0]))
        self.assertFalse(DiarioObra.objects.filter(obra=self.obra, data=nova_data).exists())

    def test_erro_de_banco_apos_gravar_foto_remove_arquivo_e_reverte_edicao(self):
        legada, original = self._foto()
        privado = InMemoryStorage()
        salvar_original = privado.save
        caminhos = []

        def registrar_nome(nome, arquivo, **opcoes):
            novo = salvar_original(nome, arquivo, **opcoes)
            caminhos.append(novo)
            return novo

        with (
            patch("obras.services.diario_midias.private_media_storage", privado),
            patch.object(privado, "save", side_effect=registrar_nome),
            patch.object(FotoDiarioObra, "save", side_effect=IntegrityError("Falha sintética")),
        ):
            resposta = self.client.post(reverse("obras:diario_editar", args=[self.diario.pk]), {
                "obra": self.obra.pk, "data": self.diario.data.isoformat(), "efetivo": "12",
                "fotos": [SimpleUploadedFile("nova.jpg", original, content_type="image/jpeg")],
            })
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(caminhos), 1)
        self.assertFalse(privado.exists(caminhos[0]))
        self.diario.refresh_from_db()
        self.assertEqual(self.diario.efetivo, 7)
        self.assertEqual(list(self.diario.fotos.values_list("pk", flat=True)), [legada.pk])

    def test_upload_recusa_formato_sem_suporte_antes_de_gravar(self):
        with BytesIO() as arquivo, Image.new("RGB", (64, 64), "brown") as imagem:
            imagem.save(arquivo, "ICO")
            dados = arquivo.getvalue()
        privado = InMemoryStorage()
        with (
            patch("obras.services.diario_midias.private_media_storage", privado),
            patch.object(privado, "save", wraps=privado.save) as salvar,
        ):
            resposta = self.client.post(reverse("obras:diario_editar", args=[self.diario.pk]), {
                "obra": self.obra.pk, "data": self.diario.data.isoformat(),
                "fotos": [SimpleUploadedFile("icone.ico", dados, content_type="image/x-icon")],
            })
        self.assertEqual(resposta.status_code, 200)
        salvar.assert_not_called()
        self.assertEqual(self.diario.fotos.count(), 0)

    def test_foto_indisponivel_corrompida_e_variante_desconhecida(self):
        ausente = FotoDiarioObra.objects.create(diario=self.diario, arquivo="obras/diarios/ausente.jpg")
        corrompida, _ = self._foto(nome="invalida.jpg", dados=b"<script>arquivo invalido</script>")
        for variante in ("miniatura", "visualizar", "original"):
            with self.subTest(variante=variante):
                self.assertEqual(self.client.get(self._url_foto(ausente, variante)).status_code, 404)
        self.assertEqual(self.client.get(self._url_foto(corrompida)).status_code, 404)
        self.assertEqual(self.client.get(self._url_foto(corrompida, "desconhecida")).status_code, 404)
        self.assertEqual(self.client.post(self._url_foto(corrompida)).status_code, 405)

    def test_detalhe_e_foto_exigem_obras_e_vinculo_ao_diario(self):
        foto, _ = self._foto()
        detalhe = reverse("obras:diario_detalhe", args=[self.diario.pk])
        outro = DiarioObra.objects.create(obra=self.obra, data=self.diario.data + timedelta(days=1))
        for variante in ("miniatura", "visualizar", "original"):
            self.assertEqual(self.client.get(self._url_foto(foto, variante, outro)).status_code, 404)
        self.assertEqual(self.client.get(self._url_foto(foto)).status_code, 200)
        self.client.logout()
        urls = [detalhe, self._url_foto(foto), self._url_foto(foto, "original")]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)
        sem_acesso = get_user_model().objects.create_user(username="diario-midias-sem-acesso")
        self.client.force_login(sem_acesso)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.leitor)
        resposta = self.client.get(detalhe)
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(resposta.context["pode_editar_diario"])

    def test_listagem_conta_fotos_sem_resolver_urls_ou_buscar_arquivos(self):
        self._foto("primeira.jpg")
        self._foto("segunda.jpg")
        with (
            patch.object(self.storage, "open", side_effect=AssertionError("A lista abriu a mídia")),
            patch.object(self.storage, "url", side_effect=AssertionError("A lista gerou uma URL de arquivo")),
            CaptureQueriesContext(connection) as consultas,
        ):
            resposta = self.client.get(reverse("obras:diario_lista"))
        self.assertEqual(resposta.context["diarios"][0].qtd_fotos, 2)
        tabela_fotos = FotoDiarioObra._meta.db_table
        self.assertTrue(all("COUNT(" in q["sql"] for q in consultas if tabela_fotos in q["sql"]))

    def test_detalhe_prefetch_mantem_consultas_ao_aumentar_quantidade_de_fotos(self):
        url = reverse("obras:diario_detalhe", args=[self.diario.pk])
        with CaptureQueriesContext(connection) as sem_fotos:
            resposta = self.client.get(url)
        self.assertEqual(resposta.context["diario"].qtd_fotos, 0)
        FotoDiarioObra.objects.bulk_create([
            FotoDiarioObra(diario=self.diario, arquivo=f"obras/diarios/lote_{i}.jpg")
            for i in range(24)
        ])
        with CaptureQueriesContext(connection) as com_fotos:
            resposta = self.client.get(url)
        self.assertEqual(resposta.context["diario"].qtd_fotos, 24)
        self.assertEqual(len(com_fotos), len(sem_fotos))

    def test_detalhe_conserva_cronograma_legado_e_respeita_permissao_de_concretagem(self):
        atividade = AtividadePlanejamento.objects.create(
            obra=self.obra, chave="atividade-diario-midia", nome_tarefa="Etapa registrada",
        )
        DiarioAtividadePlanejada.objects.create(
            diario=self.diario, atividade=atividade, semana=41, inicio_semana=self.diario.data,
            origem=DiarioAtividadePlanejada.Origem.PRE_HABITESE,
        )
        DiarioAtividadeAdicional.objects.create(
            diario=self.diario, descricao="Atividade histórica", justificativa="Justificativa registrada",
        )
        concretagem = Concretagem.objects.create(
            obra=self.obra, data_programada=self.diario.data, codigo="CONC-DIARIO-01",
        )
        Concretagem.objects.create(
            obra=self.obra, data_programada=self.diario.data, codigo="CONC-DIARIO-02",
            status=Concretagem.Status.CANCELADA,
        )
        outra_obra = Obra.objects.create(nome="Outra obra sintética", codigo="OB-DIA-MIDIA-02")
        Concretagem.objects.create(
            obra=outra_obra, data_programada=self.diario.data, codigo="CONC-DIARIO-03",
        )
        Concretagem.objects.create(
            obra=self.obra, data_programada=self.diario.data + timedelta(days=1), codigo="CONC-DIARIO-04",
        )
        self.client.force_login(self.leitor)
        url = reverse("obras:diario_detalhe", args=[self.diario.pk])
        resposta = self.client.get(url)
        self.assertContains(resposta, "Etapa registrada")
        self.assertContains(resposta, "Atividade histórica")
        self.assertContains(resposta, "Detalhe histórico")
        self.assertEqual(resposta.context["concretagens_dia"], [])
        PermissaoAcao.objects.create(usuario=self.leitor, modulo=ModuloSistema.OBRAS, acao="concretagem", permitido=True)
        resposta = self.client.get(url)
        self.assertEqual([registro.pk for registro in resposta.context["concretagens_dia"]], [concretagem.pk])
