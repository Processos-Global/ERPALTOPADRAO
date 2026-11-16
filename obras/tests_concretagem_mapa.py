"""Testes da concretagem — fase 3: mapa, formatos, agenda, indicadores e diário.

    manage.py test obras.tests_concretagem_mapa --settings=obras.test_settings_concretagem
"""
import datetime
import json
from urllib.parse import urlencode
from decimal import Decimal

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from obras.models import (
    CelulaMapa, Concretagem, DiarioObra, FormatoDesenho, LaudoConcretagem, MapaLocal, SobraConcreto,
)
from obras.services.concretagem import fluxo, indicadores
from obras.services.concretagem import mapa as svc
from obras.tests_concretagem_execucao import BaseExecucao
from usuarios.models import Notificacao

S = Concretagem.Status


def _json(client, url, dados):
    return client.post(url, json.dumps(dados), content_type="application/json", HTTP_X_REQUESTED_WITH="XMLHttpRequest")


class FormatosTests(BaseExecucao):
    def test_gerente_cria_direto(self):
        self.client.force_login(self.gerente)
        r = _json(self.client, reverse("obras:concretagem_formato_novo"), {"nome": "Casa A", "linhas": 4, "colunas": 5, "fora": [[1, 1], [9, 9]]})
        self.assertTrue(r.json()["ok"])
        f = FormatoDesenho.objects.get(nome="Casa A")
        self.assertEqual(f.celulas_fora, [[1, 1]])  # célula fora da grade descartada

    def test_qualquer_um_que_preenche_cria_e_edita_sem_aprovacao(self):
        self.client.force_login(self.eng)  # não é gerente
        r = _json(self.client, reverse("obras:concretagem_formato_novo"), {"nome": "Sobrado B", "linhas": 3, "colunas": 4, "fora": [[3, 4]]})
        self.assertTrue(r.json()["ok"])
        f = FormatoDesenho.objects.get(nome="Sobrado B")
        self.assertTrue(f.ativo)
        self.assertEqual(f.criado_por, self.eng)
        _json(self.client, reverse("obras:concretagem_formato_editar", args=[f.pk]), {"nome": "Sobrado B2", "linhas": 3, "colunas": 4, "fora": []})
        f.refresh_from_db()
        self.assertEqual((f.nome, f.celulas_fora), ("Sobrado B2", []))
        self.assertEqual(Notificacao.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_criar_pelo_mapa_ja_aplica_no_local(self):
        voltar = reverse("obras:concretagem_mapa", args=[self.obra.pk]) + f"?local={self.laje.pk}"
        url = reverse("obras:concretagem_formato_novo") + "?" + urlencode({"obra": self.obra.pk, "local": self.laje.pk, "voltar": voltar})
        self.assertContains(self.client.get(url), "Salvar e usar")
        r = _json(self.client, url, {"nome": "Laje L", "linhas": 4, "colunas": 4, "fora": [[1, 1]]})
        self.assertEqual(r.json()["redirecionar"], voltar)
        mapa = MapaLocal.objects.get(local=self.laje)
        self.assertEqual((mapa.formato.nome, mapa.linhas, mapa.celulas_fora), ("Laje L", 4, [[1, 1]]))

    def test_editar_contorno_apaga_celulas_que_ficaram_fora(self):
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        uso = self.conc.utilizacoes.get()
        f = FormatoDesenho.objects.create(nome="Q", linhas=3, colunas=3)
        mapa = svc.definir_mapa(self.laje, self.eng, formato=f)
        svc.pintar(mapa, [[1, 1], [2, 2]], f"u{uso.pk}", self.eng)
        svc.salvar_formato(self.eng, "Q", 3, 3, [[1, 1]], formato=f)
        self.assertEqual(list(mapa.celulas.values_list("linha", "coluna")), [(2, 2)])

    def test_leitor_nao_propoe(self):
        self.client.force_login(self.leitor)
        self.assertEqual(self.client.get(reverse("obras:concretagem_formato_novo")).status_code, 403)
        self.assertEqual(self.client.get(reverse("obras:concretagem_formatos")).status_code, 200)

    def test_formato_em_uso_nao_muda_tamanho(self):
        f = FormatoDesenho.objects.create(nome="Fixo", linhas=3, colunas=3)
        svc.definir_mapa(self.laje, self.eng, formato=f)
        with self.assertRaises(fluxo.FluxoError):
            svc.salvar_formato(self.gerente, "Fixo", 4, 3, [], formato=f)


class MapaTests(BaseExecucao):
    def setUp(self):
        super().setUp()
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "6"})
        self.client.post(self.url("sobra_criar"), {"volume_sobra": "2", "destino": "CALCADA", "caminhao": cam.pk})
        self.uso = self.conc.utilizacoes.get()
        self.sobra = self.conc.sobras.get()
        self.formato = FormatoDesenho.objects.create(nome="L", linhas=3, colunas=3, celulas_fora=[[1, 3]])
        self.mapa_url = reverse("obras:concretagem_mapa", args=[self.obra.pk])
        self.pintar_url = reverse("obras:concretagem_mapa_pintar", args=[self.obra.pk, self.laje.pk])

    def test_grade_so_por_formato_e_criar_volta_ao_mapa(self):
        definir = reverse("obras:concretagem_mapa_definir", args=[self.obra.pk, self.laje.pk])
        self.client.post(definir, {"linhas": "5", "colunas": "5"})  # tamanho livre não é mais aceito
        self.assertFalse(MapaLocal.objects.filter(local=self.laje).exists())
        resp = self.client.get(self.mapa_url + f"?local={self.laje.pk}")
        self.assertContains(resp, f'data-formato="{self.formato.pk}"')
        self.assertNotContains(resp, 'name="linhas"')
        self.assertContains(resp, "voltar=")  # criar/editar formato retorna ao mapa
        self.assertContains(resp, reverse("obras:concretagem_formato_editar", args=[self.formato.pk]))
        voltar = self.mapa_url + f"?local={self.laje.pk}"
        novo = reverse("obras:concretagem_formato_novo") + "?" + urlencode({"obra": self.obra.pk, "voltar": voltar})
        r = _json(self.client, novo, {"nome": "Novo L", "linhas": 4, "colunas": 4, "fora": []})
        self.assertEqual(r.json()["redirecionar"], voltar)
        externo = reverse("obras:concretagem_formato_novo") + "?" + urlencode({"voltar": "https://exemplo.com/"})
        r = _json(self.client, externo, {"nome": "Outro L", "linhas": 4, "colunas": 4, "fora": []})
        self.assertEqual(r.json()["redirecionar"], reverse("obras:concretagem_formatos"))

    def test_sobras_separadas_e_escondidas_na_lista(self):
        svc.definir_mapa(self.laje, self.eng, formato=self.formato)
        html = self.client.get(self.mapa_url + f"?local={self.laje.pk}").content.decode()
        uso, sobras = html.index(f'data-item="u{self.uso.pk}"'), html.index("data-sobras hidden")
        self.assertLess(uso, sobras)  # uso fica na lista principal
        self.assertGreater(html.index(f'data-item="s{self.sobra.pk}"'), sobras)  # sobra na parte escondida
        self.assertIn("Ver sobras (1)", html)

    def test_cores_atribuidas_e_distintas(self):
        self.assertTrue(self.uso.cor and self.sobra.cor)
        self.assertNotEqual(self.uso.cor, self.sobra.cor)

    def test_definir_pintar_respeitando_contorno(self):
        self.client.post(reverse("obras:concretagem_mapa_definir", args=[self.obra.pk, self.laje.pk]), {"formato": self.formato.pk})
        mapa = MapaLocal.objects.get(local=self.laje)
        self.assertEqual((mapa.linhas, mapa.colunas, mapa.celulas_fora), (3, 3, [[1, 3]]))
        r = _json(self.client, self.pintar_url, {"item": f"u{self.uso.pk}", "celulas": [[1, 1], [1, 3], [9, 9]]})
        self.assertEqual(r.json()["alteradas"], 1)  # fora do contorno e fora da grade ignoradas
        _json(self.client, self.pintar_url, {"item": f"s{self.sobra.pk}", "celulas": [[2, 2]]})
        self.assertEqual(svc.estado_mapa(mapa), {"1,1": f"u{self.uso.pk}", "2,2": f"s{self.sobra.pk}"})
        _json(self.client, self.pintar_url, {"item": "", "celulas": [[1, 1]]})
        self.assertEqual(CelulaMapa.objects.count(), 1)
        resp = self.client.get(self.mapa_url + f"?local={self.laje.pk}")
        self.assertContains(resp, 'id="dados-mapa"')

    def test_item_invalido_e_leitor(self):
        svc.definir_mapa(self.laje, self.eng, 5, 5)
        r = _json(self.client, self.pintar_url, {"item": "u999999", "celulas": [[1, 1]]})
        self.assertEqual(r.status_code, 400)
        self.client.force_login(self.leitor)
        self.assertEqual(_json(self.client, self.pintar_url, {"item": f"u{self.uso.pk}", "celulas": [[1, 1]]}).status_code, 403)
        self.assertEqual(self.client.get(self.mapa_url).status_code, 200)

    def test_reduzir_grade_apaga_celulas_de_fora(self):
        mapa = svc.definir_mapa(self.laje, self.eng, 5, 5)
        svc.pintar(mapa, [[5, 5], [1, 1]], f"u{self.uso.pk}", self.eng)
        svc.definir_mapa(self.laje, self.eng, 3, 3)
        self.assertEqual(list(mapa.celulas.values_list("linha", "coluna")), [(1, 1)])

    def test_sobra_recebida_de_outra_obra_aparece_na_paleta(self):
        outra = fluxo.aceitar(fluxo.solicitar(fluxo.criar_concretagem(
            Concretagem(obra=self.outra_obra, concreteira=self.forn, engenheiro=self.eng,
                        data_programada=datetime.date(2026, 12, 2), horario_programado=datetime.time(8),
                        fck_projeto=Decimal("30"), volume_solicitado=Decimal("5")),
            [{"local": self.local_outra, "descricao": "", "volume_previsto": Decimal("5")}], self.eng), self.eng), self.gerente)
        from obras.models import CaminhaoConcretagem
        cam = CaminhaoConcretagem.objects.create(concretagem=outra, ordem=1, volume_entregue=Decimal("5"))
        SobraConcreto.objects.create(concretagem=outra, caminhao=cam, volume_sobra=Decimal("1"), destino="OUTRA_OBRA", obra_destino=self.obra)
        tipos = [i["tipo"] for i in svc.itens_paleta(self.laje)]
        self.assertIn("Sobra recebida", tipos)


