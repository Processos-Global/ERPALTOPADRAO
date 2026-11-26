from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.models import Count

from compras.models import ContratacaoCompra


class Command(BaseCommand):
    help = "Lista os pares processo/fornecedor com mais de uma contratação ativa."

    def add_arguments(self, parser):
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS, choices=tuple(connections))

    def handle(self, *args, **options):
        ativas = ContratacaoCompra.objects.using(options["database"]).filter(cancelada=False)
        grupos = (
            ativas.values("processo_id", "fornecedor_id")
            .annotate(total=Count("pk"))
            .filter(total__gt=1)
            .order_by("processo_id", "fornecedor_id")
        )

        total_grupos = 0
        for grupo in grupos.iterator():
            processo_id = grupo["processo_id"]
            fornecedor_id = grupo["fornecedor_id"]
            ids = ativas.filter(processo_id=processo_id, fornecedor_id=fornecedor_id).order_by("pk")
            ids_formatados = ", ".join(str(pk) for pk in ids.values_list("pk", flat=True).iterator())
            self.stdout.write(
                f"processo_id={processo_id}, fornecedor_id={fornecedor_id}, "
                f"total={grupo['total']}, contratacoes=[{ids_formatados}]"
            )
            total_grupos += 1

        if total_grupos:
            raise CommandError(f"{total_grupos} par(es) com contratações ativas duplicadas.")
        self.stdout.write("Nenhuma contratação ativa duplicada encontrada.")
