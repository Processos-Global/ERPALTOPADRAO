from collections import Counter
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.models import Count
from django.utils import timezone

from compras.models import PedidoCompra, ReservaEstoqueCompra


class Command(BaseCommand):
    help = "Diagnostica reservas legadas de Compras. Use --aplicar para liberar apenas o saldo lógico."

    def add_arguments(self, parser):
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS, choices=tuple(connections))
        parser.add_argument("--aplicar", action="store_true")

    def handle(self, *args, **options):
        banco = options["database"]
        reservas = ReservaEstoqueCompra.objects.using(banco)
        aplicar = options["aplicar"]

        self.stdout.write(f"Consulta de reservas legadas em {timezone.localtime().isoformat()}. Banco: {banco}.")
        if not aplicar:
            self._relatar_reservas(reservas)
            self.stdout.write("Diagnóstico concluído. Para liberar o saldo lógico, use --aplicar.")
            return

        ativas = reservas.filter(status=ReservaEstoqueCompra.Status.ATIVA)
        with transaction.atomic(using=banco):
            # Bloqueia apenas as linhas da tabela legada, em ordem fixa.
            ids_ativas = list(ativas.order_by("pk").select_for_update().values_list("pk", flat=True))
            self._relatar_reservas(reservas)
            atualizado_em = timezone.now()
            liberadas = 0
            for indice in range(0, len(ids_ativas), 500):
                liberadas += ativas.filter(pk__in=ids_ativas[indice:indice + 500]).update(
                    status=ReservaEstoqueCompra.Status.LIBERADA,
                    quantidade_disponivel=Decimal("0"),
                    atualizado_em=atualizado_em,
                )
        self.stdout.write(f"Liberação concluída. Reservas atualizadas: {liberadas}.")

    def _relatar_reservas(self, reservas):
        self.stdout.write(
            "A classificação compara a quantidade originalmente reservada à solicitada. "
            "Abrange as reservas registradas. Bloqueios anteriores à gravação ficam fora da consulta."
        )
        contagem = Counter()
        linhas = reservas.values(
            "pk", "status", "quantidade_original", "quantidade_disponivel", "unidade",
            "obra_id", "material_id", "necessidade_id", "necessidade__quantidade_necessaria",
            "necessidade__quantidade_incluida", "necessidade__processo__numero",
            "necessidade__processo__etapa_atual", "necessidade__processo__status",
        ).annotate(total_movimentos=Count("movimentos")).order_by("pk")
        for linha in linhas.iterator(chunk_size=500):
            status = linha["status"]
            contagem[status] += 1
            acao = "LIBERAR_SALDO" if status == ReservaEstoqueCompra.Status.ATIVA else "PRESERVAR"
            cobertura = "TOTAL" if linha["quantidade_original"] >= linha["necessidade__quantidade_necessaria"] else "PARCIAL"
            self.stdout.write(
                f"reserva={linha['pk']} estado={status} "
                f"obra={linha['obra_id']} material={linha['material_id']} "
                f"processo={linha['necessidade__processo__numero']} "
                f"etapa={linha['necessidade__processo__etapa_atual']} "
                f"estado_processo={linha['necessidade__processo__status']} "
                f"necessidade={linha['necessidade_id']} solicitada={linha['necessidade__quantidade_necessaria']} "
                f"comercial={linha['necessidade__quantidade_incluida']} "
                f"original={linha['quantidade_original']} remanescente={linha['quantidade_disponivel']} "
                f"unidade={linha['unidade']} movimentos={linha['total_movimentos']} "
                f"cobertura_original={cobertura} proposta={acao}"
            )
        resumo = ", ".join(f"{status}={contagem[status]}" for status in ReservaEstoqueCompra.Status.values)
        self.stdout.write(f"Resumo de reservas: {resumo}.")
        pedidos = (
            PedidoCompra.objects.using(reservas.db)
            .filter(processo_id__in=reservas.values("necessidade__processo_id"))
            .order_by()
            .values("status")
            .annotate(total=Count("pk"))
        )
        totais_pedidos = {linha["status"]: linha["total"] for linha in pedidos}
        resumo_pedidos = ", ".join(f"{status}={totais_pedidos.get(status, 0)}" for status in PedidoCompra.Status.values)
        self.stdout.write(f"Pedidos dos processos vinculados por status: {resumo_pedidos}.")
