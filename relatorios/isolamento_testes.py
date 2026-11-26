import os
import re
import sys


def configuracao_mysql_isolada():
    token = os.environ.get("SAARI_QA_MYSQL_TOKEN", "")
    porta = os.environ.get("SAARI_QA_MYSQL_PORT", "")
    senha = os.environ.get("SAARI_QA_MYSQL_PASSWORD", "")
    if (not re.fullmatch(r"[0-9a-f]{16}", token) or not re.fullmatch(r"[0-9]{4,5}", porta)
            or not 1024 < int(porta) <= 65535 or int(porta) == 3306 or not senha):
        raise RuntimeError("Configure uma instância MySQL descartável para a execução SAARI QA.")
    return {
        "ENGINE": "django.db.backends.mysql",
        "HOST": "127.0.0.1",
        "PORT": porta,
        "USER": f"saari_qa_{token}",
        "PASSWORD": senha,
        "NAME": f"saari_base_{token}",
        "TEST": {"NAME": f"saari_test_{token}"},
        "OPTIONS": {"charset": "utf8mb4"},
    }


def validar_isolamento(configuracao, *, durante_testes=False):
    """Valida as configurações antes de descobrir testes ou gravar fixtures."""
    if "config.settings" in sys.modules or set(configuracao.DATABASES) != {"default"}:
        raise RuntimeError("A suíte deve usar somente as configurações isoladas do SAARI.")
    if (configuracao.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend"
            or configuracao.CONCRETAGEM_DRIVE_ENABLED or configuracao.CONCRETAGEM_DRIVE_SEGUNDO_PLANO):
        raise RuntimeError("A suíte exige e-mail em memória e Drive desativado.")

    banco = configuracao.DATABASES["default"]
    nome = banco["NAME"]
    if banco["ENGINE"] == "django.db.backends.sqlite3" and banco.get("TEST", {}).get("NAME") == ":memory:":
        if nome in {":memory:", "file:memorydb_default?mode=memory&cache=shared"}:
            return

    if configuracao.SETTINGS_MODULE == "relatorios.settings_mysql_qa":
        esperado = configuracao_mysql_isolada()
        nomes = {esperado["TEST"]["NAME"]}
        if not durante_testes:
            nomes.add(esperado["NAME"])
        campos = ("ENGINE", "HOST", "PORT", "USER", "PASSWORD")
        if (all(banco.get(campo) == esperado[campo] for campo in campos)
                and banco.get("TEST", {}).get("NAME") == esperado["TEST"]["NAME"] and nome in nomes):
            return
    raise RuntimeError("Banco fora do perfil de teste isolado do SAARI.")
