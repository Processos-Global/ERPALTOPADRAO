
"""
ConfiguraÃ§Ãµes do ERP Alto PadrÃ£o.

Projeto desenvolvido com Django.
"""

from pathlib import Path

import environ
import os

# ============================================================
# CAMINHOS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# VARIÃVEIS DE AMBIENTE
# ============================================================

env = environ.Env(
    DEBUG=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")


# ============================================================
# SEGURANÃ‡A
# ============================================================

SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool(
    "DEBUG",
    default=False,
)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=[
        "127.0.0.1",
        "localhost",
    ],
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[],
)


# Hardening HTTP/HTTPS. Em produção, configure os valores correspondentes no .env.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# ============================================================
# APLICAÃ‡Ã•ES
# ============================================================

INSTALLED_APPS = [
    "cadastros.apps.CadastrosConfig",
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # ERP Alto PadrÃ£o
    "core",
    "usuarios.apps.UsuariosConfig",
    "obras",
    "planejamento",
    "suprimentos",
    "compras",
    "contratos",
    "financeiro",
    "almoxarifado",
    "projetos",
    "vistorias",
    "diario_obra",
    "pos_obra",
    "relatorios",
    "integracoes",
]


# ============================================================
# MIDDLEWARES
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URLS E EXECUÃ‡ÃƒO
# ============================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "usuarios.context_processors.erp_layout",
            ],
        },
    },
]


# ============================================================
# BANCO DE DADOS MYSQL
# ============================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env(
            "DB_NAME",
            default="erp_alto_padrao",
        ),
        "USER": env(
            "DB_USER",
            default="root",
        ),
        "PASSWORD": env(
            "DB_PASSWORD",
            default="",
        ),
        "HOST": env(
            "DB_HOST",
            default="127.0.0.1",
        ),
        "PORT": env(
            "DB_PORT",
            default="3306",
        ),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": (
                "SET sql_mode="
                "'STRICT_TRANS_TABLES,"
                "NO_ZERO_IN_DATE,"
                "NO_ZERO_DATE,"
                "ERROR_FOR_DIVISION_BY_ZERO,"
                "NO_ENGINE_SUBSTITUTION'"
            ),
        },
        "CONN_MAX_AGE": 60,
    },
}


# ============================================================
# VALIDAÃ‡ÃƒO DE SENHAS
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ============================================================
# INTERNACIONALIZAÃ‡ÃƒO
# ============================================================

LANGUAGE_CODE = "pt-br"

TIME_ZONE = env(
    "TIME_ZONE",
    default="America/Sao_Paulo",
)

USE_I18N = True

USE_TZ = True


# ============================================================
# FORMATOS DE DATA E NÃšMEROS
# ============================================================

DATE_FORMAT = "d/m/Y"

DATETIME_FORMAT = "d/m/Y H:i"

SHORT_DATE_FORMAT = "d/m/Y"

DECIMAL_SEPARATOR = ","

THOUSAND_SEPARATOR = "."

USE_THOUSAND_SEPARATOR = True


# ============================================================
# ARQUIVOS ESTÃTICOS
# ============================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"


# ============================================================
# ARQUIVOS DE MÃDIA
# ============================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# Documentos confidenciais nunca devem possuir URL pública direta.
_PRIVATE_MEDIA_ROOT_ENV = env("PRIVATE_MEDIA_ROOT", default="").strip()
PRIVATE_MEDIA_ROOT = (
    Path(_PRIVATE_MEDIA_ROOT_ENV)
    if _PRIVATE_MEDIA_ROOT_ENV
    else BASE_DIR.parent / "private_media"
)


# ============================================================
# GOOGLE DRIVE
# ============================================================

# Caminho do arquivo JSON da conta de serviÃ§o.
# Pode ser absoluto ou relativo ao BASE_DIR.
GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE = env(
    "GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE",
    default="credenciais/google-drive.json",
)

# Pasta que contÃ©m os arquivos CSV do cronograma de obras.
# O sistema buscarÃ¡ automaticamente o CSV modificado mais recentemente.
CRONOGRAMA_ALTO_PADRAO_FOLDER_ID = env(
    "CRONOGRAMA_ALTO_PADRAO_FOLDER_ID",
    default="",
)

