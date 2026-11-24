from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Fornecedor, Material, UnidadeMedida
from compras.models import (NecessidadeCompra, PedidoCompra, PrazoEntregaPedido, ProcessoCompra, RegraPrazoCompra,
                            TransicaoEtapaCompra)
from compras.services.sla import (criar_regra_prazo, indicador_processo,
                                  indicador_pedido, reconciliar_regra_inicial,
                                  registrar_prazo_entrega,
                                  resumir_sla_listagem, resumo_sla_processos)
from obras.models import Obra
from planejamento.models.cronograma_suprimentos import (
    CronogramaSuprimentosObra, ImportacaoCronogramaSuprimentos, ItemCronogramaSuprimento,
)


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

    def test_resumo_listagem_preserva_sla_de_reabertura_e_entregas(self):
        referencia = timezone.now()
        inicio = referencia - timedelta(days=14)
        hoje = timezone.localdate(referencia)
        em_andamento, cancelado, legado = ProcessoCompra.objects.bulk_create([
            ProcessoCompra(numero="PC-ABERTO", obra=self.obra, titulo="Compra"),
            ProcessoCompra(numero="PC-CANCELADO", obra=self.obra, titulo="Compra",
                           status=ProcessoCompra.Status.CANCELADO, etapa_atual=ProcessoCompra.Etapa.CONTRATADO),
            ProcessoCompra(numero="PC-LEGADO", obra=self.obra, titulo="Compra"),
        ])
        TransicaoEtapaCompra.objects.bulk_create([
            TransicaoEtapaCompra(
                processo=processo, etapa="COTACAO", iniciada_em=iniciada, encerrada_em=encerrada,
                contagem="UTEIS", prazo_dias=3, limite_em=hoje - timedelta(days=4),
            )
            for processo, iniciada, encerrada in [
                (em_andamento, inicio, inicio + timedelta(days=7)),
                (em_andamento, inicio + timedelta(days=7), None),
                (cancelado, inicio, referencia - timedelta(days=1)),
            ]
        ])
        fornecedor = Fornecedor.objects.create(nome="Fornecedor SLA")
        contratos = PedidoCompra.objects.bulk_create([
            PedidoCompra(
                numero=f"PED-SLA-{i}", processo=em_andamento, obra=self.obra, fornecedor=fornecedor,
                status=status, previsao_entrega_original=previsao, recebido_em=recebido,
            )
            for i, (status, previsao, recebido) in enumerate([
                (PedidoCompra.Status.ENTREGA_PARCIAL, hoje - timedelta(days=1), None),
                (PedidoCompra.Status.CANCELADO, hoje - timedelta(days=1), None),
                (PedidoCompra.Status.ENTREGUE, hoje - timedelta(days=1), referencia),
                (PedidoCompra.Status.CONFIRMADO, None, None),
            ])
        ])
        PrazoEntregaPedido.objects.create(pedido=contratos[-1], limite_em=hoje - timedelta(days=1))
        queryset = ProcessoCompra.objects.filter(pk__in=(em_andamento.pk, cancelado.pk, legado.pk))
        for situacao, ids, atrasados in [
            ("", {em_andamento.pk, cancelado.pk, legado.pk}, 2),
            ("ATRASADO", {em_andamento.pk}, 2),
            ("ENCERRADO", {cancelado.pk}, 0),
            ("SEM_HISTORICO", {legado.pk}, 0),
        ]:
            with self.subTest(situacao=situacao):
                filtrado, novo = resumir_sla_listagem(queryset, referencia, situacao_etapa=situacao)
                anterior = resumo_sla_processos(queryset, referencia, situacao_etapa=situacao)
                anterior.pop("indicadores")
                self.assertEqual(set(filtrado.values_list("pk", flat=True)), ids)
                self.assertEqual(novo, anterior)
                self.assertEqual(novo["pedidos_atrasados"], atrasados)

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
        detalhe = self.client.get(reverse("compras:detalhe_processo", args=[processo.pk]))
        self.assertContains(detalhe, "Prazo da etapa")
        self.assertContains(detalhe, "Data necessária na obra")
        self.assertContains(detalhe, "Não definida")
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

    def test_data_necessaria_vem_do_suprimento_vinculado_e_e_independente_do_atraso_comercial(self):
        hoje = timezone.localdate()
        importacao = ImportacaoCronogramaSuprimentos.objects.create()
        cronograma = CronogramaSuprimentosObra.objects.create(importacao=importacao, obra=self.obra, nome_aba="Obra SLA")
        suprimento = ItemCronogramaSuprimento.objects.create(
            cronograma_obra=cronograma, item="Bancadas", categoria="MATERIAL",
            data_necessaria_obra=hoje + timedelta(days=2),
            prazo_limite_contratacao=hoje - timedelta(days=10),
        )
        processo = ProcessoCompra.objects.create(
            numero="PC-SLA-OBRA", obra=self.obra, titulo="Compra com prazo da obra", item_cronograma=suprimento,
        )
        fornecedor = Fornecedor.objects.create(nome="Fornecedor prazo da obra")
        pedido = PedidoCompra.objects.create(
            numero="PED-SLA-OBRA", processo=processo, obra=self.obra, fornecedor=fornecedor,
            status=PedidoCompra.Status.ENTREGA_PARCIAL,
            previsao_entrega_atual=hoje + timedelta(days=7),
        )
        indicador = indicador_pedido(pedido, hoje)
        self.assertEqual(indicador["previsao"], hoje + timedelta(days=7))
        self.assertEqual(indicador["data_necessaria_obra"], hoje + timedelta(days=2))
        self.assertEqual(indicador["dias_atraso_comercial"], 0)
        self.assertEqual(indicador["defasagem_necessidade"], 5)
        self.assertEqual(indicador["situacao_obra"], "Previsão após a data necessária")
        self.assertIsNone(indicador["realizada"])

        pedido.status = PedidoCompra.Status.ENTREGUE
        pedido.recebido_em = timezone.now()
        entregue = indicador_pedido(pedido, hoje)
        self.assertEqual(entregue["realizada"], hoje)
        self.assertEqual(entregue["defasagem_necessidade"], -2)
        self.assertEqual(entregue["dias_desvio_comercial"], -7)

        outra_obra = Obra.objects.create(nome="Outra obra", codigo="OB-SLA-OUTRA")
        pedido.obra_id = outra_obra.pk
        sem_vinculo = indicador_pedido(pedido, hoje)
        self.assertIsNone(sem_vinculo["data_necessaria_obra"])
        self.assertIsNone(sem_vinculo["defasagem_necessidade"])

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
