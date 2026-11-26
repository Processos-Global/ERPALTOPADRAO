from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from financeiro.models import AprovacaoTituloFinanceiro, Pagamento, RelatorioPagamento, TituloPagar
from financeiro.services.pagamentos import programar_pagamento, registrar_pagamento
from obras.models import Obra


class MalotePorObraTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser("malote-obras")
        cls.obra = Obra.objects.create(codigo="MAL-A", nome="Obra sintética A")
        cls.outra = Obra.objects.create(codigo="MAL-B", nome="Obra sintética B")

    def criar_aprovacao(self, numero, obra, origem=TituloPagar.Origem.MANUAL):
        titulo = TituloPagar.objects.create(
            numero=numero, descricao="Obrigação sintética", beneficiario_nome="Fornecedor sintético",
            status=TituloPagar.Status.APROVADO, origem=origem, obra=obra, ciclo_aprovacao=1,
            vencimento=timezone.localdate(), valor_original=Decimal("42.55"),
        )
        return AprovacaoTituloFinanceiro.objects.create(
            titulo=titulo, ciclo=1, decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO, usuario=self.usuario,
        )

    def emitir(self, *aprovacoes):
        self.client.force_login(self.usuario)
        self.client.post(reverse("financeiro:relatorio_pagamento_emitir"), {
            "aprovacoes": [aprovacao.pk for aprovacao in aprovacoes],
            **{f"meio_{aprovacao.pk}": "BOLETO" for aprovacao in aprovacoes},
        })

    def test_malote_rejeita_obras_diferentes_e_preserva_avulsa_e_compra_na_mesma_obra(self):
        avulsa = self.criar_aprovacao("MAL-1", self.obra)
        compra = self.criar_aprovacao("MAL-2", self.obra, TituloPagar.Origem.COMPRA)
        outra = self.criar_aprovacao("MAL-3", self.outra)
        administrativo = self.criar_aprovacao("MAL-4", None)

        self.emitir(avulsa, outra)
        self.emitir(avulsa, administrativo)
        self.assertFalse(RelatorioPagamento.objects.exists())
        self.emitir(avulsa, compra)
        malote = RelatorioPagamento.objects.get()
        self.assertEqual(malote.valor_total, Decimal("85.10"))
        self.assertEqual(set(malote.itens.values_list("titulo_id", flat=True)), {avulsa.titulo_id, compra.titulo_id})
        self.assertFalse(Pagamento.objects.exists())
        self.emitir(administrativo)
        self.assertEqual(RelatorioPagamento.objects.count(), 2)

    def test_ciclo_sem_aprovacao_vigente_impede_programar_e_pagar(self):
        aprovacao = self.criar_aprovacao("MAL-CICLO", self.obra)
        TituloPagar.objects.filter(pk=aprovacao.titulo_id).update(ciclo_aprovacao=2)
        with self.assertRaises(ValidationError):
            programar_pagamento(aprovacao.titulo, data_programada=timezone.localdate(), usuario=self.usuario)
        with self.assertRaises(ValidationError):
            registrar_pagamento(titulo=aprovacao.titulo, usuario=self.usuario)
