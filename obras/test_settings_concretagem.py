"""Settings isolados para os testes da concretagem.

Reaproveita `relatorios.test_settings` (SQLite em memória, sem .env, sem
migrações, sem conexão real). Drive desligado e e-mail em memória.
Uso:
    manage.py test obras.tests_concretagem --settings=obras.test_settings_concretagem
"""
from relatorios.test_settings import *  # noqa: F401,F403
from relatorios.test_settings import TEMPLATES

TEMPLATES[0]["OPTIONS"]["context_processors"] = TEMPLATES[0]["OPTIONS"]["context_processors"] + [
    "usuarios.context_processors.erp_layout",
]
import atexit  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

# Uploads temporários dos testes vão para uma pasta descartável, removida no fim.
PRIVATE_MEDIA_ROOT = tempfile.mkdtemp(prefix="conc_test_private_")
MEDIA_ROOT = tempfile.mkdtemp(prefix="conc_test_media_")
atexit.register(shutil.rmtree, PRIVATE_MEDIA_ROOT, True)
atexit.register(shutil.rmtree, MEDIA_ROOT, True)

CONCRETAGEM_DRIVE_ENABLED = False
CONCRETAGEM_DRIVE_SEGUNDO_PLANO = False  # nos testes, roda no on_commit, sem thread
CONCRETAGEM_DRIVE_ROOT_FOLDER_ID = ""
GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE = ""
SITE_URL = "http://testserver/"
DEFAULT_FROM_EMAIL = "erp@example.com"
