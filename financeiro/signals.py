from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from compras.models import ParcelaPrevistaPedido, PedidoCompra, RecebimentoPedido
from financeiro.services.previsoes import sincronizar_previsoes_pedido
from financeiro.services.titulos import criar_ou_atualizar_titulo_recebimento


@receiver(post_save, sender=PedidoCompra)
def pedido_financeiro_atualizado(sender, instance, **kwargs):
    # O pedido pode ser salvo antes de suas parcelas; a sincronização será refinada
    # pelos sinais das parcelas quando elas forem criadas.
    sincronizar_previsoes_pedido(instance)


@receiver(post_save, sender=ParcelaPrevistaPedido)
def parcela_financeira_atualizada(sender, instance, **kwargs):
    sincronizar_previsoes_pedido(instance.pedido)


@receiver(post_delete, sender=ParcelaPrevistaPedido)
def parcela_financeira_excluida(sender, instance, **kwargs):
    if PedidoCompra.objects.filter(pk=instance.pedido_id).exists():
        sincronizar_previsoes_pedido(instance.pedido)


@receiver(post_save, sender=RecebimentoPedido)
def recebimento_financeiro_atualizado(sender, instance, **kwargs):
    criar_ou_atualizar_titulo_recebimento(instance)
