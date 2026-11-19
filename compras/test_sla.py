from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.models import (NecessidadeCompra, PedidoCompra, ProcessoCompra, RegraPrazoCompra,
                            TransicaoEtapaCompra)
from compras.services.sla import (criar_regra_prazo, indicador_processo,
                                  indicador_pedido, reconciliar_regra_inicial,
                                  registrar_prazo_entrega,
                                  resumo_sla_processos)
from obras.models import Obra


class PrazoComprasTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_superuser(
            username="sla_admin", email="sla@example.test", password="teste"
        )
        self.obra = Obra.objects.create(nome="Obra SLA", codigo="OB-SLA")

    def regra(self, *, etapa="COTACAO", dias=3):
        return criar_regra_prazo(
            usuario=self.usuario, escopo=RegraPrazoCompra.Escopo.ETAPA,
            etapa=etapa, dias=dias, dias_alerta=1,
            vigente_desde=timezone.localdate() - timedelta(days=1),
            justificativa="Prazo operacional aprovado",
        )

    def test_passagens_por_etapa_preservam_regra_e_reabertura(self):
        regra = self.regra()
        processo = ProcessoCompra.objects.create(
            numero="PC-SLA-1", obra=self.obra, titulo="Compra", criado_por=self.usuario
        )
        atual = processo.transicoes_sla.get(etapa="COTACAO")
        self.assertEqual(atual.regra_id, regra.pk)
        self.assertEqual(atual.prazo_dias, 3)
        processo.etapa_atual = ProcessoCompra.Etapa.COMPATIBILIZACAO
        processo.save(update_fields=["etapa_atual"])
        atual.refresh_from_db()
        self.assertIsNotNone(atual.encerrada_em)
        processo.etapa_atual = ProcessoCompra.Etapa.COTACAO
        processo.save(update_fields=["etapa_atual"])
        ciclos = list(processo.transicoes_sla.filter(etapa="COTACAO"))
        self.assertEqual(len(ciclos), 2)
        self.assertEqual(ciclos[0].prazo_dias, 3)
        self.assertEqual(ciclos[1].motivo, "RETORNO")
        self.assertEqual(indicador_processo(processo)["etapa"]["situacao"], "NO_PRAZO")
        self.assertEqual(indicador_processo(
            processo, referencia=timezone.now() + timedelta(days=4)
        )["etapa"]["situacao"], "ATRASADO")
        nova_regra = self.regra(dias=7)
        self.assertNotEqual(nova_regra.pk, regra.pk)
        ciclos[0].refresh_from_db()
        self.assertEqual(ciclos[0].prazo_dias, 3)

    def test_prazo_util_snapshot_e_filtros_resumo(self):
        criar_regra_prazo(
            usuario=self.usuario, escopo="ETAPA", etapa="COTACAO", dias=2,
            contagem="UTEIS", dias_alerta=1,
            vigente_desde=timezone.localdate() - timedelta(days=1),
            justificativa="Dias úteis sem feriados cadastrados",
        )
        processo = ProcessoCompra.objects.create(numero="PC-SLA-2", obra=self.obra, titulo="Compra")
        passagem = processo.transicoes_sla.get(etapa="COTACAO")
        self.assertEqual(passagem.contagem, "UTEIS")
        self.assertEqual(passagem.prazo_dias, 2)
        self.assertEqual(resumo_sla_processos(ProcessoCompra.objects.filter(pk=processo.pk))["processos_atrasados"], 0)
        self.assertEqual(TransicaoEtapaCompra.objects.filter(processo=processo).count(), 2)

    def test_regra_exige_administrador(self):
        comum = get_user_model().objects.create_user(username="sla_comum", password="teste")
        with self.assertRaises(PermissionDenied):
            criar_regra_prazo(usuario=comum, escopo="ETAPA", etapa="COTACAO", dias=2,
                              vigente_desde=timezone.localdate(), justificativa="Teste")

    def test_telas_e_configuracao_respeitam_filtros_e_permissao(self):
        self.regra()
        processo = ProcessoCompra.objects.create(numero="PC-SLA-UI", obra=self.obra, titulo="Compra SLA")
        self.client.force_login(self.usuario)
        lista = self.client.get(reverse("compras:lista_processos"), {"obra": self.obra.pk})
        self.assertContains(lista, "Compra SLA")
        self.assertContains(lista, "Dentro do prazo")
        self.assertContains(self.client.get(reverse("compras:dashboard")), "SLA: processos em atraso")
        self.assertContains(self.client.get(reverse("compras:detalhe_processo", args=[processo.pk])), "Prazo da etapa")
        self.assertEqual(self.client.get(reverse("compras:regras_prazo")).status_code, 200)
        comum = get_user_model().objects.create_user(username="sla_leitor", password="teste")
        self.client.force_login(comum)
        self.assertNotEqual(self.client.get(reverse("compras:regras_prazo")).status_code, 200)

    def test_prazo_comercial_congelado_sem_sobrepor_previsao_contratual(self):
        regra = criar_regra_prazo(
            usuario=self.usuario, escopo="ENTREGA", dias=5,
            vigente_desde=timezone.localdate() - timedelta(days=1),
            justificativa="Prazo comercial para fornecedores comuns",
        )
        processo = ProcessoCompra.objects.create(numero="PC-SLA-PED", obra=self.obra, titulo="Compra")
        fornecedor = Fornecedor.objects.create(nome="Fornecedor SLA")
        contratual = timezone.localdate() + timedelta(days=10)
        pedido = PedidoCompra.objects.create(
            numero="PED-SLA", processo=processo, obra=self.obra, fornecedor=fornecedor,
            previsao_entrega_original=contratual, previsao_entrega_atual=contratual,
        )
        prazo = registrar_prazo_entrega(pedido)
        self.assertEqual(prazo.regra_id, regra.pk)
        self.assertEqual(registrar_prazo_entrega(pedido).pk, prazo.pk)
        indicador = indicador_pedido(pedido)
        self.assertEqual(indicador["previsao"], contratual)
        self.assertEqual(indicador["origem_previsao"], "CONTRATUAL")
        self.assertIsNotNone(indicador["limite_regra_comercial"])

    def test_regra_de_material_aplica_ao_snapshot_da_abertura(self):
        unidade = UnidadeMedida.objects.create(sigla="UN", descricao="Unidade")
        material = Material.objects.create(nome="Material SLA", unidade=unidade)
        especifica = criar_regra_prazo(
            usuario=self.usuario, escopo="ETAPA", etapa="COTACAO", material=material,
            dias=6, vigente_desde=timezone.localdate(), justificativa="Material sob encomenda",
        )
        processo = ProcessoCompra.objects.create(numero="PC-SLA-MAT", obra=self.obra, titulo="Compra")
        NecessidadeCompra.objects.create(
            processo=processo, material=material, descricao="Material SLA", unidade="UN",
            quantidade_necessaria=1, quantidade_incluida=1,
        )
        reconciliar_regra_inicial(processo)
        passagem = processo.transicoes_sla.get(etapa="COTACAO")
        self.assertEqual(passagem.regra_id, especifica.pk)
        self.assertEqual(passagem.prazo_dias, 6)
