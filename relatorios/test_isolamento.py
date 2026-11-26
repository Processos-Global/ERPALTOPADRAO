import io
from contextlib import redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from relatorios.executar_mysql_qa import main
from relatorios.isolamento_testes import configuracao_mysql_isolada, validar_isolamento


class IsolamentoTestesTest(SimpleTestCase):
    def _configuracao(self, banco, modulo):
        return SimpleNamespace(
            DATABASES={"default": banco}, SETTINGS_MODULE=modulo,
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            CONCRETAGEM_DRIVE_ENABLED=False, CONCRETAGEM_DRIVE_SEGUNDO_PLANO=False,
        )

    def test_sqlite_persistente_e_recusado(self):
        cfg = self._configuracao({"ENGINE": "django.db.backends.sqlite3", "NAME": "dev.sqlite3",
                                  "TEST": {"NAME": ":memory:"}}, "relatorios.test_settings")
        with self.assertRaises(RuntimeError):
            validar_isolamento(cfg)

    @patch.dict("os.environ", {"SAARI_QA_MYSQL_TOKEN": "0123456789abcdef", "SAARI_QA_MYSQL_PORT": "41234",
                               "SAARI_QA_MYSQL_PASSWORD": "sintetica"})
    def test_mysql_exige_schema_descartavel_e_banco_de_teste_ativo_ao_gravar(self):
        banco = configuracao_mysql_isolada()
        cfg = self._configuracao(banco, "relatorios.settings_mysql_qa")
        validar_isolamento(cfg)
        with self.assertRaises(RuntimeError):
            validar_isolamento(cfg, durante_testes=True)
        banco["NAME"] = banco["TEST"]["NAME"]
        validar_isolamento(cfg, durante_testes=True)
        banco["HOST"] = "mysql.example.test"
        with self.assertRaises(RuntimeError):
            validar_isolamento(cfg)

    def test_executor_recusa_opcoes_alheias_ao_perfil_e_geracao_de_migrations(self):
        casos = (
            (["migrate", "--"], "configurações e o caminho"),
            (["migrate", "--sett=config.settings"], "configurações e o caminho"),
            (["check", "--pythonpath", "outro"], "configurações e o caminho"),
            (["makemigrations"], "sem gravar arquivos"),
        )
        for argumentos, mensagem in casos:
            with self.subTest(argumentos=argumentos), redirect_stderr(io.StringIO()) as saida:
                with patch("sys.argv", ["executor", "--mysqld", "mysqld.exe", *argumentos]):
                    with self.assertRaises(SystemExit) as erro:
                        main()
                self.assertEqual(erro.exception.code, 2)
                self.assertIn(mensagem, saida.getvalue())