class AgendaIndicadoresDiarioTests(BaseExecucao):
    def _finalizar(self, volume="8", entregue="8"):
        cam = self._caminhao(entregue)
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": str(Decimal(entregue) - 1)})
        self.client.post(self.url("sobra_criar"), {"volume_sobra": "1", "destino": "DESCARTADO", "caminhao": cam.pk})
        self._serie_completa(cam)
        self._anexar_nf(cam)
        self.client.post(self.url("finalizar"))
        self.conc.refresh_from_db()
        self.assertEqual(self.conc.status, S.EXECUTADA)

    def test_agenda_mostra_concretagem_e_rompimento(self):
        self._finalizar()
        base = self.conc.executada_em.date() + datetime.timedelta(days=7)
        resp = self.client.get(reverse("obras:concretagem_agenda") + f"?mes={base.year}-{base.month:02d}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"7d · {self.conc.codigo}")
        self.assertContains(resp, "Registrar envio")

    def test_indicadores_calculos(self):
        self._finalizar(entregue="16")  # solicitado 15, entregue 16, sobra 1 descartada
        self.client.post(self.url("cps_enviados"), {"enviado_por_nome": "Carlos"})
        LaudoConcretagem.objects.create(concretagem=self.conc, idade_dias=28, resistencia_mpa=Decimal("27"))
        dados = indicadores.calcular(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        r = dados["resumo"]
        self.assertEqual(r["volume_entregue"], Decimal("16.00"))
        self.assertEqual(r["desvio_pct"], Decimal("6.7"))   # (16-15)/15
        self.assertEqual(r["sobra_pct"], Decimal("6.3"))    # 1/16
        self.assertEqual(r["perda_pct"], Decimal("6.3"))
        self.assertEqual(r["laudos_reprovados"], 1)          # 27 < 28,5
        self.assertEqual(r["media_fck_28"], Decimal("90.0"))
        url = reverse("obras:concretagem_indicadores") + "?inicio=2026-01-01&fim=2026-12-31"
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.leitor)  # sem a permissão Concretagem
        self.assertEqual(self.client.get(url + "&aba=uso").status_code, 403)
        self.client.force_login(self.gerente)
        resp = self.client.get(url + "&aba=uso")
        self.assertContains(resp, "Tempo por etapa")

    def test_diario_mostra_concretagens_do_dia(self):
        dados = self.client.get(reverse("obras:concretagem_api_dia") + f"?obra={self.obra.pk}&data=2026-12-01").json()
        self.assertEqual([c["codigo"] for c in dados["concretagens"]], [self.conc.codigo])
        DiarioObra.objects.create(obra=self.obra, data=datetime.date(2026, 12, 1), servicos_executados="Concretagem da laje", registrado_por=self.eng)
        resp = self.client.get(reverse("obras:diario_lista"))
        self.assertContains(resp, "Concretagens do dia")
        self.assertContains(resp, self.conc.codigo)

    def test_paginas_novas_renderizam(self):
        self.client.force_login(self.gerente)
        for nome, args in [
            ("concretagem_painel", []), ("concretagem_agenda", []), ("concretagem_indicadores", []),
            ("concretagem_formatos", []), ("concretagem_formato_novo", []),
            ("concretagem_mapa", [self.obra.pk]),
        ]:
            with self.subTest(nome=nome):
                self.assertEqual(self.client.get(reverse(f"obras:{nome}", args=args)).status_code, 200)


class AcessoMapaTests(BaseExecucao):
    def test_painel_leva_ao_mapa_sem_escolher_obra(self):
        painel = self.client.get(reverse("obras:concretagem_painel"))
        self.assertContains(painel, reverse("obras:concretagem_mapa_inicio"))
        resp = self.client.get(reverse("obras:concretagem_mapa_inicio"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Escolha a obra")
        self.assertNotContains(resp, 'id="dados-mapa"')
        # Obra escolhida, sem local: pede o local e não abre nenhum mapa.
        svc.definir_mapa(self.laje, self.eng, 4, 4)
        resp = self.client.get(reverse("obras:concretagem_mapa", args=[self.obra.pk]))
        self.assertContains(resp, "Escolha o local de uso")
        self.assertNotContains(resp, 'id="dados-mapa"')
        detalhe = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk]))
        self.assertContains(detalhe, reverse("obras:concretagem_mapa", args=[self.obra.pk]))


