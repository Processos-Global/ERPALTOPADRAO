from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from compras.models import (
    GrandeFornecedorProcesso,
    ParcelaGrandeFornecedor,
    ParcelaPrevistaPedido,
    PedidoCompra,
    RateioParcelaGrandeFornecedor,
)
from financeiro.services.previsoes import (
    sincronizar_contas_grande_fornecedor,
    sincronizar_contas_pedido,
)


@receiver(post_save, sender=PedidoCompra)
def pedido_financeiro_atualizado(sender, instance, **kwargs):
    sincronizar_contas_pedido(instance)


@receiver(post_save, sender=ParcelaPrevistaPedido)
def parcela_financeira_atualizada(sender, instance, **kwargs):
    sincronizar_contas_pedido(instance.pedido)


@receiver(post_delete, sender=ParcelaPrevistaPedido)
def parcela_financeira_excluida(sender, instance, **kwargs):
    if PedidoCompra.objects.filter(pk=instance.pedido_id).exists():
        sincronizar_contas_pedido(instance.pedido)


@receiver(post_save, sender=GrandeFornecedorProcesso)
def grande_fornecedor_financeiro_atualizado(sender, instance, **kwargs):
    sincronizar_contas_grande_fornecedor(instance)


@receiver(post_save, sender=ParcelaGrandeFornecedor)
def parcela_gf_financeira_atualizada(sender, instance, **kwargs):
    sincronizar_contas_grande_fornecedor(instance.fluxo)


@receiver(post_delete, sender=ParcelaGrandeFornecedor)
def parcela_gf_financeira_excluida(sender, instance, **kwargs):
    if GrandeFornecedorProcesso.objects.filter(pk=instance.fluxo_id).exists():
        sincronizar_contas_grande_fornecedor(instance.fluxo)


@receiver(post_save, sender=RateioParcelaGrandeFornecedor)
def rateio_gf_financeiro_atualizado(sender, instance, **kwargs):
    sincronizar_contas_grande_fornecedor(instance.parcela.fluxo)


@receiver(post_delete, sender=RateioParcelaGrandeFornecedor)
def rateio_gf_financeiro_excluido(sender, instance, **kwargs):
    if ParcelaGrandeFornecedor.objects.filter(pk=instance.parcela_id).exists():
        sincronizar_contas_grande_fornecedor(instance.parcela.fluxo)
