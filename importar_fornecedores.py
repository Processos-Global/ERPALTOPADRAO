from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_PADRAO = "LISTA DE FORNECEDORES- ALTO PADRÃO.xlsx"


def configurar_django():
    manage_py = BASE_DIR / "manage.py"

    if not manage_py.exists():
        raise RuntimeError(f"manage.py não encontrado em: {manage_py}")

    conteudo = manage_py.read_text(encoding="utf-8", errors="ignore")

    padroes = [
        r'os\.environ\.setdefault\(\s*["\']DJANGO_SETTINGS_MODULE["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        r'os\.environ\[\s*["\']DJANGO_SETTINGS_MODULE["\']\s*\]\s*=\s*["\']([^"\']+)["\']',
    ]

    settings_module = None

    for padrao in padroes:
        match = re.search(padrao, conteudo)
        if match:
            settings_module = match.group(1).strip()
            break

    if not settings_module:
        raise RuntimeError(
            "Não foi possível identificar DJANGO_SETTINGS_MODULE no manage.py."
        )

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    sys.path.insert(0, str(BASE_DIR))

    import django
    django.setup()

    return settings_module


def main():
    parser = argparse.ArgumentParser(
        description="Importa fornecedores do Alto Padrão."
    )
    parser.add_argument(
        "arquivo",
        nargs="?",
        default=ARQUIVO_PADRAO,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Exclui fornecedores atuais antes de importar.",
    )
    args = parser.parse_args()

    settings_module = configurar_django()

    from django.core.management import call_command

    caminho = Path(args.arquivo)
    if not caminho.is_absolute():
        caminho = BASE_DIR / caminho
    caminho = caminho.resolve()

    if not caminho.exists():
        print(f"ERRO: planilha não encontrada: {caminho}")
        sys.exit(1)

    print(f"Configuração Django detectada: {settings_module}")
    print(f"Importando: {caminho.name}")

    parametros = [
        "importar_fornecedores_alto_padrao",
        str(caminho),
    ]

    if args.dry_run:
        parametros.append("--dry-run")
    if args.reset:
        parametros.append("--reset")

    call_command(*parametros)


if __name__ == "__main__":
    main()
