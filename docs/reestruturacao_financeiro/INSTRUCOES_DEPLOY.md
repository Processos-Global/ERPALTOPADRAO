# Publicação posterior no PythonAnywhere

Use uma janela autorizada e a revisão previamente homologada. Suspenda as escritas da aplicação e de rotinas agendadas durante o backup e a mudança de índices. O MySQL confirma cada DDL separadamente, de modo que a coluna gerada e o índice único podem existir em etapas diferentes durante a mesma publicação.

## Preparar backup e homologação

1. Confirme na aba **Databases** o host e o nome completo da base. Anote a revisão anterior, as migrations aplicadas e a versão do Python da aplicação. Use a autenticação já provisionada no host.
2. Faça o dump em diretório privado, guarde uma cópia da mídia privada e dos arquivos enviados e valide a restauração em um schema separado. Verifique a integridade dos anexos e reconcilie contagens de títulos, pagamentos e pedidos.

```bash
umask 077
mkdir -p "$HOME/saari-backup"
mysqldump -h HOST_PYTHONANYWHERE -u USUARIO --single-transaction --set-gtid-purged=OFF \
  --no-tablespaces 'USUARIO$NOME_BANCO' > "$HOME/saari-backup/antes-da-publicacao.sql"
```

O nome completo do schema do PythonAnywhere inclui o caractere `$`. Preserve as aspas e use o mecanismo de acesso do host. Confira se o dump terminou com código zero e a mídia privada está íntegra. Ensaie a recuperação em um schema vazio separado. [Backup e restauração no PythonAnywhere](https://help.pythonanywhere.com/pages/MySQLBackupRestore/)

```bash
mysql -h HOST_PYTHONANYWHERE -u USUARIO 'USUARIO$SCHEMA_RECUPERACAO' \
  < "$HOME/saari-backup/antes-da-publicacao.sql"
```

3. Na conexão que será usada pelo Django, confirme suporte ao fuso nomeado e os metadados do InnoDB. Um resultado `NULL` em `CONVERT_TZ` indica que a conversão por nome está indisponível. Acione o responsável pelo MySQL hospedado antes de operar o Planejamento Financeiro. Preserve `USE_TZ = True` e `America/Sao_Paulo`.

```sql
SELECT CONVERT_TZ('2026-11-25 03:30:00', 'UTC', 'America/Sao_Paulo') AS atual,
       CONVERT_TZ('2018-12-15 03:30:00', 'UTC', 'America/Sao_Paulo') AS historico;
SELECT VERSION(), @@innodb_page_size, @@innodb_default_row_format;
SHOW TABLE STATUS LIKE 'compras_suprimentoreferencia';
SHOW INDEX FROM compras_suprimentoreferencia;
SELECT COUNT(*) AS registros, MAX(CHAR_LENGTH(chave)) AS max_caracteres,
       MAX(OCTET_LENGTH(chave)) AS max_bytes,
       COUNT(CASE WHEN CHAR_LENGTH(chave) > 255 THEN 1 END) AS acima_de_255
FROM compras_suprimentoreferencia;
SELECT COUNT(*) AS registros, MAX(CHAR_LENGTH(suprimento_chave)) AS max_caracteres,
       MAX(OCTET_LENGTH(suprimento_chave)) AS max_bytes
FROM compras_historicocomprasuprimento;
```

Os valores esperados para o horário local são `00:30:00` e `01:30:00`, respectivamente. O segundo horário verifica a época de horário de verão. A chave de Suprimentos usa `VARCHAR(500)`, até 2.000 bytes em `utf8mb4`. Confirme que o índice único tem `Sub_part` nulo e que o formato de linha e tamanho da página suportam o índice completo. [Fusos no MySQL](https://dev.mysql.com/doc/refman/8.0/en/time-zone-support.html) · [Limites do InnoDB](https://dev.mysql.com/doc/refman/8.0/en/innodb-limits.html)

4. Execute os diagnósticos após disponibilizar o código da revisão e antes de adicionar os índices. Se houver duplicados, mantenha a publicação suspensa até uma decisão documentada sobre os registros. O diagnóstico de contratações reporta IDs. O diagnóstico de fornecedores reporta contagens sem imprimir documentos.

```bash
python manage.py diagnosticar_documentos_fornecedores
python manage.py diagnosticar_contratacoes_duplicadas
python manage.py migrate --plan
```

Para cada grupo de fornecedores em conflito, a equipe de Cadastros pode conferir os documentos e os vínculos em ambiente restrito. Se houver erro de digitação comprovado, registre a decisão e use o fluxo normal de edição antes de repetir o diagnóstico. Desativar um fornecedor mantém seu documento sujeito à unicidade. Se dois cadastros precisarem conservar o mesmo documento, encaminhe o caso para decisão de negócio antes da migration. Para contratações, compare situação, anexo, pedidos e liberações de cada ID. Quando a duplicação for confirmada, use o cancelamento auditado nas condições admitidas pelo fluxo e preserve os vínculos históricos. Caso haja pedidos ou liberações que impeçam esse tratamento, mantenha a migration suspensa para análise conjunta de Compras e Financeiro.

## Aplicar a revisão aprovada

```bash
cd /caminho/do/checkout
source /caminho/da/venv/bin/activate
git status --short --branch
git rev-parse HEAD
git fetch origin
git log --oneline HEAD..origin/main
git merge --ff-only origin/main
python -m pip install -r requirements.txt
python manage.py check --database default
python manage.py makemigrations --check --dry-run
python manage.py diagnosticar_documentos_fornecedores
python manage.py diagnosticar_contratacoes_duplicadas
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Compare a referência remota com a revisão aprovada antes do fast-forward. O grafo aplica as dependências das migrations anteriores e instala, nesta retomada, `cadastros/0017` antes de `0018` e `compras/0042` antes de `0043`. Mantenha as escritas pausadas até que as quatro novas migrations concluam. Se a criação de um índice falhar por colisão, confira `showmigrations`, use os diagnósticos e retome após resolver a inconsistência autorizada. `--fake` apagaria a correspondência entre histórico e esquema.

Na aba **Web**, confirme o mapeamento de `STATIC_URL` para `STATIC_ROOT` e use **Reload**. Antes de reabrir as escritas, valide login e permissões, um PDF e um XLSX, títulos, parcelas, programação, saldos, recebimento com frete e data local no Planejamento. [Arquivos estáticos e Reload](https://help.pythonanywhere.com/pages/DjangoStaticFiles/)

```bash
python manage.py diagnosticar_duplicidades_financeiras --saida duplicidades_financeiras.csv
python manage.py diagnosticar_frete_compras --somente-divergencias
python manage.py exportar_pagamentos_excel --help
```

Em caso de rollback, mantenha as escritas suspensas e confirme em uma cópia a compatibilidade entre a revisão anterior e o esquema aplicado. A reversão dos novos índices remove a proteção no MySQL e deve ser planejada. Caso seja necessário restaurar dados, restaure o dump e a mídia privada em área separada, valide registros e anexos e reconcilie escritas posteriores ao backup antes de direcionar a aplicação para a base recuperada. Recolha os estáticos da revisão restaurada e use **Reload**.
