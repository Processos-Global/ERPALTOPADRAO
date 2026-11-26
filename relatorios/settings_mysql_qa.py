"""MySQL temporário com nomes e conta exclusivos por execução de QA.

O provisionamento fica fora das configurações da aplicação. Use uma instância
descartável vinculada ao loopback e limite a conta aos dois schemas de QA.
"""
import os

import config  # noqa: F401  # Instala o adaptador PyMySQL, sem importar config.settings.
from relatorios.isolamento_testes import configuracao_mysql_isolada
from relatorios.test_settings import *  # noqa: F403

DATABASES = {"default": configuracao_mysql_isolada()}
if os.environ.get("SAARI_QA_MYSQL_MIGRATIONS") == "1":
    INSTALLED_APPS = [*INSTALLED_APPS, "orcamento"]  # noqa: F405
    MIGRATION_MODULES = {}
