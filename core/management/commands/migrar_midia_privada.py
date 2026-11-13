from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


PASTAS_PRIVADAS = ("compras", "financeiro")


class Command(BaseCommand):
    help = "Move documentos sensíveis do MEDIA_ROOT público para PRIVATE_MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        origem_raiz = Path(settings.MEDIA_ROOT)
        destino_raiz = Path(settings.PRIVATE_MEDIA_ROOT)
        dry_run = options["dry_run"]
        movidos = 0
        ignorados = 0

        for pasta in PASTAS_PRIVADAS:
            origem = origem_raiz / pasta
            if not origem.exists():
                continue

            for arquivo in origem.rglob("*"):
                if not arquivo.is_file():
                    continue
                relativo = arquivo.relative_to(origem_raiz)
                destino = destino_raiz / relativo

                if destino.exists():
                    ignorados += 1
                    self.stdout.write(self.style.WARNING(f"Já existe, ignorado: {relativo}"))
                    continue

                self.stdout.write(f"{'Moveria' if dry_run else 'Movendo'}: {relativo}")
                if not dry_run:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(arquivo), str(destino))
                movidos += 1

        if not dry_run:
            # Remove somente diretórios vazios dentro das pastas privadas antigas.
            for pasta in PASTAS_PRIVADAS:
                origem = origem_raiz / pasta
                if origem.exists():
                    for diretorio in sorted(
                        (p for p in origem.rglob("*") if p.is_dir()),
                        key=lambda p: len(p.parts),
                        reverse=True,
                    ):
                        try:
                            diretorio.rmdir()
                        except OSError:
                            pass
                    try:
                        origem.rmdir()
                    except OSError:
                        pass

        self.stdout.write(self.style.SUCCESS(
            f"Concluído. Arquivos {'identificados' if dry_run else 'movidos'}: {movidos}. Ignorados: {ignorados}."
        ))