# Pasta reservada para o cronograma de suprimentos.
GOOGLE_DRIVE_CRONOGRAMA_SUPRIMENTOS_FOLDER_ID = env(
    "GOOGLE_DRIVE_CRONOGRAMA_SUPRIMENTOS_FOLDER_ID",
    default="",
)


# ============================================================
# IMPORTAÃ‡ÃƒO DO CRONOGRAMA
# ============================================================

# Quantidade de linhas lidas por bloco pelo Pandas.
CRONOGRAMA_TAMANHO_BLOCO_LEITURA = env.int(
    "CRONOGRAMA_TAMANHO_BLOCO_LEITURA",
    default=5000,
)

# Quantidade de registros enviados por lote ao banco.
CRONOGRAMA_TAMANHO_LOTE_BANCO = env.int(
    "CRONOGRAMA_TAMANHO_LOTE_BANCO",
    default=2000,
)


# ============================================================
# SESSÃƒO E AUTENTICAÃ‡ÃƒO
# ============================================================

LOGIN_URL = "/usuarios/login/"

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "/usuarios/login/"

SESSION_COOKIE_AGE = 60 * 60 * 8

SESSION_SAVE_EVERY_REQUEST = True

SESSION_EXPIRE_AT_BROWSER_CLOSE = False


# ============================================================
# COOKIES
# ============================================================

SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = env.bool(
    "SESSION_COOKIE_SECURE",
    default=False,
)

CSRF_COOKIE_SECURE = env.bool(
    "CSRF_COOKIE_SECURE",
    default=False,
)


LOGIN_MAX_ATTEMPTS = env.int("LOGIN_MAX_ATTEMPTS", default=5)
LOGIN_LOCKOUT_SECONDS = env.int("LOGIN_LOCKOUT_SECONDS", default=900)

PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=1800)
PASSWORD_RESET_MAX_ATTEMPTS = env.int("PASSWORD_RESET_MAX_ATTEMPTS", default=3)
PASSWORD_RESET_LOCKOUT_SECONDS = env.int("PASSWORD_RESET_LOCKOUT_SECONDS", default=900)


# ============================================================
# MENSAGENS
# ============================================================

MESSAGE_STORAGE = (
    "django.contrib.messages.storage.session.SessionStorage"
)


# ============================================================
# UPLOADS
# ============================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024


# ============================================================
# E-MAIL
# ============================================================

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = env(
    "EMAIL_HOST",
    default="smtp.gmail.com",
)

EMAIL_PORT = env.int(
    "EMAIL_PORT",
    default=587,
)

EMAIL_USE_TLS = env.bool(
    "EMAIL_USE_TLS",
    default=True,
)

EMAIL_USE_SSL = env.bool(
    "EMAIL_USE_SSL",
    default=False,
)

EMAIL_TIMEOUT = env.int(
    "EMAIL_TIMEOUT",
    default=30,
)

EMAIL_HOST_USER = env(
    "EMAIL_HOST_USER",
    default="processos@globalengenharia.eng.br",
)

EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default=EMAIL_HOST_USER,
)

EMAIL_FROM = DEFAULT_FROM_EMAIL

SERVER_EMAIL = DEFAULT_FROM_EMAIL


# ============================================================
# LOGS
# ============================================================

LOG_DIR = BASE_DIR / "logs"

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detalhado": {
            "format": (
                "{levelname} {asctime} "
                "{name} {module} {message}"
            ),
            "style": "{",
        },
        "simples": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simples",
        },
        "arquivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "erp_alto_padrao.log"),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "detalhado",
            "encoding": "utf-8",
        },
    },
    "root": {
        "handlers": [
            "console",
            "arquivo",
        ],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": [
                "console",
                "arquivo",
            ],
            "level": "INFO",
            "propagate": False,
        },
        "planejamento": {
            "handlers": [
                "console",
                "arquivo",
            ],
            "level": "INFO",
            "propagate": False,
        },
        "integracoes": {
            "handlers": [
                "console",
                "arquivo",
            ],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# ============================================================
# CONFIGURAÃ‡Ã•ES PADRÃƒO
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CRONOGRAMA_SUPRIMENTOS_FILE_ID = os.getenv(
    "CRONOGRAMA_SUPRIMENTOS_FILE_ID",
    ""
)

CRONOGRAMA_SUPRIMENTOS_FOLDER_ID = os.getenv(
    "CRONOGRAMA_SUPRIMENTOS_FOLDER_ID",
    ""
)
