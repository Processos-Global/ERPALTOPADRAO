from django.core.management.base import BaseCommand

from financeiro.models import PlanoFinanceiro


PLANO_PADRAO = [
    ("1", "CUSTOS DE OBRA", None),
    ("1.1", "Materiais", "1"),
    ("1.2", "Mão de obra", "1"),
    ("1.3", "Equipamentos", "1"),
    ("1.4", "Serviços", "1"),
    ("1.5", "Fretes", "1"),
    ("2", "DESPESAS ADMINISTRATIVAS", None),
    ("2.1", "Escritório", "2"),
    ("2.2", "Sistemas", "2"),
    ("2.3", "Contabilidade", "2"),
    ("2.4", "Marketing", "2"),
    ("3", "IMPOSTOS", None),
    ("4", "FINANCEIRO", None),
    ("4.1", "Juros", "4"),
    ("4.2", "Tarifas bancárias", "4"),
]


class Command(BaseCommand):
    help = "Cria o plano financeiro inicial sem apagar classificações já existentes."

    def handle(self, *args, **options):
        criados = 0
        cache = {}
        for codigo, nome, pai_codigo in PLANO_PADRAO:
            pai = cache.get(pai_codigo) if pai_codigo else None
            obj, criado = PlanoFinanceiro.objects.get_or_create(
                codigo=codigo,
                defaults={"nome": nome, "pai": pai, "tipo": PlanoFinanceiro.Tipo.DESPESA, "ativo": True},
            )
            cache[codigo] = obj
            criados += int(criado)
        self.stdout.write(self.style.SUCCESS(f"Plano financeiro inicializado: {criados} novas classificações."))
