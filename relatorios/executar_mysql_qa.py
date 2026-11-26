"""Executa uma verificação do Django em um servidor MySQL descartável."""
import argparse
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pymysql


def _porta_livre():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _aguardar_servidor(processo, log):
    inicio = time.monotonic()
    while time.monotonic() - inicio < 60:
        if processo.poll() is not None:
            break
        if log.exists() and "ready for connections" in log.read_text(encoding="utf-8", errors="replace"):
            return
        time.sleep(0.2)
    raise RuntimeError("O MySQL descartável não iniciou no prazo.")


def _validar_instancia(conexao, pasta):
    with conexao.cursor() as cursor:
        cursor.execute("SELECT @@datadir, @@port, VERSION(), @@innodb_page_size, @@innodb_default_row_format")
        dados, porta, versao, pagina, formato = cursor.fetchone()
        if Path(dados).resolve() != pasta or porta != conexao.port:
            raise RuntimeError("Conexão recusada: o servidor não é a instância descartável criada.")
        print(f"MySQL {versao} descartável, porta {porta}, InnoDB {formato}/{pagina} B.", flush=True)


def _carregar_fuso(cursor, zona):
    epoca = datetime(1970, 1, 1, tzinfo=UTC)

    def tipo(instante):
        local = (epoca + timedelta(seconds=instante)).astimezone(zona)
        return int(local.utcoffset().total_seconds()), int(bool(local.dst())), local.tzname()

    # O conversor MySQL pode ignorar as transições da seção de 64 bits de um
    # TZif slim. ZoneInfo lê a seção adequada, inclusive o horário de verão.
    inicio = int(datetime(1900, 1, 1, tzinfo=UTC).timestamp())
    fim = int(datetime(2101, 1, 1, tzinfo=UTC).timestamp())
    anterior = tipo(inicio)
    tipos = {anterior: 0}
    transicoes = []
    for instante in range(inicio + 86400, fim, 86400):
        atual = tipo(instante)
        if atual == anterior:
            continue
        antes, depois = instante - 86400, instante
        while depois - antes > 1:
            meio = (antes + depois) // 2
            if tipo(meio) == anterior:
                antes = meio
            else:
                depois = meio
        transicoes.append((depois, tipos.setdefault(atual, len(tipos))))
        anterior = atual

    cursor.execute("INSERT INTO mysql.time_zone (Use_leap_seconds) VALUES ('N')")
    fuso_id = cursor.lastrowid
    cursor.execute("INSERT INTO mysql.time_zone_name (Name, Time_zone_id) VALUES (%s, %s)", (zona.key, fuso_id))
    cursor.executemany(
        "INSERT INTO mysql.time_zone_transition_type VALUES (%s, %s, %s, %s, %s)",
        [(fuso_id, identificador, *dados) for dados, identificador in tipos.items()],
    )
    cursor.executemany("INSERT INTO mysql.time_zone_transition VALUES (%s, %s, %s)",
                       [(fuso_id, instante, identificador) for instante, identificador in transicoes])


def _preparar_instancia(conexao, token, senha):
    with conexao.cursor() as cursor:
        zona = ZoneInfo("America/Sao_Paulo")
        _carregar_fuso(cursor, ZoneInfo("UTC"))
        _carregar_fuso(cursor, zona)
        for data in (datetime(2026, 11, 25, 3, 30, tzinfo=UTC), datetime(2018, 12, 15, 3, 30, tzinfo=UTC)):
            cursor.execute("SELECT CONVERT_TZ(%s, 'UTC', %s)", (data.replace(tzinfo=None), zona.key))
            if cursor.fetchone()[0] != data.astimezone(zona).replace(tzinfo=None):
                raise RuntimeError("O MySQL de QA não converteu o fuso America/Sao_Paulo.")
        print("Conversao de UTC para America/Sao_Paulo confirmada com datas atuais e historicas.", flush=True)
        nome_usuario = f"saari_qa_{token}"
        cursor.execute("CREATE USER %s@'127.0.0.1' IDENTIFIED BY %s", (nome_usuario, senha))
        cursor.execute(f"CREATE DATABASE `saari_base_{token}` CHARACTER SET utf8mb4")
        for prefixo in ("base", "test"):
            nome = f"saari_{prefixo}_{token}".replace("_", r"\_")
            cursor.execute(f"GRANT ALL PRIVILEGES ON \x60{nome}\x60.* TO %s@'127.0.0.1'", (nome_usuario,))


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--mysqld", type=Path, required=True)
    parser.add_argument("--com-migrations", action="store_true")
    parser.add_argument("comando", nargs=argparse.REMAINDER)
    argumentos = parser.parse_args()
    comando = argumentos.comando
    if not comando or comando[0] not in {"test", "check", "makemigrations", "migrate"}:
        parser.error("Informe test, check, makemigrations ou migrate com os argumentos desejados.")
    opcoes = {arg.split("=", 1)[0] for arg in comando[1:] if arg.startswith("--")}
    if any("--settings".startswith(opcao) or "--pythonpath".startswith(opcao) for opcao in opcoes):
        parser.error("O executor define as configurações e o caminho de importação de QA.")
    if comando[0] == "makemigrations" and not opcoes.intersection({"--check", "--dry-run"}):
        parser.error("Execute makemigrations com --check ou --dry-run para validar sem gravar arquivos.")
    mysqld = argumentos.mysqld.resolve(strict=True)
    token = secrets.token_hex(8)
    senha = secrets.token_hex(24)
    porta = _porta_livre()
    with TemporaryDirectory(prefix="saari-mysql-qa-") as temporario:
        raiz = Path(temporario).resolve()
        pasta = raiz / "db"
        log = raiz / "mysql.log"
        base = [str(mysqld), "--no-defaults", f"--basedir={mysqld.parent.parent}", f"--datadir={pasta}"]
        subprocess.run([*base, "--initialize-insecure", f"--log-error={log}"], check=True)
        log_inicio = raiz / "mysql-inicio.log"
        processo = subprocess.Popen([
            *base, "--bind-address=127.0.0.1", f"--port={porta}", "--mysqlx=OFF",
            "--skip-log-bin", f"--log-error={log_inicio}", f"--pid-file={raiz / 'mysql.pid'}",
        ])
        try:
            _aguardar_servidor(processo, log_inicio)
            with pymysql.connect(host="127.0.0.1", port=porta, user="root", autocommit=True) as conexao:
                _validar_instancia(conexao, pasta)
                try:
                    _preparar_instancia(conexao, token, senha)
                    ambiente = {
                        **os.environ, "DJANGO_SETTINGS_MODULE": "relatorios.settings_mysql_qa",
                        "SAARI_QA_MYSQL_TOKEN": token, "SAARI_QA_MYSQL_PORT": str(porta),
                        "SAARI_QA_MYSQL_PASSWORD": senha, "SAARI_QA_MYSQL_MIGRATIONS": str(int(argumentos.com_migrations)),
                    }
                    return subprocess.call([sys.executable, "manage.py", *comando],
                                           cwd=Path(__file__).resolve().parent.parent, env=ambiente)
                finally:
                    with conexao.cursor() as cursor:
                        cursor.execute("SHUTDOWN")
        finally:
            try:
                processo.wait(timeout=15)
            except subprocess.TimeoutExpired:
                processo.terminate()
                processo.wait(timeout=15)


if __name__ == "__main__":
    sys.exit(main())
