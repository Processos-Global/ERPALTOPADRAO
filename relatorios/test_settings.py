"""Independent, disposable settings. Never imports application settings or .env."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'isolated-tests-only-not-a-deployment-key'
DEBUG = False
ALLOWED_HOSTS = ['testserver']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:', 'TEST': {'NAME': ':memory:'}}}
assert set(DATABASES) == {'default'}
assert DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
assert DATABASES['default']['NAME'] == DATABASES['default']['TEST']['NAME'] == ':memory:'
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'cadastros', 'core', 'usuarios', 'obras', 'planejamento', 'suprimentos', 'compras', 'contratos', 'financeiro', 'almoxarifado', 'projetos', 'vistorias', 'diario_obra', 'pos_obra', 'relatorios', 'integracoes']
MIGRATION_MODULES = {app.rsplit('.', 1)[-1]: None for app in INSTALLED_APPS}
ROOT_URLCONF = 'config.urls'
MIDDLEWARE = ['django.contrib.sessions.middleware.SessionMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware']
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
PRIVATE_MEDIA_ROOT = BASE_DIR / '__unused_test_private_media__'
PRIVATE_MEDIA_URL = '/private/'
USE_TZ = True
TIME_ZONE = 'America/Sao_Paulo'
LANGUAGE_CODE = 'pt-br'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
LOGIN_URL = '/usuarios/login/'