class ListaCaminhoesMapaTests(BaseExecucao):
    def test_tempo_total_e_lista_no_mapa(self):
        from datetime import time
        from obras.models import CaminhaoConcretagem, SerieMoldagem

        cam = CaminhaoConcretagem(ordem=1, termino_descarga=time(0, 30))
        self.assertEqual(svc._dados_caminhao(cam)["tempo_total"], "")  # sem série de moldagem
        cam.serie_moldagem = SerieMoldagem(inicio_mistura=time(23, 0))
        self.assertEqual(svc._dados_caminhao(cam)["tempo_total"], "1h30")  # passa da meia-noite
        self.assertEqual(svc._dados_caminhao(None)["caminhao"], "")

        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        svc.definir_mapa(self.laje, self.eng, 4, 4)
        resp = self.client.get(reverse("obras:concretagem_mapa", args=[self.obra.pk]) + f"?local={self.laje.pk}")
        self.assertContains(resp, "Caminhões deste local")
        self.assertContains(resp, cam.rotulo)
        self.assertContains(resp, "data-borracha")


class AcessoFacilMapaTests(BaseExecucao):
    def test_menu_e_botao_pintar_no_mapa(self):
        self.assertContains(self.client.get(reverse("obras:menu")), reverse("obras:concretagem_mapa_inicio"))
        cam = self._caminhao("8")
        self.client.post(self.url("uso_criar"), {"caminhao": cam.pk, "local": self.laje.pk, "volume_utilizado": "8"})
        uso = self.conc.utilizacoes.get()
        detalhe = self.client.get(reverse("obras:concretagem_detalhe", args=[self.conc.pk])).content.decode()
        link = reverse("obras:concretagem_mapa", args=[self.obra.pk]) + f"?local={self.laje.pk}&item=u{uso.pk}"
        self.assertIn(link, detalhe)
        svc.definir_mapa(self.laje, self.eng, 6, 6)
        resp = self.client.get(reverse("obras:concretagem_mapa", args=[self.obra.pk]) + f"?local={self.laje.pk}&item=u{uso.pk}")
        self.assertContains(resp, f'data-item="u{uso.pk}"')
        self.assertContains(resp, "mp-pagina")
